# Use slim Python base image
FROM python:3.11-slim

# Environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# System dependencies (only if needed for compiling Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
#RUN useradd -m trader
#USER trader

# Optional healthcheck: verifies heartbeat file exists
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD test -f /app/state/heartbeat.json || exit 1

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "src.app.trading_bot"]

ARG UID=1000
ARG GID=1000
RUN groupadd -g $GID trader || true && \
    useradd -m -u $UID -g $GID trader || true

RUN mkdir -p /app/backups /app/state /app/logs /app/config && \
    chown -R $UID:$GID /app/backups /app/state /app/logs /app/config
USER trader
