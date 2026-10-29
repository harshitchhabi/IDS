# HTTP honeypot: serves the SAME static site as prod-web, logs every request as
# one JSON line. Lab-internal; no egress. Pinned deps for reproducibility.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "flask==3.0.3" "gunicorn==23.0.0"
COPY app/ /app/
ENV SITE_DIR=/site HP_LOG=/var/log/hp/http_honeypot.jsonl
RUN mkdir -p /var/log/hp
EXPOSE 80
# Single worker, few threads: it only ever serves a trickle of lab traffic.
CMD ["gunicorn","-b","0.0.0.0:80","-w","1","--threads","4","app:app"]
