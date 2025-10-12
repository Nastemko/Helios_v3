# Helios Deployment Guide

This guide covers deploying Helios to production.

## Pre-Deployment Checklist

- [ ] Backend tests passing
- [ ] Frontend builds without errors
- [ ] Database migrations prepared
- [ ] Environment variables configured
- [ ] OAuth credentials for production domain
- [ ] SSL certificates ready
- [ ] Monitoring setup complete

## Option 1: Docker Compose (Recommended for Testing)

### 1. Create docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: helios
      POSTGRES_USER: helios
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U helios"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://helios:${DB_PASSWORD}@postgres:5432/helios
      SECRET_KEY: ${SECRET_KEY}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
      GOOGLE_REDIRECT_URI: ${GOOGLE_REDIRECT_URI}
      CORS_ORIGINS: ${CORS_ORIGINS}
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./canonical-greekLit:/app/canonical-greekLit:ro
      - ./backend/models:/app/models

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    environment:
      VITE_API_URL: ${VITE_API_URL}
    depends_on:
      - backend

volumes:
  postgres_data:
```

### 2. Create Backend Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create models directory
RUN mkdir -p models

# Expose port
EXPOSE 8000

# Run migrations and start server
CMD python scripts/populate_texts.py --limit 10 && \
    uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Create Frontend Dockerfile

```dockerfile
FROM node:18-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### 4. Frontend nginx.conf

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
}
```

### 5. Deploy

```bash
# Create .env file
cp .env.example .env
# Edit .env with production values

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Option 2: Cloud Deployment (Production)

### Backend: Railway / Render / Fly.io

#### Railway

1. Install Railway CLI:
```bash
npm install -g @railway/cli
```

2. Login and initialize:
```bash
railway login
railway init
```

3. Create PostgreSQL database:
```bash
railway add --database postgres
```

4. Set environment variables:
```bash
railway variables set SECRET_KEY=your-secret-key
railway variables set GOOGLE_CLIENT_ID=your-client-id
railway variables set GOOGLE_CLIENT_SECRET=your-secret
railway variables set GOOGLE_REDIRECT_URI=https://your-backend.railway.app/api/auth/callback/google
```

5. Deploy:
```bash
cd backend
railway up
```

#### Render

1. Create new Web Service on Render.com
2. Connect GitHub repository
3. Configure:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add PostgreSQL database
5. Set environment variables in Render dashboard
6. Deploy

### Frontend: Vercel / Netlify

#### Vercel

1. Install Vercel CLI:
```bash
npm install -g vercel
```

2. Deploy:
```bash
cd frontend
vercel
```

3. Set environment variables in Vercel dashboard:
   - `VITE_API_URL=https://your-backend.railway.app`

4. Deploy production:
```bash
vercel --prod
```

#### Netlify

1. Install Netlify CLI:
```bash
npm install -g netlify-cli
```

2. Build:
```bash
cd frontend
npm run build
```

3. Deploy:
```bash
netlify deploy --prod --dir=dist
```

4. Set environment variables in Netlify dashboard

## Post-Deployment Tasks

### 1. Database Setup

```bash
# SSH into backend server or use Railway shell

# Run migrations
alembic upgrade head

# Populate texts (start with limited set)
python scripts/populate_texts.py --limit 100
```

### 2. Download Aeneas Models (Optional)

```bash
# Greek model
curl -o models/ithaca_153143996_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/ithaca_153143996_2.pkl

curl -o models/iphi.json \
    https://storage.googleapis.com/ithaca-resources/models/iphi.json

curl -o models/iphi_emb_xid153143996.pkl \
    https://storage.googleapis.com/ithaca-resources/models/iphi_emb_xid153143996.pkl
```

Note: Models are large (~2GB). Consider cloud storage or disabling AI features for MVP.

### 3. Configure OAuth

1. Go to Google Cloud Console
2. Create OAuth 2.0 credentials
3. Add authorized redirect URIs:
   - `https://your-backend-domain.com/api/auth/callback/google`
4. Add authorized JavaScript origins:
   - `https://your-frontend-domain.com`
5. Update environment variables with new credentials

### 4. SSL/HTTPS

Most platforms (Railway, Vercel, Netlify) provide automatic SSL.

For custom domains:
- Use Let's Encrypt
- Configure via platform settings
- Update OAuth redirect URLs to use HTTPS

