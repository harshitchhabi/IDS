# Adversary container. Two modes: (a) mimic — real benign-shaped sessions aimed at
# the honeypots, to exercise the A1 poisoning channel end-to-end; (b) a few small,
# standard, SEEDED attacks (slow SSH guessing, a TCP connect scan, canned SQLi/XSS
# HTTP probes) against lab targets only. Every routine is gated by an allowlist.
# Lab-internal; the network is internal:true so nothing here can reach outside.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends nmap \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "requests==2.32.3" "paramiko==3.4.1"
COPY lib/ /app/lib/
COPY attack.py /app/attack.py
ENV PYTHONUNBUFFERED=1
