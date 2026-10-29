"""Low-interaction HTTP honeypot. Serves the same static pages as prod-web so a
mimicking client cannot tell the two apart from content alone, and records every
request as a JSON line. It never executes anything a request asks for: SQLi/XSS
probes are logged and answered with an ordinary page or 404, exactly as a static
server would. The loop's policy ("seen by a honeypot -> malicious") is applied in
tools/label.py from the destination, not here."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

SITE = Path(os.environ.get("SITE_DIR", "/site"))
LOG = Path(os.environ.get("HP_LOG", "/var/log/hp/http_honeypot.jsonl"))
LOG.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def _record() -> None:
    rec = {
        "ts": time.time(),
        "src_ip": request.remote_addr,
        "method": request.method,
        "path": request.path,
        "query": request.query_string.decode("latin-1"),
        "ua": request.headers.get("User-Agent", ""),
        "length": request.content_length or 0,
    }
    with LOG.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


@app.after_request
def _log(resp: Response) -> Response:
    try:
        _record()
    except Exception:  # logging must never take the honeypot down
        pass
    return resp


@app.route("/", defaults={"page": "index.html"})
@app.route("/<path:page>")
def serve(page: str) -> Response:
    target = (SITE / page)
    if target.is_dir():
        target = target / "index.html"
        page = f"{page}/index.html"
    if target.is_file():
        return send_from_directory(SITE, page)
    # Unknown path (including probe URLs): a plain 404, like a static server.
    return Response("Not Found", status=404, mimetype="text/plain")
