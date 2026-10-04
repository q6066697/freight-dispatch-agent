# Freight Dispatch Agent — slim, non-root image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LLM_PROVIDER=mock \
    FREIGHT_DB_PATH=/app/data/freight.db

WORKDIR /app

# Copy project metadata + source, then install (editable-free, runtime deps only).
COPY pyproject.toml README.md ./
COPY app ./app
COPY db ./db
COPY eval ./eval

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Build the synthetic DB at image build time.
RUN python -m db.seed

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
