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
- **🏛️ Inscription Workbench** - Restore, attribute, and contextualize PHI inscriptions

## Architecture

```
┌──────────────┐
│    React     │  Frontend (dev :3000, Docker :8888)
└──────┬───────┘
       │ HTTP/REST
       ▼
┌──────────────┐
│   FastAPI    │  Backend (:8000)
└─┬──┬───┬───┬─┘
  │  │   │   │
  │  │   │   └──▶ Ollama          Translation assist (:11434)
  │  │   └──────▶ CLTK            Greek/Latin morphology (in-process)
  │  └──────────▶ Ithaca/Aeneas   JAX inscription models (in-process)
  └─────────────▶ PostgreSQL      Texts, inscriptions, users, annotations
```

A separate `perseus-db` (MariaDB, `:3307`) holds the Perseus dumps and is
currently browse-only via Adminer — it is not yet read by the backend.

### Tech Stack

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query
- **Backend:** Python 3.13 + FastAPI + SQLAlchemy 2.0 (managed with uv)
- **Database:** PostgreSQL (pgvector image); MariaDB for the Perseus dumps
- **Authentication:** OAuth2 (Google) + JWT
- **AI:** Ithaca (Greek) and Aeneas (Latin) models via JAX/Flax; Ollama for translation assist
- **Morphology:** CLTK
- **Texts:** Perseus Digital Library (TEI XML)

## Quick Start

### Prerequisites

- Python 3.13 (the backend pins `~=3.13.0`)
- Node.js 18+
- PostgreSQL 14+ (pgvector image in Docker)
- Git
- uv

### 1. Clone Repository

```bash
git clone <repository-url>
cd Helios_v3
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Fill in at least `DATABASE_PASSWORD`. For local development set `DEBUG=True`,
which relaxes the `SECRET_KEY` requirement and enables the dev auth bypass — see
[Configuration](#configuration) below.

### 3. Backend Setup

```bash
cd backend

# Create virtual environment and install dependencies
uv sync
# Parse and populate texts (resumable; safe to re-run)
PYTHONPATH=./src uv run python src/scripts/populate_database.py --limit 10  # Start with 10 texts for testing

# Start backend server
uv run fastapi dev src/main.py
```

Backend will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs` (requires `DEBUG=True`)

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend will be available at `http://localhost:3000`

### 5. (Optional) Download Ithaca / Aeneas Models

The inscription features need two JAX checkpoints — Ithaca for Greek, Aeneas for
Latin — placed under `INSCRIPTIONS_DIR`. See
[`backend/README.md`](backend/README.md) for the expected layout and the full set
of download commands.

The Docker image fetches these at build time, so this step is only needed for
local runs. Without them the app still starts; the inscription endpoints report
the models as unavailable.

## Project Structure

```
Helios_v3/
├── backend/                 # Python FastAPI backend
│   ├── src/                # Python root — set PYTHONPATH=./src
│   │   ├── main.py         # Entry point + startup sequence
│   │   ├── config.py       # Pydantic settings groups
│   │   ├── database.py     # Engine, session, get_db dependency
│   │   ├── models/         # SQLAlchemy models
│   │   ├── routers/        # API endpoints
│   │   ├── services/       # Business logic (morphology, LLM, Ithaca)
│   │   ├── vendor/         # Vendored DeepMind model code
│   │   ├── parsers/        # Perseus CTS + TEI XML parsers
│   │   ├── middleware/     # Auth & performance middleware
│   │   └── scripts/        # Database populators
│   ├── assets/
│   │   └── canonical-greekLit/data/   # Perseus TEI XML texts
│   └── pyproject.toml      # Python dependencies (managed by uv)
├── frontend/               # React + TypeScript frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── pages/         # Page components
│   │   ├── contexts/      # React contexts
│   │   ├── services/      # API services
│   │   └── types/         # TypeScript types
│   ├── package.json       # Node dependencies
│   └── vite.config.ts     # Vite configuration
├── perseus/                # Perseus MariaDB dumps + import script
│   ├── dumps/             # ~839MB of MySQL dumps
│   └── init/              # Entrypoint loader run on first boot
├── docker-compose.yml      # Full stack: postgres, backend, frontend, ollama, perseus-db, adminer
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
- `GET /api/texts/` - List/search texts
- `GET /api/texts/{text_id}` - Get a text with its segments
- `GET /api/texts/{text_id}/segment/{reference}` - Get a specific segment

### Word Analysis
- `POST /api/analyze/word` - Analyze Greek/Latin word

### Translation Assist
- `POST /api/translate-assist` - AI translation suggestion for a passage
- `GET /api/translate-assist/status` - Service availability

### Inscriptions (PHI + Ithaca/Aeneas AI)
- `GET /api/inscriptions/` - List/search inscriptions
- `GET /api/inscriptions/model/status` - Check model availability
- `POST /api/inscriptions/restore` - Restore damaged text
- `POST /api/inscriptions/attribute` - Geographic/date attribution
- `POST /api/inscriptions/contextualize` - Find similar inscriptions

### Annotations
- `POST /api/annotations/` - Create annotation
- `GET /api/annotations/` - List user annotations
- `PUT /api/annotations/{id}` - Update annotation
- `DELETE /api/annotations/{id}` - Delete annotation

The full endpoint list is in [`backend/README.md`](backend/README.md), and the
interactive Swagger docs are at `/docs` when `DEBUG=True`.

## Configuration

There is a single `.env` at the repo root, shared by the backend and by
`docker-compose.yml`. Copy [`.env.example`](.env.example) and fill it in — it is
the authoritative list of variables.

The connection string is assembled from separate `DATABASE_*` parts rather than a
single `DATABASE_URL`:

```bash
# Database (DATABASE_ prefix)
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_DB=helios
DATABASE_USER=heliosuser
DATABASE_PASSWORD=<generate-a-strong-password>

