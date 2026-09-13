# Backend Dockerfile - Ubuntu base
# NOTE: This Dockerfile expects to be built from the repo ROOT directory, not backend/
# Build with: docker build -f backend/Dockerfile .
# (docker compose build passes the ARGs below through from .env; see docker-compose.yml)
ARG UBUNTU_VERSION=24.04
FROM ubuntu:${UBUNTU_VERSION}

# Build-time tunables. Defaults preserve the previously hardcoded values.
# UID is deliberately NOT wired through docker-compose.yml interpolation because
# most shells predefine a readonly UID that would silently override the default.
ARG UID=1100
ARG ITHACA_MODEL_BASE_URL=https://storage.googleapis.com/ithaca-resources/models
ARG BACKEND_CPUS_LIMIT=5
ARG BACKEND_PORT=8000

# Environment variables for Python and debian non-interactive mode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Runtime default for the uvicorn port (overridable with `docker run -e` or the
# compose env_file). Kept in sync with the build ARG so a custom --build-arg
# BACKEND_PORT still produces a consistent image.
ENV BACKEND_PORT=${BACKEND_PORT}

# Create a non-root user for security, app directory and models directory,
# and ensure correct ownership.
RUN useradd -m -u ${UID} helios && \
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

RUN curl -fSL -o /app/assets/inscriptions/models/ithaca_153143996_2.pkl \
    ${ITHACA_MODEL_BASE_URL}/ithaca_153143996_2.pkl && \
    curl -fSL -o /app/assets/inscriptions/iphi.json \
    ${ITHACA_MODEL_BASE_URL}/iphi.json && \
    curl -fSL -o /app/assets/inscriptions/models/iphi_emb_xid153143996.pkl \
    ${ITHACA_MODEL_BASE_URL}/iphi_emb_xid153143996.pkl && \
    curl -fSL -o /app/assets/inscriptions/models/aeneas_117149994_2.pkl \
    ${ITHACA_MODEL_BASE_URL}/aeneas_117149994_2.pkl && \
    curl -fSL -o /app/assets/inscriptions/led.json \
    ${ITHACA_MODEL_BASE_URL}/led.json && \
    curl -fSL -o /app/assets/inscriptions/models/led_emb_xid117149994.pkl \
    ${ITHACA_MODEL_BASE_URL}/led_emb_xid117149994.pkl && \
    chown -R helios:helios /app/assets/inscriptions

# Thread-pool sizing for CPU inference. JAX/XLA and OpenBLAS each default to
# sizing a pool to the host core count and then oversubscribe each other, which
# costs more than it gains. Keep these in sync with the CPU limit set on the
# backend service in docker-compose.yml (via the BACKEND_CPUS_LIMIT build arg).
# Declared after the model download layer so changing them does not invalidate
# that ~2GB cached layer.
#
# The deploy host has 6 processors. One is left to postgres/ollama/caddy rather
# than pinning all six here, since a saturated inference pool would otherwise
# contend with the database serving the same request.
ENV OMP_NUM_THREADS=${BACKEND_CPUS_LIMIT} \
    OPENBLAS_NUM_THREADS=${BACKEND_CPUS_LIMIT} \
    MKL_NUM_THREADS=${BACKEND_CPUS_LIMIT} \
    XLA_FLAGS="--xla_cpu_multi_thread_eigen=true"

# Persistent XLA compilation cache, so a container restart does not re-pay
# compilation of the Ithaca forward pass.
RUN mkdir -p /app/.cache/jax && chown -R helios:helios /app/.cache

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

# Expose the port the application will run on (metadata only; publishing is
# controlled by the compose ports mapping).
EXPOSE ${BACKEND_PORT}

# Shell form so the uvicorn port and trusted-proxy setting resolve at RUNTIME
# from the container environment (compose env_file), not at build time.
# `exec` preserves PID 1 so SIGTERM reaches uvicorn directly.
CMD ["sh", "-c", "exec uv run uvicorn main:app --host 0.0.0.0 --port \"${BACKEND_PORT:-8000}\" --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-*}\""]
