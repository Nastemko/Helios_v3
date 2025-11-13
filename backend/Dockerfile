# Backend Dockerfile - Ubuntu base
FROM ubuntu:24.04

# Set environment variables for Python and debian non-interactive mode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies, download and install uv in a single layer to optimize image size.
# uv is moved to a system-wide binary path to be available to all users.
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Create a non-root user for security and create the application directory
RUN useradd -m -u 1100 helios && \
    mkdir -p /app && \
    chown -R helios:helios /app

# Set the working directory for subsequent commands
WORKDIR /app

# Switch to the non-root user to run the application
USER helios

# Copy dependency definition files first to leverage Docker's layer caching.
# This layer is only rebuilt when pyproject.toml or uv.lock change.
COPY --chown=helios:helios pyproject.toml uv.lock ./

# Install Python dependencies using uv.
# This uses the system's Python interpreter, which is fine for a container.
RUN uv sync

# Copy the rest of the application source code into the container
COPY --chown=helios:helios src .

# Expose the port the application will run on
EXPOSE 8000

# Add a health check to ensure the application is running correctly
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# The command to run the application using uvicorn
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips=\"*\""]
