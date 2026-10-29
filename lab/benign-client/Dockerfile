FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "requests==2.32.3" "paramiko==3.4.1"
COPY lib/ /app/lib/
COPY client.py /app/client.py
ENV PYTHONUNBUFFERED=1
CMD ["python","/app/client.py"]
