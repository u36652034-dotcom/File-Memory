FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY filememory ./filememory
COPY README.md .env.example ./

# The core is a library today; this smoke command initializes its local store.
CMD ["python", "-c", "from filememory.db import Database; Database('/data/filememory.sqlite3'); print('filememory ready')"]
