#!/bin/sh
# Sniff the lab bridge and write rotated pcaps. Runs in the host network namespace
# (where the docker bridge lives under the WSL2 backend); the BPF filter pins it to
# the lab subnet so only lab traffic is recorded. Read-only: it sends nothing.
set -eu
SUBNET="${LAB_SUBNET:-172.28.0.0/16}"
ROTATE="${ROTATE_SECONDS:-60}"
OUT=/pcap
mkdir -p "$OUT"

# Find the bridge interface that carries the lab subnet. The interface appears
# once the labnet bridge has an endpoint, so wait for it.
base="$(echo "$SUBNET" | cut -d. -f1-2)"
iface=""
for _ in $(seq 1 30); do
  iface="$(ip -o -4 addr show | awk -v b="$base" '$4 ~ ("^"b"\.") {print $2; exit}')"
  [ -n "$iface" ] && break
  echo "capture: waiting for lab bridge ($SUBNET)..." >&2
  sleep 2
done
if [ -z "$iface" ]; then
  echo "capture: lab bridge not found; capturing on any with subnet filter" >&2
  iface=any
fi
echo "capture: interface=$iface subnet=$SUBNET rotate=${ROTATE}s -> $OUT" >&2

# -G rotate seconds, -w strftime template, -n no DNS, -s0 full packets.
exec tcpdump -i "$iface" -n -s 0 -U \
  -G "$ROTATE" -w "$OUT/lab_%Y%m%d_%H%M%S.pcap" \
  "net $SUBNET"
