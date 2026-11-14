# TrueLift service and page in one small image.
#   docker build -t truelift .        (or: python tasks.py docker / docker compose up)
#   docker run --rm -p 8000:8000 truelift      -> http://localhost:8000
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pinned versions, exported from uv.lock (the same ones the committed numbers were produced with).
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY truelift/ truelift/
COPY scripts/ scripts/
COPY data/processed/ data/processed/
COPY reports/ reports/

# Use the checkout's model when it has one with its checksum; otherwise train it here (about six
# minutes; reports go to a scratch folder so the committed ones stay as they are). Then build the
# serving cache once, so the container starts in seconds and never needs to write it.
RUN if [ ! -f data/processed/model.pkl ] || [ ! -f data/processed/model.pkl.sha256 ]; then \
        python scripts/run_pipeline.py --out /tmp/pipeline-reports && rm -rf /tmp/pipeline-reports; \
    fi \
    && python -c "from truelift.api import get_state; s = get_state(); print('model', s.engine.model_version)"

RUN useradd --create-home --uid 10001 truelift && mkdir -p /data && chown truelift /data
USER truelift

# Consent ledger and exposure log persist in /data (mount a volume there to keep them).
ENV TRUELIFT_DB=/data/truelift.sqlite \
    TRUELIFT_LOG_JSON=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status != 200)"

CMD ["uvicorn", "truelift.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
