# Stage 1: builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools only in builder stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install using prebuilt wheels when possible
COPY requirements.txt .
COPY ./data/btc_usdt_features.csv /app/data/btc_usdt_features.csv

RUN pip install --no-cache-dir --prefer-binary --prefix=/install -r requirements.txt \
    && rm -rf /root/.cache/pip

# Stage 2: runtime
FROM python:3.11-slim

WORKDIR /app

# Environment hygiene
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create runtime directories and clean up pyc/test files
RUN mkdir -p /app/backups /app/state /app/logs /app/config \
    && chmod +x /app/docker/healthcheck.sh \
    && find /usr/local/lib/python3.11 -name '*.pyc' -delete \
    && rm -rf /usr/local/lib/python3.11/site-packages/*/tests

# Non-root user
ARG UID=1000
ARG GID=1000
RUN groupadd -g $GID trader || true && \
    useradd -m -u $UID -g $GID trader || true && \
    chown -R $UID:$GID /app/backups /app/state /app/logs /app/config
USER trader

# Healthcheck
COPY docker/healthcheck.sh /app/docker/healthcheck.sh
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD /app/docker/healthcheck.sh


# Default command
CMD ["python", "-m", "src.app.trading_bot"]