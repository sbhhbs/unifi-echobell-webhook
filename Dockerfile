# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.14
ARG POETRY_VERSION=2.2.1

FROM python:${PYTHON_VERSION}-alpine AS builder
ARG POETRY_VERSION
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry-cache
WORKDIR /app
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root && rm -rf "$POETRY_CACHE_DIR"

FROM python:${PYTHON_VERSION}-alpine AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DB_PATH=/data/unifi-webhook.sqlite3
WORKDIR /app
RUN addgroup -S webhook && adduser -S -G webhook webhook && mkdir /data && chown webhook:webhook /data
COPY --from=builder /app/.venv /app/.venv
COPY --chown=webhook:webhook unifi_webhook ./unifi_webhook
USER webhook
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health', timeout=2).read()"
ENTRYPOINT ["python", "-m", "unifi_webhook"]
