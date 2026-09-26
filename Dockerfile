FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/MikeDuignan/galway-bank" \
      org.opencontainers.image.title="Galway Mutual teaching lab" \
      org.opencontainers.image.description="Deliberately vulnerable fictional banking app for local CSSP teaching labs" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=app:create_app \
    GALWAY_BANK_DB=/var/lib/galway-bank/bank.db

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 1000 galway

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY seed ./seed
COPY tools ./tools

RUN pip install --no-cache-dir .

RUN mkdir -p /var/lib/galway-bank && chown -R galway:galway /var/lib/galway-bank /app

USER galway

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:5000/health || exit 1

CMD ["sh", "-c", "python tools/reset_db.py --if-empty && python -m flask --app app:create_app run --host=0.0.0.0 --port=5000"]
