"""Scripted benign users. Two session types, chosen at a seeded random:

  web  — GET the home page, parse its links/assets, follow a random subset with
         random think times, like a person reading the site.
  ssh  — log in as the test admin, run a few ordinary commands, log out.

Everything is driven by LAB_SEED so a run reproduces. BENIGN_RATE scales the
pace (actions per minute, roughly): higher = shorter gaps. Each completed
session writes one ground-truth line with intent="benign"."""
from __future__ import annotations

import os
import random
import re
import time

import paramiko
import requests

from lib.gt import GroundTruth

SEED = int(os.environ.get("LAB_SEED", "1"))
RATE = float(os.environ.get("BENIGN_RATE", "1.0"))
WEB = [u for u in os.environ.get("WEB_TARGETS", "http://172.28.0.10").split(",") if u]
SSH = [h for h in os.environ.get("SSH_TARGETS", "172.28.0.11").split(",") if h]
GT = GroundTruth(os.environ.get("GROUND_TRUTH", "/data/logs/ground_truth/benign.jsonl"))

SSH_USER, SSH_PASS = "admin", "correct-horse-battery"
SSH_CMDS = ["whoami", "uptime", "ls -la /home/admin", "cat /etc/motd", "df -h", "ps aux"]
SITE_PATHS = ["/", "/about.html", "/docs.html", "/status.html", "/contact.html",
              "/assets/style.css", "/assets/app.js", "/assets/logo.svg", "/assets/manual.txt"]
HREF = re.compile(r'(?:href|src)="(/[^"]*)"')

# Dense mode: many parallel workers, each request its own TCP connection (so one
# flow per request), minimal think time — to build a large benign capture quickly.
WORKERS = int(os.environ.get("BENIGN_WORKERS", "1"))
DENSE = os.environ.get("BENIGN_DENSE", "0") == "1"

rng = random.Random(SEED)


def dense_web_session(base: str, wrng: random.Random) -> None:
    """One short web burst, each GET on a fresh connection (Connection: close),
    so every request is a distinct flow. Used only in dense capture mode."""
    t0 = time.time()
    host = base.split("//", 1)[-1].split("/", 1)[0]
    n_req, n_bytes = 0, 0
    for path in wrng.sample(SITE_PATHS, wrng.randint(2, len(SITE_PATHS))):
        try:
            r = requests.get(base + path, timeout=5,
                             headers={"User-Agent": "Mozilla/5.0 AcmeBrowse/1.0",
                                      "Connection": "close"})
            n_req += 1; n_bytes += len(r.content)
        except requests.RequestException:
            pass
    GT.log(dst=host, dst_port=80, intent="benign", kind="web",
           t_start=t0, t_end=time.time(), requests=n_req, bytes=n_bytes)


def think() -> None:
    # Mean gap ~ 3s / RATE, exponential (Poisson-ish arrivals), with diurnal-ish
    # jitter so the stream is not perfectly stationary.
    time.sleep(rng.expovariate(RATE / 3.0))


def web_session(base: str) -> None:
    t0 = time.time()
    n_req, n_bytes = 0, 0
    host = base.split("//", 1)[-1].split("/", 1)[0]
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AcmeBrowse/1.0"
    try:
        r = sess.get(base + "/", timeout=5)
        n_req += 1; n_bytes += len(r.content)
        links = list(dict.fromkeys(HREF.findall(r.text)))
        rng.shuffle(links)
        for path in links[: rng.randint(1, max(1, len(links)))]:
            time.sleep(rng.expovariate(RATE))  # think time between clicks
            try:
                rr = sess.get(base + path, timeout=5)
                n_req += 1; n_bytes += len(rr.content)
            except requests.RequestException:
                pass
    except requests.RequestException:
        pass
    finally:
        sess.close()
    GT.log(dst=host, dst_port=80, intent="benign", kind="web",
           t_start=t0, t_end=time.time(), requests=n_req, bytes=n_bytes)


def ssh_session(host: str) -> None:
    t0 = time.time()
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    n_cmds = 0
    try:
        cli.connect(host, port=22, username=SSH_USER, password=SSH_PASS,
                    timeout=6, allow_agent=False, look_for_keys=False)
        for cmd in rng.sample(SSH_CMDS, rng.randint(2, len(SSH_CMDS))):
            time.sleep(rng.expovariate(RATE))
            _in, out, _err = cli.exec_command(cmd, timeout=5)
            out.read(); n_cmds += 1
    except Exception:
        pass
    finally:
        cli.close()
    GT.log(dst=host, dst_port=22, intent="benign", kind="ssh",
           t_start=t0, t_end=time.time(), commands=n_cmds)


def _worker(wid: int) -> None:
    wrng = random.Random(SEED * 100003 + wid)  # per-worker stream, reproducible
    while True:
        if DENSE:
            # mostly web (dense flows); an occasional ssh session for realism
            if wrng.random() < 0.9 and WEB:
                dense_web_session(wrng.choice(WEB), wrng)
            elif SSH:
                ssh_session(wrng.choice(SSH))
            # tiny gap so workers don't lockstep; dense = high throughput
            time.sleep(wrng.uniform(0.0, 0.2))
        else:
            if wrng.random() < 0.7 and WEB:
                web_session(wrng.choice(WEB))
            elif SSH:
                ssh_session(wrng.choice(SSH))
            time.sleep(wrng.expovariate(RATE / 3.0))


def main() -> None:
    print(f"benign-client: seed={SEED} rate={RATE} workers={WORKERS} dense={DENSE} "
          f"web={WEB} ssh={SSH}", flush=True)
    if WORKERS <= 1:
        _worker(0)
        return
    import threading
    threads = [threading.Thread(target=_worker, args=(i,), daemon=True) for i in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
