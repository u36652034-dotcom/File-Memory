FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FILE_MEMORY_HOST=0.0.0.0 \
    FILE_MEMORY_DATABASE=/data/filememory.sqlite3
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY filememory ./filememory
COPY web ./web
COPY README.md .env.example ./

EXPOSE 8765
CMD ["python", "-m", "filememory.web"]
