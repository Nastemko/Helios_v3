# Backend Dockerfile - Ubuntu base
FROM ubuntu:24.04

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 helios && \
    mkdir -p /app && \
    chown -R helios:helios /app

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY --chown=helios:helios requirements.txt .

# Install Python dependencies
RUN python3.12 -m pip install --upgrade pip && \
    python3.12 -m pip install -r requirements.txt

# Copy application code
COPY --chown=helios:helios . .

# Switch to non-root user
USER helios

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

