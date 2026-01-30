# Backend Dockerfile - Ubuntu base
# NOTE: This Dockerfile expects to be built from the repo ROOT directory, not backend/
# Build with: docker build -f backend/Dockerfile .
FROM ubuntu:24.04

# Environment variables for Python and debian non-interactive mode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install required system packages (including libs for JAX / numerical libs),
# install `uv` (the package manager used in this repo), and clean apt cache.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    build-essential \
    libgomp1 \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Create a non-root user for security, app directory and models directory,
# and ensure correct ownership.
RUN useradd -m -u 1100 helios && \
    mkdir -p /app /app/models /app/data/canonical-greekLit && \
    chown -R helios:helios /app

# Optionally download Aeneas / Ithaca model files into /app/models at build time.
# Use: docker build --build-arg DOWNLOAD_AENEAS_MODELS=true -f backend/Dockerfile .
RUN curl -fSL -o /app/models/ithaca_153143996_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/ithaca_153143996_2.pkl && \
    curl -fSL -o /app/models/iphi.json \
    https://storage.googleapis.com/ithaca-resources/models/iphi.json && \
    curl -fSL -o /app/models/iphi_emb_xid153143996.pkl \
    https://storage.googleapis.com/ithaca-resources/models/iphi_emb_xid153143996.pkl && \
    chown -R helios:helios /app/models

# Set the working directory for subsequent commands
WORKDIR /app

# Switch to the non-root user to run the application
USER helios

# Copy dependency definition files first to leverage Docker's layer caching.
# This layer is only rebuilt when pyproject.toml or uv.lock change.
COPY --chown=helios:helios ./pyproject.toml ./uv.lock ./

# Install Python dependencies using uv.
RUN uv sync

# Copy the rest of the application source code into the container
COPY --chown=helios:helios ./src .

# Copy the Greek text data files (Perseus canonical Greek XML)
# Keep these under /app/data so the application can find them.
COPY --chown=helios:helios ./canonical-greekLit /app/data/canonical-greekLit

# Expose the port the application will run on
EXPOSE 8000

# Add a health check to ensure the application is running correctly
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
