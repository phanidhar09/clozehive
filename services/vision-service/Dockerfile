FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────────────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Pre-download rembg U2Net model so first upload doesn't stall ─────────────
FROM deps AS model-warmup
# Ensure the directory always exists so the COPY below never fails,
# even when rembg model download fails (network unavailable, etc.).
RUN mkdir -p /root/.u2net && \
    python -c "import rembg; rembg.remove(b'x')" 2>/dev/null || true

# ── Runtime ───────────────────────────────────────────────────────────────────
FROM deps AS runtime
COPY . .

# Copy the pre-downloaded ONNX model cache from the warmup stage
COPY --from=model-warmup /root/.u2net /root/.u2net

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN mkdir -p /app/uploads && chown -R appuser:appgroup /app \
    && cp -r /root/.u2net /home/appuser/.u2net 2>/dev/null || true \
    && chown -R appuser:appgroup /home/appuser/.u2net 2>/dev/null || true
USER appuser

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/live')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