# Security — required when DEBUG=False; generate with: openssl rand -hex 32
SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback/google

# Application
DEBUG=False
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8888"]

# Asset paths
INSCRIPTIONS_DIR=/app/assets/inscriptions
PERSEUS_DATA_DIR=/app/assets/canonical-greekLit/data

# Frontend
VITE_API_URL=http://backend:8000
```

Setting `DEBUG=True` for local development disables the `SECRET_KEY` requirement,
mounts `/docs`, and **bypasses authentication entirely** — `get_current_user`
returns a `dev@helios.local` user without a token. Never run with `DEBUG=True`
in production or when testing authorization behavior.

## Development

### Running Tests

```bash
cd backend
pytest                       # all tests
pytest src/config_test.py    # a single file
```

The frontend has no test runner configured. `npm run lint` is declared in
`package.json` but currently fails — eslint is not in the dependencies and no
config file exists. Type checking via `npm run build` (or `npx tsc --noEmit`) is
the working check.

### Code Formatting

```bash
cd backend
uv run black .    # 88 columns; run before committing
```

### Database Schema

There are no migrations. The backend calls `Base.metadata.create_all()` on
startup, which creates missing tables but never alters existing ones — so
changing a model has no effect on a database that already has that table. Apply
such changes manually with SQL, or reset the volume:

```bash
docker compose down -v && docker compose up -d   # destroys all local data
```

### Populating Texts

```bash
cd backend

# Dry run (parse without inserting)
PYTHONPATH=./src uv run python src/scripts/populate_database.py --dry-run --limit 5

# Insert 100 texts
PYTHONPATH=./src uv run python src/scripts/populate_database.py --limit 100

# Insert all texts
PYTHONPATH=./src uv run python src/scripts/populate_database.py
```

Files that fail lxml parsing are recorded to `lxml_failures.json`. An LLM-based
populator at `src/scripts/populate_database_llm.py` retries those through
OpenRouter, and runs automatically on startup when `OPENROUTER_API_KEY` is set.
See [`backend/README.md`](backend/README.md) for details.

## Deployment

See [PRD/implementation_plan_v1.md](PRD/implementation_plan_v1.md) for detailed deployment instructions.

### Docker Compose (Quick Deploy)

```bash
docker compose up -d
```

Services and ports:

| Service      | Port  | Notes                                          |
|--------------|-------|------------------------------------------------|
| frontend     | 8888  | Caddy-served production build                  |
| backend      | 8000  | FastAPI                                        |
| postgres     | —     | pgvector image, internal only                  |
| ollama       | 11434 | LLM for translation assist                     |
| perseus-db   | 3307  | MariaDB with Perseus dumps                     |
| adminer      | 8080  | Web UI for inspecting perseus-db               |

On first boot `perseus-db` imports ~839MB of dumps from `perseus/dumps/` and does
not accept connections until that finishes — its healthcheck allows a 60-minute
grace period. Subsequent starts reuse the volume and come up immediately.

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

These are the goals from the PRD, not measured results:

- Word analysis: < 500ms
- Text loading: < 3 seconds
- Concurrent users: 100+
- Uptime: 99.5%

Request timings are logged by the performance middleware in
`backend/src/middleware/performance.py`.

## Contributing

This is an educational project. Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Documentation

- [Backend README](backend/README.md) - setup, endpoints, data population
- [Backend agent guidelines](backend/AGENTS.md) - code style and conventions
- [Frontend README](frontend/README.md)
- [Product Requirements Document](PRD/helios_v3_prd.md)
- [Implementation Plan](PRD/implementation_plan_v1.md)

The `PRD/` and `roadmap/` documents describe intended design and are partly out
of date; where they disagree with the code, the code is authoritative.

## License

No license file is currently present in this repository.

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
