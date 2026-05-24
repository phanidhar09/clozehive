FROM python:3.12.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_NO_CACHE=1

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:0.7.3 /uv /usr/local/bin/uv
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# ── Runtime ───────────────────────────────────────────────────────────────────
COPY . .

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN mkdir -p /app/uploads /home/appuser/.u2net && chown -R appuser:appgroup /app /home/appuser/.u2net
USER appuser

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/live')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
