# --- Builder Stage ---
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# --- MODIFIED: Added libgomp1 for trimesh/numpy dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# --- Final Stage ---
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# --- MODIFIED: Added libgomp1 for trimesh/numpy dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    fonts-dejavu-core \
    gosu \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1000 app && adduser --system --uid 1000 --ingroup app --home /home/app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY . .

ENV PATH="/opt/venv/bin:$PATH"

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

RUN mkdir -p /app/media /app/staticfiles /app/scans/outputs \
    && chown -R app:app /app

USER app

EXPOSE 8000
CMD ["/app/docker-entrypoint.sh", "web"]