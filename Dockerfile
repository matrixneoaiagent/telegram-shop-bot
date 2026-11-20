FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/data/shop.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 shopbot \
    && mkdir -p /data \
    && chown -R shopbot:shopbot /app /data
USER shopbot

VOLUME ["/data"]

CMD ["python", "-m", "bot"]
