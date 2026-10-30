#!/usr/bin/env bash
# Phase B.5 (DECISIONS §34): high-interaction honeypot, but the attacker's benign
# traffic comes from an INDEPENDENT generator (different paths + timing, ATTACKER_INDEP=1)
# than the defender's. Condition label H5. replay + profile strategies (no oracle).
set -uo pipefail
cd "$(dirname "$0")/.."                 # lab/
REPO=$(cd .. && pwd); PY="$REPO/.venv/Scripts/python.exe"
LD="$(pwd -W)/data"; GT=data/logs/ground_truth
export MSYS_NO_PATHCONV=1 HTTP_HONEYPOT=172.28.0.22 SSH_HONEYPOT=172.28.0.23 SSH_HONEYPOT_PORT=22
HP_IPS="172.28.0.22,172.28.0.23"
SVCS="prod-web prod-ssh http-honeypot-hi ssh-honeypot-hi benign-client attacker capture"
BENIGN_SECONDS=${BENIGN_SECONDS:-400}; MIMIC_SECONDS=${MIMIC_SECONDS:-200}
COND=H5
echo "== B.5 condition $COND (independent attacker benign) =="
rm -f data/pcap/*.pcap "$GT"/*.jsonl 2>/dev/null || true
mkdir -p data/pcap "$GT" data/profiles
ROTATE_SECONDS=30 BENIGN_WORKERS=6 BENIGN_DENSE=1 docker compose up -d $SVCS
sleep 12
echo "== dense benign (defender, UNCHANGED) ${BENIGN_SECONDS}s =="; sleep "$BENIGN_SECONDS"
echo "== attacker's OWN independent benign browse =="
docker compose exec -T -e ATTACKER_INDEP=1 attacker python /app/attack.py benign --seconds 120
"$PY" tools/learn_profile.py --ground-truth "$GT/attacker.jsonl" --out data/profiles/profile_attacker.json
echo "== mimic: replay (indep) + profile (from attacker's own indep benign) =="
docker compose exec -T -e ATTACKER_INDEP=1 attacker python /app/attack.py replay --seconds "$MIMIC_SECONDS"
docker compose exec -T -e ATTACKER_INDEP=1 attacker python /app/attack.py mimic --seconds "$MIMIC_SECONDS" \
  --profile /profiles/profile_attacker.json --tag mimic_profile
echo "== scaled attacks =="
docker compose exec -T attacker python /app/attack.py portscan --host 172.28.0.22 --ports 1-1000 || true
docker compose exec -T attacker python /app/attack.py portscan --host 172.28.0.10 --ports 1-1000 || true
docker compose exec -T attacker python /app/attack.py ssh-guess --target honeypot --attempts 300 --delay 0.2 || true
docker compose exec -T attacker python /app/attack.py ssh-guess --target prod --attempts 300 --delay 0.2 || true
docker compose exec -T attacker python /app/attack.py webprobe --host 172.28.0.22 --count 120 --delay 0.1 || true
docker compose exec -T attacker python /app/attack.py webprobe --host 172.28.0.10 --count 120 --delay 0.1 || true
docker compose stop capture benign-client
echo "== extract rotated pcaps (fresh JVM each) =="
STAGE=data/b5_stage; OUT=data/b5_out; rm -rf "$STAGE" "$OUT"; mkdir -p "$STAGE" "$OUT"
for pc in data/pcap/*.pcap; do
  [ -s "$pc" ] || continue
  rm -f "$STAGE"/*.pcap; cp "$pc" "$STAGE/"
  docker run --rm --network none -v "${LD}:/tmp/pcap" dloop-cicflowmeter:4dd5319 /tmp/pcap/b5_stage /tmp/pcap/b5_out >/dev/null 2>&1 || true
done
rm -rf "$STAGE"
awk 'FNR==1 && seen{next} {print} FNR==1{seen=1}' "$OUT"/*_Flow.csv > "data/realism_${COND}_flows.csv"
docker compose down
# Free the ballooned Docker VM before the pure-Python build/B.1/B.2 (they need no
# Docker). This gives the loop workers full memory and prevents OOM-kills/orphans.
wsl --shutdown || true
sleep 6
echo "== label (honeypots=$HP_IPS) =="
"$PY" tools/label.py --flows "data/realism_${COND}_flows.csv" \
  --ground-truth "$GT/benign.jsonl" "$GT/attacker.jsonl" --honeypots "$HP_IPS" \
  --out "data/realism_${COND}_labelled.csv"
LAB_CSV="lab/data/realism_${COND}_labelled.csv"
cd "$REPO"
echo "== build + B.1 =="
"$PY" -m experiments.phaseB_build_lab --labelled "$LAB_CSV" --out "data/loop/lab_${COND}.npz" --primary-strategy replay
cp "data/loop/lab_${COND}.npz" "data/loop/lab.npz"
"$PY" -m experiments.phaseB_fidelity --labelled "$LAB_CSV" --npz "data/loop/lab_${COND}.npz" --out "results/phaseB/b1_fidelity_${COND}.csv"
R="results/phaseB/realism/$("$PY" -c "from experiments.phaseB_jobs import run_dir; print(run_dir('','${COND}','data/loop/lab.npz').name)")"
RS="results/phaseB/realism/$("$PY" -c "from experiments.phaseB_jobs import run_dir; print(run_dir('','${COND}_sharecap','data/loop/lab.npz').name)")"
echo "== B.2 (a1/a1truth/junk/control + sharecap), workers 2, one loop at a time =="
"$PY" -m experiments.phase0_loop --dataset lab --a1-replay --val-nn-tau 0.1 --scenarios control a1 a1truth --models rf xgboost --ratios 0.2 0.5 --seeds 15 --workers 2 --out "$R"
"$PY" -m experiments.phase0_loop --dataset lab --val-nn-tau 0.1 --scenarios junk --jitters 0.0 --models rf xgboost --ratios 0.2 0.5 --seeds 15 --workers 2 --out "$R"
"$PY" -m experiments.phase0_loop --dataset lab --a1-replay --val-nn-tau 0.1 --scenarios control a1 --defense sharecap --share-cap 0.05 --models rf xgboost --ratios 0.2 0.5 --seeds 15 --workers 2 --out "$RS"
echo "B5_DONE  R=$R  RS=$RS"
