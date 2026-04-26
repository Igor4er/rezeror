# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.14-alpine AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md main.py ./
COPY src ./src

ARG RAILWAY_SERVICE_ID

RUN --mount=type=cache,id=s/${RAILWAY_SERVICE_ID}/root/.cache/uv,target=/root/.cache/uv \
    uv sync --frozen --no-dev
RUN --mount=type=cache,id=s/${RAILWAY_SERVICE_ID}/root/.cache/uv,target=/root/.cache/uv \
    uv pip install --python /app/.venv/bin/python gunicorn==23.0.0


FROM python:3.14-alpine AS runtime

ARG APP_UID=1000
ARG APP_GID=1000

RUN apk add --no-cache wget

RUN addgroup -g ${APP_GID} app \
    && adduser -u ${APP_UID} -G app -h /home/app -D app \
    && mkdir -p /data /app \
    && chown -R app:app /data /app /home/app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/main.py /app/main.py

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q -T 3 -O /dev/null http://127.0.0.1:8080/healthz || exit 1

CMD ["/app/.venv/bin/gunicorn", "--pythonpath", "/app/src", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "--timeout", "60", "rezeror.web.wsgi:app"]
