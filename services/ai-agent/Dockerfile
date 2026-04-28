FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

FROM deps AS runtime
COPY . .

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8001/health').raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips=*"]
