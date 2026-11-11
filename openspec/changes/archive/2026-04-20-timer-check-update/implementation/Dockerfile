FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai

RUN pip install --no-cache-dir aliyun-python-sdk-core aliyun-python-sdk-ecs

COPY src/ip_sync.py /app/src/ip_sync.py
COPY src/run_with_daily_log.sh /app/src/run_with_daily_log.sh

RUN chmod +x /app/src/run_with_daily_log.sh

ENTRYPOINT ["/app/src/run_with_daily_log.sh"]
CMD ["--once"]
