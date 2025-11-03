# Helios Docker Deployment Guide

This guide covers deploying Helios using Docker and Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 8GB+ RAM (for Ollama with Llama 3.2 8B)
- 100GB+ storage

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/yourusername/Helios_v3.git
cd Helios_v3

# Copy environment template
cp .env.example .env

# Edit .env with your values
nano .env
```

**Important environment variables:**
- `POSTGRES_PASSWORD` - Set a secure password
- `SECRET_KEY` - Generate with: `openssl rand -hex 32`
- `CORS_ORIGINS` - Add your domain(s)

### 2. Pull Ollama Models (First Time Setup)

The Ollama container needs to download models (~5GB total):

```bash
# Start only Ollama first
docker-compose up -d ollama

# Wait for Ollama to be ready
docker-compose exec ollama ollama pull llama3.2:8b
docker-compose exec ollama ollama pull nomic-embed-text

# Verify models are installed
docker-compose exec ollama ollama list
```

### 3. Start All Services

```bash
# Start all containers
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. Initialize Database

```bash
# Run Alembic migrations
docker-compose exec backend alembic upgrade head

# (Optional) Populate with sample texts
docker-compose exec backend python scripts/populate_texts.py
```

### 5. Generate Embeddings (for RAG)

```bash
# Generate embeddings for all texts (runs once, takes ~2 minutes)
docker-compose exec backend python scripts/generate_embeddings.py --batch-size 100
```

### 6. Access the Application

- **Frontend**: http://localhost
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
│                                                          │
│  ┌──────────────┐      ┌──────────────┐                │
│  │   Frontend   │      │   Backend    │                │
│  │  (nginx:80)  │◄────►│ (FastAPI)    │                │
│  └──────────────┘      └───────┬──────┘                │
│                                 │                        │
│         ┌───────────────────────┼────────────┐          │
│         ▼                       ▼            ▼          │
│  ┌─────────────┐      ┌──────────────┐  ┌────────┐    │
│  │  PostgreSQL │      │    Ollama    │  │ Logs   │    │
│  │  + pgvector │      │  Llama 3.2   │  │ Volume │    │
│  └─────────────┘      └──────────────┘  └────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Development vs Production

### Development Mode

```bash
# Use docker-compose with live reloading
docker-compose -f docker-compose.dev.yml up

# Backend hot-reloads on code changes
# Frontend uses Vite dev server (port 5173)
```

### Production Mode

```bash
# Build optimized images
docker-compose build --no-cache

# Start with production settings
docker-compose up -d

# Use Caddy for HTTPS (see VPS_SETUP_PHASE1.md)
```

## Common Commands

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f postgres
docker-compose logs -f ollama
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart backend
```

### Execute Commands in Containers

```bash
# Backend shell
docker-compose exec backend bash

# Database shell
docker-compose exec postgres psql -U heliosuser -d helios

# Check Ollama models
docker-compose exec ollama ollama list
```

### Backup Database

```bash
# Backup to file
docker-compose exec postgres pg_dump -U heliosuser helios > backup_$(date +%Y%m%d).sql

# Restore from backup
docker-compose exec -T postgres psql -U heliosuser helios < backup_20250103.sql
```

### Stop and Clean Up

```bash
# Stop all containers
docker-compose down

# Stop and remove volumes (WARNING: deletes data!)
docker-compose down -v

# Remove all images
docker-compose down --rmi all
```

## Monitoring

### Check Resource Usage

```bash
# All containers
docker stats

# Specific container
docker stats helios-backend
```

### Health Checks

```bash
# Check all container health
docker-compose ps

# Manual health checks
curl http://localhost/health          # Frontend
curl http://localhost:8000/health     # Backend
docker-compose exec postgres pg_isready -U heliosuser  # Database
```

## Troubleshooting

### Backend won't start

```bash
# Check logs
docker-compose logs backend

# Common issues:
# 1. Database not ready - wait for postgres healthcheck
# 2. Missing migrations - run: docker-compose exec backend alembic upgrade head
# 3. Ollama not accessible - check: docker-compose exec backend curl http://ollama:11434
```

### Ollama out of memory

```bash
# Check memory usage
docker stats helios-ollama

# Solution: Add swap space on host
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### PostgreSQL connection errors

```bash
# Check postgres is running
docker-compose exec postgres pg_isready -U heliosuser

# Check DATABASE_URL in .env matches docker-compose.yml
# Should be: postgresql://heliosuser:password@postgres:5432/helios
```

### Port conflicts

```bash
# Check what's using ports
sudo lsof -i :80    # Frontend
sudo lsof -i :8000  # Backend
sudo lsof -i :5432  # PostgreSQL

# Change ports in docker-compose.yml if needed
```

## VPS Deployment

For deploying to a VPS (Contabo, DigitalOcean, etc.):

1. **Install Docker on VPS**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

2. **Clone repository**
```bash
git clone https://github.com/yourusername/Helios_v3.git
cd Helios_v3
```

3. **Configure .env for production**
```bash
cp .env.example .env
nano .env
# Set secure passwords, SECRET_KEY, and production CORS_ORIGINS
```

4. **Follow Quick Start steps above**

5. **Setup Caddy for HTTPS** (see `docs/VPS_SETUP_PHASE1.md`)

## Performance Tuning

### Optimize Ollama

```bash
# In docker-compose.yml, adjust:
# - OLLAMA_NUM_THREADS (default: auto)
# - OLLAMA_NUM_GPU (if GPU available)
```

### Scale Backend Workers

```bash
# In backend/Dockerfile, adjust:
CMD ["uvicorn", "main:app", "--workers", "4"]  # Increase for more CPU cores
```

### PostgreSQL Tuning

```bash
# Add to postgres service in docker-compose.yml:
command: postgres -c shared_buffers=256MB -c max_connections=100
```

## Security Checklist

- [ ] Change default `POSTGRES_PASSWORD`
- [ ] Generate new `SECRET_KEY`
- [ ] Set `DEBUG=False` in production
- [ ] Update `CORS_ORIGINS` to your domain only
- [ ] Use Caddy/nginx with HTTPS in production
- [ ] Enable firewall (ufw) on VPS
- [ ] Regular database backups
- [ ] Keep Docker images updated

## Next Steps

- See `docs/VPS_SETUP_PHASE1.md` for full VPS setup
- See `PLAN_B_REVISED.md` for RAG implementation details
- See `docs/PHASE1_TESTING.md` for testing procedures

## Support

For issues, check:
1. `docker-compose logs` for error messages
2. GitHub issues
3. Documentation in `/docs` directory

