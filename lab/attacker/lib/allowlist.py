"""Target allowlist. Every attack routine calls require_allowed() on its target
before it sends anything; an address not in TARGET_ALLOWLIST raises and nothing
fires. This is the CLAUDE.md safety constraint ("attack tooling runs only against
containers in this compose project") enforced in code, not by convention."""
from __future__ import annotations

import os


def allowed() -> frozenset[str]:
    raw = os.environ.get("TARGET_ALLOWLIST", "")
    return frozenset(a.strip() for a in raw.split(",") if a.strip())


def require_allowed(target: str) -> str:
    """Return *target* if it is on the allowlist, else raise. Hostnames are not
    accepted — only the explicit lab IPs, so a DNS surprise cannot widen scope."""
    host = target.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    ok = allowed()
    if host not in ok:
        raise PermissionError(
            f"target {host!r} is not on TARGET_ALLOWLIST ({sorted(ok)}); refusing to send")
    return target
