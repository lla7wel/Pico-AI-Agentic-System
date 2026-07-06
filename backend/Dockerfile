FROM python:3.12-slim

# Keep Python lean and unbuffered so logs stream to Fly.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fly routes public 443 -> this internal port (see fly.toml).
EXPOSE 8080

# One worker: the SQLite store, in-memory sessions, presence, and settings
# cache all assume a single process. Scale by partitioning if ever needed.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
