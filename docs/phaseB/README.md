# Phase B — packet-level lab

An end-to-end lab that answers the IJERESM rejection's main point: the Phase 0/A
poison was generated **in feature space**, never as real traffic through a live
honeypot and a flow extractor. Here the A1 "benign mimicry" adversary sends real
sessions to a real honeypot; `tcpdump` captures them; Engelen's fixed CICFlowMeter
turns the packets into flows; and the same normalisation/distance code as the
paper measures how close the mimic flows land to benign traffic.

This is **build + validation + an exploratory pilot**. Nothing here is a
confirmatory result; the pilot numbers are labelled exploratory and are not cited.

## What runs

One Docker Compose project (`lab/docker-compose.yml`) on a single `internal: true`
network `labnet` (`172.28.0.0/16`), so nothing in the lab can reach the internet
once it is up. No service publishes a port to the host.

| service | role | addr | mem_limit |
|---|---|---|---:|
| `prod-web` | nginx, small static site (several pages + assets) | .10 | 64m |
| `prod-ssh` | OpenSSH, test user `admin` | .11 | 96m |
| `cowrie` | SSH honeypot (JSON logs) | .20 | 320m |
| `http-honeypot` | Flask app serving the **same** site as prod-web, logs every request | .21 | 128m |
| `benign-client` | scripted web + SSH users, seeded, rate-configurable | .30 | 256m |
| `attacker` | mimic mode + small real attacks (allowlist-gated) | .40 | 256m |
| `capture` | tcpdump on the lab bridge, rotated pcaps | host netns | 128m |

Flow extraction (`lab/extractor`, the fixed CICFlowMeter, Docker image
`dloop-cicflowmeter:4dd5319`) runs **offline** over the pcaps — not as a
long-running service.

## Safety

- `labnet` is `internal: true`: no egress. Build needs the internet; runtime does not.
- The attacker validates every target against `TARGET_ALLOWLIST` (the lab IPs)
  in `attacker/lib/allowlist.py` before sending anything; hostnames are rejected.
- No ports are published to the host; honeypots are reachable only from inside the lab.
- Captured pcaps, extracted CSVs, honeypot logs and learned profiles live under
  `lab/data/` and are gitignored. Only lab **code** is committed.

## Start / stop / reset

```bash
cd lab
docker compose up -d --build       # start (first run builds images, pulls cowrie)
docker compose ps                  # check health
docker compose logs -f benign-client

docker compose stop                # stop, keep state + data
docker compose down                # stop and remove containers (pcaps/logs remain under data/)

# full reset: containers AND captured data
docker compose down -v
rm -rf data/pcap/* data/flows* data/logs/* data/profiles/*
```

Tunables (env or `lab/.env`): `LAB_SEED` (default 1), `BENIGN_RATE` (default 1.0),
`ROTATE_SECONDS` (pcap rotation, default 60).

## Run the exploratory pilot

```bash
bash lab/tools/run_pilot.sh        # up -> warmup -> learn profile -> mimic+attacks -> extract -> label -> measure
```

Or step by step: `learn_profile.py` builds the benign profile from the captured
benign ground truth; `attack.py mimic` replays it at the HTTP honeypot;
`attack.py {portscan,ssh-guess,webprobe}` run the small real attacks; the extractor
turns `data/pcap/*.pcap` into flows; `label.py` joins flows to ground truth
(emitting both the loop's policy label and the true intent); `pilot_measure.py`
reports NN distance, twin fraction and cost.

## Extractor validation (step 3)

`lab/tools/validate_extractor.py` compares this lab's extraction of a CICIDS2017
raw-pcap slice against the matching rows of Engelen's published reprocessed CSV
(`IDS-data/cicids2017-fixed/monday.csv`), per feature.

**Done — see [extractor-validation.md](extractor-validation.md).** The raw pcap
(manual download from the UNB CIC IDS-2017 page, registration-gated) is in
`newdata/` (gitignored). The first 30 min was sliced; a full-slice extraction OOM'd
(Java heap in the 1.86 GiB VM), so the slice was **split by host-pair** (every
5-tuple kept whole) and each piece extracted in a fresh JVM — never raising memory.
The reassembled 18,248 flows match Engelen's release at **0 s offset, 99.8 %
matched, per-feature exact ≥ 97 %**. The extractor build is confirmed correct.

## Resource use (measured)

> Docker's WSL2 VM on this machine reports **1.86 GiB** total — below the ~4 GB
> target, so the VM, not the target, is the binding ceiling. The `mem_limit`s sum
> to ~1.25 GB, which fits.

Measured with `docker stats --no-stream` during the pilot (mimic + benign load):

| service | mem (peak observed) | limit |
|---|---:|---:|
| cowrie | ~82 MiB | 320m |
| http-honeypot | ~33 MiB | 128m |
| attacker (active) | ~26 MiB | 256m |
| benign-client | ~25 MiB | 256m |
| prod-web / prod-ssh / capture | ~3 MiB each | 64–128m |
| **total** | **~174 MiB (~9% of the VM)** | ~1.25 GB |

CPU stayed under 1% per container — the lab is a trickle generator, not a load
test. The offline extractor runs separately: ~250 MB image, a few seconds per
60-second pcap, single-threaded.

## Known limitations

- **Timezone / clock.** The extractor writes flow-start timestamps as naive local
  time; ground truth is epoch (UTC). `label.py` treats the extractor time as UTC,
  so a non-UTC host needs the offset applied, or the join window (`MATCH_SLACK_S`)
  widened. The pilot runs on one host so the offset is constant.
- **Bridge capture under Docker Desktop.** The docker bridge lives in the WSL2 VM;
  `capture` sniffs it from the host network namespace and filters to the lab
  subnet. A learning bridge still delivers all lab unicast to the namespace, so
  capture is complete, but this is a Docker-Desktop-specific arrangement.
- **CICFlowMeter flow assembly.** TCP flows split on timeout and the appendix-flow
  behaviour both create extra short flows; retransmissions and MTU effects shift
  byte/packet counts. These are properties of the extractor, recorded, not tuned.
- Cowrie sessions are SSH-honeypot telemetry, **not** CICFlowMeter flows, and do
  not feed the model — consistent with the project's demo design (CLAUDE.md).