### 5. Monitoring

#### Backend Monitoring

```python
# Add to main.py
from fastapi.middleware.cors import CORSMiddleware
import logging

logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Status: {response.status_code}")
    return response
```

#### Frontend Monitoring

Consider integrating:
- Sentry for error tracking
- Google Analytics for usage
- LogRocket for session replay

### 6. Performance Optimization

#### Backend

- Enable database connection pooling (already configured)
- Add Redis for caching:
  ```python
  from redis import Redis
  redis_client = Redis(host='localhost', port=6379, db=0)
  ```
- Implement query result caching
- Use CDN for static assets

#### Frontend

- Enable gzip compression (nginx config above)
- Use code splitting in React
- Lazy load heavy components
- Optimize images

## Scaling Considerations

### Horizontal Scaling

- Use load balancer (AWS ELB, nginx)
- Scale backend instances based on CPU/memory
- Share session state via Redis

### Database Scaling

- Read replicas for heavy read operations
- Connection pooling (already configured)
- Index optimization:
  ```sql
  CREATE INDEX idx_texts_author ON texts(author);
  CREATE INDEX idx_texts_language ON texts(language);
  CREATE INDEX idx_segments_text_ref ON text_segments(text_id, reference);
  ```

### Caching Strategy

- Cache text content (rarely changes)
- Cache word analysis results
- Use CDN for frontend assets

## Monitoring & Alerts

### Health Checks

```python
# Already in main.py
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### Uptime Monitoring

- UptimeRobot (free tier)
- Pingdom
- Better Uptime

### Performance Monitoring

- New Relic
- Datadog
- Prometheus + Grafana

## Backup Strategy

### Database Backups

```bash
# Daily automated backups
pg_dump helios > backup_$(date +%Y%m%d).sql

# Restore
psql helios < backup_YYYYMMDD.sql
```

Most cloud platforms provide automatic backups.

### Code Backups

- Use Git with GitHub/GitLab
- Tag releases: `git tag -a v1.0.0 -m "Release v1.0"`

## Troubleshooting

### Backend Won't Start

1. Check logs: `docker-compose logs backend`
2. Verify database connection
3. Check environment variables
4. Ensure models directory exists

### Frontend Can't Connect to Backend

1. Check CORS settings
2. Verify API URL in frontend .env
3. Check network/firewall rules
4. Verify backend is accessible

### Authentication Issues

1. Verify OAuth credentials
2. Check redirect URIs match exactly
3. Ensure HTTPS in production
4. Clear browser cookies/localStorage

### Performance Issues

1. Check database query performance
2. Monitor memory usage
3. Profile slow endpoints
4. Check network latency

## Security Checklist

- [ ] HTTPS enabled everywhere
- [ ] Environment variables secured
- [ ] Database credentials rotated
- [ ] CORS properly configured
- [ ] Rate limiting enabled
- [ ] SQL injection prevention (SQLAlchemy handles this)
- [ ] XSS prevention (React handles this)
- [ ] CSRF protection for state-changing operations
- [ ] Secrets not in version control
- [ ] Regular dependency updates

## Rollback Plan

```bash
# Docker Compose
docker-compose down
git checkout previous-working-commit
docker-compose up -d

# Cloud platforms
# Use platform's rollback feature or deploy previous version
```

## Support & Maintenance

### Regular Tasks

- Weekly: Review logs and errors
- Monthly: Update dependencies
- Quarterly: Security audit
- Annually: Performance review

### Monitoring Metrics

- Response times (target: <500ms for word analysis)
- Error rates (target: <1%)
- Uptime (target: 99.5%)
- Concurrent users (target: 100+)

---

## Quick Reference

### Environment Variables

**Backend:**
- `DATABASE_URL`
- `SECRET_KEY`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `CORS_ORIGINS`

**Frontend:**
- `VITE_API_URL`

### URLs

- Backend API: `https://api.helios.app`
- Frontend: `https://helios.app`
- API Docs: `https://api.helios.app/docs`

### Common Commands

```bash
# Start local development
docker-compose up -d

# View logs
docker-compose logs -f backend

# Restart service
docker-compose restart backend

# Update and redeploy
git pull
docker-compose up -d --build

# Database backup
docker-compose exec postgres pg_dump -U helios helios > backup.sql
```

