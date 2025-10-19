# Helios Backend

FastAPI backend for the Helios classical texts application.

## Setup

### 1. Install Dependencies

1.  **Install uv**

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2. **Synchronise the environment**

    ```bash
    uv sync
    ```


### 2. Download Aeneas Models (Optional)

For AI features, download the Greek model:

```bash
mkdir -p models

# Greek model
curl -o models/ithaca_153143996_2.pkl \
    https://storage.googleapis.com/ithaca-resources/models/ithaca_153143996_2.pkl

curl -o models/iphi.json \
    https://storage.googleapis.com/ithaca-resources/models/iphi.json

curl -o models/iphi_emb_xid153143996.pkl \
    https://storage.googleapis.com/ithaca-resources/models/iphi_emb_xid153143996.pkl
```

## Running

### Development

```bash
fastapi dev src/main.py
```

The API will be available at http://localhost:8000

### API Documentation

Visit http://localhost:8000/docs for interactive API documentation (Swagger UI)

## Project Structure

```
backend/src/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration and settings
├── database.py          # Database connection and session
├── models/              # SQLAlchemy models
│   ├── user.py
│   ├── text.py
│   └── annotation.py
├── routers/             # API route handlers
│   ├── texts.py
│   ├── auth.py
│   ├── analysis.py
│   ├── aeneas.py
│   └── annotations.py
├── services/            # Business logic
│   ├── morphology.py
│   └── aeneas_service.py
├── parsers/             # Data parsers
│   └── perseus_xml_parser.py
├── middleware/          # Middleware
│   ├── auth.py
│   └── performance.py
├── utils/               # Utilities
│   └── security.py
└── scripts/             # Helper scripts
    └── populate_texts.py
```

## API Endpoints

### Health Check
- `GET /health` - Health check endpoint

### Authentication
- `GET /api/auth/login/google` - Redirect to Google OAuth
- `GET /api/auth/callback/google` - OAuth callback
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout

### Texts
- `GET /api/texts` - List/search texts
- `GET /api/texts/{urn}` - Get specific text
- `GET /api/texts/{urn}/segment/{reference}` - Get text segment

### Word Analysis
- `POST /api/analyze/word` - Analyze Greek/Latin word

### Aeneas AI
- `POST /api/aeneas/restore` - Restore damaged text
- `POST /api/aeneas/attribute` - Geographic/date attribution
- `POST /api/aeneas/contextualize` - Find similar inscriptions

### Annotations
- `POST /api/annotations` - Create annotation
- `GET /api/annotations` - List user annotations
- `PUT /api/annotations/{id}` - Update annotation
- `DELETE /api/annotations/{id}` - Delete annotation

## Development

### Adding a New Router

1. Create router file in `routers/`
2. Define endpoints
3. Import and include in `main.py`

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Testing

```bash
pytest
```

## Production Deployment

See `../PRD/implementation_plan_v1.md` for deployment instructions.

