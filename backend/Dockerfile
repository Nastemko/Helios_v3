# Backend Dockerfile - Ubuntu base
# NOTE: This Dockerfile expects to be built from the repo ROOT directory, not backend/
# Build with: docker build -f backend/Dockerfile .
FROM ubuntu:24.04

# Environment variables for Python and debian non-interactive mode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Create a non-root user for security, app directory and models directory,
# and ensure correct ownership.
RUN useradd -m -u 1100 helios && \
    mkdir -p /app /app/assets/inscriptions/models /app/assets/canonical-greekLit && \
    chown -R helios:helios /app

# Copy the Greek text data files (Perseus canonical Greek XML)
# Keep these under /app/assets so the application can find them.
COPY --chown=helios:helios ./assets/canonical-greekLit /app/assets/canonical-greekLit

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

# The Ithaca/Aeneas checkpoints (~2GB) and the JAX/OpenBLAS thread-pool tuning
# that used to live here are gone: inference moved to ithaca-service/, which
# owns the model files and its own accelerator-specific configuration. This
# image no longer imports JAX at all.
#
# `iphi.json` is still read at startup by the PHI inscription populator, but it
# is supplied through INSCRIPTIONS_DIR (a volume in compose), not baked in.

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

# Expose the port the application will run on
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
