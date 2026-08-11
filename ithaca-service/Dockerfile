# Ithaca/Aeneas inference service -- CPU build.
#
# This is the local-development and fallback image. The GPU build that runs on
# Cloud Run is Dockerfile.gpu, which differs only in its base image and its JAX
# wheel; everything else here is shared deliberately, so a bug found locally is
# the same bug in production.
#
# Build from this directory (unlike backend/Dockerfile, which builds from the
# repo root):
#   docker build -t helios-ithaca:cpu ./ithaca-service
FROM ubuntu:24.04

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Same non-root user and uid as the backend image, so a bind-mounted asset
# directory has consistent ownership across both.
RUN useradd -m -u 1100 helios && \
    mkdir -p /app /app/assets/inscriptions/models && \
    chown -R helios:helios /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    libgomp1 \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Thread-pool sizing for CPU inference. JAX/XLA and OpenBLAS each default to
# sizing a pool to the host core count and then oversubscribe each other, which
# costs more than it gains. Keep in sync with the cpus limit on the ithaca
# service in docker-compose.yml.
#
# The GPU image drops this block entirely -- these values are meaningless, and
# XLA_FLAGS actively wrong, once the forward pass is not on the CPU.
ENV OMP_NUM_THREADS=5 \
    OPENBLAS_NUM_THREADS=5 \
    MKL_NUM_THREADS=5 \
    XLA_FLAGS="--xla_cpu_multi_thread_eigen=true"

# Persistent XLA compilation cache, so a container restart does not re-pay
# compilation of the forward pass.
RUN mkdir -p /app/.cache/jax && chown -R helios:helios /app/.cache

WORKDIR /app
USER helios

# Dependencies first, so this layer survives source edits.
COPY --chown=helios:helios ./pyproject.toml ./uv.lock ./
RUN uv sync

COPY --chown=helios:helios ./src .

# NOTE: no checkpoint download here. The CPU image expects the six model files
# to be mounted at INSCRIPTIONS_DIR (see docker-compose.yml), which keeps local
# rebuilds from re-fetching ~2GB. The GPU image bakes them in instead, because
# Cloud Run has nothing to mount and container streaming makes an in-image copy
# the faster option at this size.

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
