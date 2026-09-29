FROM python:3.11-slim

WORKDIR /app

# build-essential: some deps (chromadb/sentence-transformers/scikit-learn) pull in
# packages without prebuilt wheels for every platform.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# No --reload in production: uvicorn's file-watcher reloader is dev-only tooling
# and has no reason to run in a container that gets redeployed on every push.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
