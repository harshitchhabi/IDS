#!/usr/bin/env bash
# Phase B exploratory pilot (docs/phaseB/README.md step 4). EXPLORATORY — not a result.
#
# Brings the lab up, runs benign users to learn a profile, then runs the mimic
# adversary (benign-shaped traffic at the honeypot) plus a few small real attacks,
# extracts the captured pcaps with the Dockerised fixed CICFlowMeter, labels the
# flows, and measures NN distance / twin fraction / cost. All timings are short by
# default so the whole pilot fits a laptop; override with the env vars below.
set -euo pipefail
cd "$(dirname "$0")/.."                      # lab/

BENIGN_WARMUP=${BENIGN_WARMUP:-420}          # seconds of benign-only, to learn a profile
MIMIC_SECONDS=${MIMIC_SECONDS:-600}          # seconds of mimic sessions at the honeypot
REPO=$(cd .. && pwd)
PY="$REPO/.venv/Scripts/python.exe"
DATA=data
GT=$DATA/logs/ground_truth

echo "== up =="; docker compose up -d --build
echo "== benign warmup ${BENIGN_WARMUP}s (profile learning) =="; sleep "$BENIGN_WARMUP"

echo "== learn benign profile =="
"$PY" tools/learn_profile.py --ground-truth "$GT/benign.jsonl" --out "$DATA/profiles/benign_profile.json"

echo "== mimic (poison) + small real attacks =="
# MSYS_NO_PATHCONV stops Git Bash rewriting the container-side /app/... path into a
# Windows path before docker sees it.
export MSYS_NO_PATHCONV=1
docker compose exec -T attacker python /app/attack.py mimic --seconds "$MIMIC_SECONDS" &
MIMIC_PID=$!
sleep 30
docker compose exec -T attacker python /app/attack.py portscan --host 172.28.0.21 || true
docker compose exec -T attacker python /app/attack.py ssh-guess --target honeypot --attempts 12 || true
docker compose exec -T attacker python /app/attack.py webprobe --host 172.28.0.21 || true
wait $MIMIC_PID || true

echo "== flush capture, extract =="; docker compose stop capture
mkdir -p "$DATA/flows_in" "$DATA/flows_out"
rm -f "$DATA"/flows_in/*.pcap "$DATA"/flows_out/*.csv 2>/dev/null || true
cp "$DATA"/pcap/*.pcap "$DATA/flows_in/" 2>/dev/null || true
# Offline extraction. MSYS_NO_PATHCONV stops Git Bash rewriting the container-side
# /tmp/pcap args into Windows paths; pwd -W gives Docker Desktop a Windows host path.
HOSTDATA="$(pwd -W 2>/dev/null || pwd)/$DATA"
MSYS_NO_PATHCONV=1 docker run --rm --network none -v "${HOSTDATA}:/tmp/pcap" \
  dloop-cicflowmeter:4dd5319 /tmp/pcap/flows_in /tmp/pcap/flows_out
# The tool writes one <pcap>_Flow.csv per pcap, all with an identical header line.
awk 'FNR==1 && seen{next} {print} FNR==1{seen=1}' "$DATA"/flows_out/*_Flow.csv > "$DATA/flows_all.csv"

echo "== label + measure =="
"$PY" tools/label.py --flows "$DATA/flows_all.csv" --ground-truth "$GT/benign.jsonl" "$GT/attacker.jsonl" \
  --out "$REPO/results/phaseB/labelled.csv"
"$PY" tools/pilot_measure.py --labelled "$REPO/results/phaseB/labelled.csv" \
  --ground-truth "$GT/benign.jsonl" "$GT/attacker.jsonl" --out "$REPO/results/phaseB/pilot.json"
echo "== done; see results/phaseB/pilot.json =="
