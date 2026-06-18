# Sunshine — container image for the FastAPI survey tool.
# Suited to container hosts (Render, Railway, Fly.io, plain Docker) where the
# SQLite database lives on a mounted volume for persistence.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Persist the SQLite DB on a mounted volume by default (4 slashes = abs path)
    DATABASE_URL=sqlite:////data/sunshine.db

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app
COPY scripts ./scripts

# Non-root user; give it ownership of the app and the data volume mount point.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser /app /data
USER appuser
VOLUME ["/data"]

EXPOSE 8000

# Honor $PORT when the platform provides one (Render, Railway, ...).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=3)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
