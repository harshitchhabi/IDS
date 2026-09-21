#!/usr/bin/env bash
# One-time Cowrie install inside WSL2 Ubuntu (run via: python scripts/run.py cowrie setup).
# Why WSL and not Docker Desktop: this machine has 8 GB of RAM, and Docker Desktop adds a second VM and its
# own services on top of WSL2. Cowrie is pure Python, so a venv inside the (2 GB-capped) WSL VM is enough.
# Cowrie listens on 127.0.0.1:2222 ONLY, never 0.0.0.0 (CLAUDE.md safety constraints).
set -euo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
HERE="$(dirname "$(readlink -f "$0")")"
PROJ="$(dirname "$(dirname "$HERE")")"
LOGDIR="$PROJ/data/cowrie/log"

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
cd "$HOME"
[ -d cowrie ] || git clone --depth 1 https://github.com/cowrie/cowrie.git
cd cowrie
# Cowrie's dependencies (twisted, cryptography, ...) are not all available for the distro's newest Python
[ -d cowrie-env ] || uv venv --python 3.12 cowrie-env
uv pip install --python cowrie-env/bin/python -e .

mkdir -p etc var/lib/cowrie var/run "$LOGDIR"
cat > etc/cowrie.cfg <<EOF
[honeypot]
hostname = svr04
log_path = $LOGDIR
state_path = $HOME/cowrie/var/lib/cowrie
[ssh]
enabled = true
listen_endpoints = tcp:2222:interface=127.0.0.1
[telnet]
enabled = false
[output_jsonlog]
enabled = true
logfile = $LOGDIR/cowrie.json
EOF
# Only these lab-fake pairs log in; everything else is refused, so brute force shows real failed attempts.
cat > etc/userdb.txt <<EOF
root:x:toor
admin:x:admin123
ubuntu:x:ubuntu
EOF
echo "cowrie installed; config -> $HOME/cowrie/etc/cowrie.cfg, json log -> $LOGDIR/cowrie.json"
