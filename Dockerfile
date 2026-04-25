# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md main.py ./
COPY src ./src

RUN uv sync --frozen --no-dev
RUN uv pip install --python /app/.venv/bin/python --no-cache-dir gunicorn==23.0.0


FROM python:3.14-slim-bookworm AS runtime

RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /data /app \
    && chown -R app:app /data /app /home/app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/main.py /app/main.py

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/library', timeout=3); sys.exit(0)"

CMD ["/app/.venv/bin/gunicorn", "--pythonpath", "/app/src", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "60", "rezeror.web.wsgi:app"]
