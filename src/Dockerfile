FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Shanghai

RUN pip install --no-cache-dir \
    aliyun-python-sdk-core \
    aliyun-python-sdk-ecs \
    huaweicloudsdkcore \
    huaweicloudsdkvpc \
    pyyaml

COPY ip_sync.py /app/ip_sync.py
COPY ip_sync_app /app/ip_sync_app
COPY run_with_daily_log.sh /app/run_with_daily_log.sh

RUN chmod +x /app/run_with_daily_log.sh

ENTRYPOINT ["/app/run_with_daily_log.sh"]
