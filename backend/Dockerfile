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

RUN curl -fSL -o /app/assets/inscriptions/models/ithaca_153143996_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/ithaca_153143996_2.pkl && \
    curl -fSL -o /app/assets/inscriptions/iphi.json \
    https://storage.googleapis.com/ithaca-resources/models/iphi.json && \
    curl -fSL -o /app/assets/inscriptions/models/iphi_emb_xid153143996.pkl \
    https://storage.googleapis.com/ithaca-resources/models/iphi_emb_xid153143996.pkl && \
    curl -fSL -o /app/assets/inscriptions/models/aeneas_117149994_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/aeneas_117149994_2.pkl && \
    curl -fSL -o /app/assets/inscriptions/led.json \
    https://storage.googleapis.com/ithaca-resources/models/led.json && \
    curl -fSL -o /app/assets/inscriptions/models/led_emb_xid117149994.pkl \
    https://storage.googleapis.com/ithaca-resources/models/led_emb_xid117149994.pkl && \
    chown -R helios:helios /app/assets/inscriptions

# Thread-pool sizing for CPU inference. JAX/XLA and OpenBLAS each default to
# sizing a pool to the host core count and then oversubscribe each other, which
# on a 4-core box costs more than it gains. Keep these in sync with the CPU
# limit set on the backend service in docker-compose.yml.
# Declared after the model download layer so changing them does not invalidate
# that ~2GB cached layer.
ENV OMP_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
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

# Expose the port the application will run on
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
