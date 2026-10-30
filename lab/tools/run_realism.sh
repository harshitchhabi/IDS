#!/usr/bin/env bash
# Phase B.4 (DECISIONS §33): one honeypot condition end to end.
#   L = low-interaction (Cowrie :2222 / Flask :21 at .20/.21)
#   H = high-interaction clone (prod-identical nginx :80 / OpenSSH :22 at .22/.23)
# Capture (short rotations) -> per-file extract -> label -> build -> B.1 -> B.2.
# Memory rule: never raises limits; inputs split. Caller watches Windows memory.
set -uo pipefail
cd "$(dirname "$0")/.."                 # lab/
COND="${1:?usage: run_realism.sh L|H}"
REPO=$(cd .. && pwd); PY="$REPO/.venv/Scripts/python.exe"
LD="$(pwd -W)/data"; GT=data/logs/ground_truth
export MSYS_NO_PATHCONV=1
BENIGN_SECONDS=${BENIGN_SECONDS:-400}; MIMIC_SECONDS=${MIMIC_SECONDS:-200}

if [ "$COND" = "L" ]; then
  export HTTP_HONEYPOT=172.28.0.21 SSH_HONEYPOT=172.28.0.20 SSH_HONEYPOT_PORT=2222
  HP_IPS="172.28.0.20,172.28.0.21"; SVCS="prod-web prod-ssh cowrie http-honeypot benign-client attacker capture"
else
  export HTTP_HONEYPOT=172.28.0.22 SSH_HONEYPOT=172.28.0.23 SSH_HONEYPOT_PORT=22
  HP_IPS="172.28.0.22,172.28.0.23"; SVCS="prod-web prod-ssh http-honeypot-hi ssh-honeypot-hi benign-client attacker capture"
fi
echo "== condition $COND : honeypots $HP_IPS =="

rm -f data/pcap/*.pcap "$GT"/*.jsonl 2>/dev/null || true
mkdir -p data/pcap "$GT" data/profiles
ROTATE_SECONDS=30 BENIGN_WORKERS=6 BENIGN_DENSE=1 docker compose up -d $SVCS
sleep 12
echo "== dense benign ${BENIGN_SECONDS}s =="; sleep "$BENIGN_SECONDS"
docker compose exec -T attacker python /app/attack.py benign --seconds 90
"$PY" tools/learn_profile.py --ground-truth "$GT/attacker.jsonl" --out data/profiles/profile_attacker.json
"$PY" tools/learn_profile.py --ground-truth "$GT/benign.jsonl"   --out data/profiles/profile_defender.json
echo "== mimic replay + oracle =="
docker compose exec -T attacker python /app/attack.py replay --seconds "$MIMIC_SECONDS"
docker compose exec -T attacker python /app/attack.py mimic --seconds "$MIMIC_SECONDS" \
  --profile /profiles/profile_defender.json --tag mimic_oracle
echo "== scaled attacks (>=1000 eval attack rows target) =="
docker compose exec -T attacker python /app/attack.py portscan --host "$HTTP_HONEYPOT" --ports 1-1000 || true
docker compose exec -T attacker python /app/attack.py portscan --host 172.28.0.10 --ports 1-1000 || true
docker compose exec -T attacker python /app/attack.py ssh-guess --target honeypot --attempts 300 --delay 0.2 || true
docker compose exec -T attacker python /app/attack.py ssh-guess --target prod --attempts 300 --delay 0.2 || true
docker compose exec -T attacker python /app/attack.py webprobe --host "$HTTP_HONEYPOT" --count 120 --delay 0.1 || true
docker compose exec -T attacker python /app/attack.py webprobe --host 172.28.0.10 --count 120 --delay 0.1 || true
docker compose stop capture benign-client
echo "== extract rotated pcaps (fresh JVM each) =="
STAGE=data/realism_stage; OUT=data/realism_out; rm -rf "$STAGE" "$OUT"; mkdir -p "$STAGE" "$OUT"
for pc in data/pcap/*.pcap; do
  [ -s "$pc" ] || continue
  rm -f "$STAGE"/*.pcap; cp "$pc" "$STAGE/"
  docker run --rm --network none -v "${LD}:/tmp/pcap" dloop-cicflowmeter:4dd5319 \
    /tmp/pcap/realism_stage /tmp/pcap/realism_out >/dev/null 2>&1 || true
done
rm -rf "$STAGE"
awk 'FNR==1 && seen{next} {print} FNR==1{seen=1}' "$OUT"/*_Flow.csv > "data/realism_${COND}_flows.csv"
docker compose down
echo "== label (honeypots=$HP_IPS) =="
"$PY" tools/label.py --flows "data/realism_${COND}_flows.csv" \
  --ground-truth "$GT/benign.jsonl" "$GT/attacker.jsonl" \
  --honeypots "$HP_IPS" --out "data/realism_${COND}_labelled.csv"
# The experiment steps run from the repo root (that is where the `experiments`
# package lives); paths are repo-relative there.
LAB_CSV="lab/data/realism_${COND}_labelled.csv"
R="results/phaseB/realism/${COND}"
cd "$REPO"
echo "== build loop cache + B.1 =="
"$PY" -m experiments.phaseB_build_lab --labelled "$LAB_CSV" \
  --out "data/loop/lab_${COND}.npz" --primary-strategy replay
cp "data/loop/lab_${COND}.npz" "data/loop/lab.npz"
"$PY" -m experiments.phaseB_fidelity --labelled "$LAB_CSV" \
  --npz "data/loop/lab_${COND}.npz" --out "results/phaseB/b1_fidelity_${COND}.csv"
echo "== B.2 loop (a1/a1truth/junk/control + sharecap) =="
"$PY" -m experiments.phase0_loop --dataset lab --a1-replay --val-nn-tau 0.1 \
  --scenarios control a1 a1truth --models rf xgboost --ratios 0.2 0.5 --seeds 15 --workers 2 --out "$R"
"$PY" -m experiments.phase0_loop --dataset lab --val-nn-tau 0.1 \
  --scenarios junk --jitters 0.0 --models rf xgboost --ratios 0.2 0.5 --seeds 15 --workers 2 --out "$R"
"$PY" -m experiments.phase0_loop --dataset lab --a1-replay --val-nn-tau 0.1 \
  --scenarios control a1 --defense sharecap --share-cap 0.05 --models rf xgboost \
  --ratios 0.2 0.5 --seeds 15 --workers 2 --out "${R}_sharecap"
echo "REALISM_${COND}_DONE"
