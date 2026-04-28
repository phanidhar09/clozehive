FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY packing/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY shared /app/shared
COPY packing /app/packing
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser && chown -R appuser:appgroup /app
USER appuser
WORKDIR /app/packing
EXPOSE 8013
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',8013)); s.close()"
CMD ["python", "server.py"]
