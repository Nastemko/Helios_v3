# Helios - Classical Text Reader

A modern web application for reading and analyzing ancient Greek and Latin texts, powered by AI.

## Overview

Helios integrates the Perseus Digital Library with Google DeepMind's Aeneas AI model to provide students and researchers with an interactive platform for classical text analysis.

### Key Features

- **📚 Extensive Text Library** - Access 2500+ texts from the Perseus Digital Library
- **🔍 Word-by-Word Analysis** - Click any word for instant morphological analysis
- **🤖 AI-Powered Insights** - Text restoration and attribution using Aeneas model
- **📝 Personal Annotations** - Save notes and translations that persist across sessions
- **🔐 Secure Authentication** - Google OAuth integration
- **⚡ Fast Performance** - <500ms word analysis, <3s text loading

## Architecture

```
┌─────────────┐
│   React     │  Frontend (Port 3000)
│  Frontend   │
└──────┬──────┘
       │ HTTP/REST
       ▼
┌─────────────┐
│   FastAPI   │  Backend (Port 8000)
│   Backend   │
└─┬───┬───┬───┘
  │   │   │
  ▼   ▼   ▼
┌──┐┌───┐┌──┐
│DB││AI ││MA│  Database, AI Model, Morphology
└──┘└───┘└──┘
```

### Tech Stack

- **Frontend:** React + TypeScript + Vite + Tailwind CSS
- **Backend:** Python FastAPI + SQLAlchemy
- **Database:** PostgreSQL
- **Authentication:** OAuth2 (Google) + JWT
- **AI:** Aeneas model (JAX/Flax)
- **Texts:** Perseus Digital Library (TEI XML)

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Git
- uv

### 1. Clone Repository

```bash
git clone <repository-url>
cd Helios_v3
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment and install dependencies
uv sync
# Parse and populate texts
uv run python scripts/populate_texts.py --limit 10  # Start with 10 texts for testing

# Start backend server
uv run fastapi dev main.py
```

Backend will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at `http://localhost:3000`

### 4. (Optional) Download Aeneas Models

For AI features, download the Greek model:

```bash
cd backend
mkdir -p models

# Greek model (Ithaca)
curl -o models/ithaca_153143996_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/ithaca_153143996_2.pkl

curl -o models/iphi.json \
    https://storage.googleapis.com/ithaca-resources/models/iphi.json

curl -o models/iphi_emb_xid153143996.pkl \
    https://storage.googleapis.com/ithaca-resources/models/iphi_emb_xid153143996.pkl
```

## Project Structure

```
Helios_v3/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Entry point
│   ├── config.py           # Configuration
│   ├── database.py         # Database setup
│   ├── models/             # SQLAlchemy models
│   ├── routers/            # API endpoints
│   ├── services/           # Business logic
│   ├── parsers/            # Perseus XML parser
│   ├── middleware/         # Auth & performance middleware
│   ├── scripts/            # Helper scripts
│   └── requirements.txt    # Python dependencies
├── frontend/               # React + TypeScript frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── pages/         # Page components
│   │   ├── contexts/      # React contexts
│   │   ├── services/      # API services
│   │   └── types/         # TypeScript types
│   ├── package.json       # Node dependencies
│   └── vite.config.ts     # Vite configuration
├── canonical-greekLit/     # Perseus texts (Greek)
│   └── data/              # TEI XML files
├── predictingthepast_exp/  # Aeneas AI model
└── PRD/                    # Product documentation
    ├── helios_v3_prd.md   # Product requirements
    └── implementation_plan_v1.md  # Implementation plan
```

## API Endpoints

### Authentication
- `GET /api/auth/login/google` - Initiate Google OAuth
- `GET /api/auth/callback/google` - OAuth callback
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout

### Texts
- `GET /api/texts` - List/search texts
- `GET /api/texts/{urn}` - Get specific text
- `GET /api/texts/{urn}/segment/{ref}` - Get text segment

### Word Analysis
- `POST /api/analyze/word` - Analyze Greek/Latin word

### Aeneas AI
- `GET /api/aeneas/status` - Check model availability
- `POST /api/aeneas/restore` - Restore damaged text
- `POST /api/aeneas/attribute` - Geographic/date attribution
- `POST /api/aeneas/contextualize` - Find similar inscriptions

### Annotations
- `POST /api/annotations` - Create annotation
- `GET /api/annotations` - List user annotations
- `PUT /api/annotations/{id}` - Update annotation
- `DELETE /api/annotations/{id}` - Delete annotation

## Configuration

### Backend (.env)

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/helios

# Security
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback/google

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Paths
MODELS_DIR=./models
PERSEUS_DATA_DIR=../canonical-greekLit/data
```

### Frontend (.env)

```bash
VITE_API_URL=http://localhost:8000
```

## Development

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

### Database Migrations

```bash
cd backend

# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Populating Texts

```bash
cd backend

# Dry run (parse without inserting)
python scripts/populate_texts.py --dry-run --limit 5

# Insert 100 texts
python scripts/populate_texts.py --limit 100

# Insert all texts
python scripts/populate_texts.py
```

## Deployment

See [PRD/implementation_plan_v1.md](PRD/implementation_plan_v1.md) for detailed deployment instructions.

### Docker Compose (Quick Deploy)

```bash
docker-compose up -d
```

### Manual Deployment

**Backend:**
- Railway, Render, or Fly.io
- PostgreSQL database
- Environment variables configured

**Frontend:**
- Vercel or Netlify
- Connect to backend API
- OAuth redirect URLs updated

## Performance Targets

- ✅ Word analysis: < 500ms
- ✅ Text loading: < 3 seconds
- ✅ Concurrent users: 100+
- ✅ Uptime: 99.5%

## Contributing

This is an educational project. Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Documentation

- [Product Requirements Document](PRD/helios_v3_prd.md)
- [Implementation Plan](PRD/implementation_plan_v1.md)
- [Backend README](backend/README.md)
- [Frontend README](frontend/README.md)

## License

See LICENSE file for details.

## Acknowledgments

- **Perseus Digital Library** - Classical texts
- **Google DeepMind** - Aeneas AI model
- **Logeion** - Lexicon integration
- Classical language community

## Support

For issues or questions:
- Check existing documentation
- Review API docs at `/docs` when backend is running
- Open an issue on GitHub

---

**Status:** MVP Complete - Ready for pilot testing

Built with ❤️ for classics students and researchers
