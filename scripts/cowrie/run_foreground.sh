#!/usr/bin/env bash
# Run Cowrie in the foreground (the launching wsl.exe process keeps the WSL VM alive while it runs).
set -euo pipefail
export PATH="$HOME/cowrie/cowrie-env/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME/cowrie"
rm -f var/run/cowrie.pid
exec twistd -n --umask=0022 --pidfile= cowrie
