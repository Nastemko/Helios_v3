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


### 2. Download Ithaca / Aeneas Models (Optional)

The inscription endpoints load two independent JAX checkpoints — Ithaca for Greek
and Aeneas for Latin. Both are looked up under `INSCRIPTIONS_DIR` (default
`/app/assets/inscriptions`), with the `.pkl` checkpoints in a `models/`
subdirectory alongside the `.json` datasets:

```
$INSCRIPTIONS_DIR/
├── iphi.json                        # Greek dataset
├── led.json                         # Latin dataset
└── models/
    ├── ithaca_153143996_2.pkl       # Greek checkpoint
    ├── iphi_emb_xid153143996.pkl    # Greek retrieval embeddings
    ├── aeneas_117149994_2.pkl       # Latin checkpoint
    └── led_emb_xid117149994.pkl     # Latin retrieval embeddings
```

```bash
export INSCRIPTIONS_DIR=./assets/inscriptions
mkdir -p "$INSCRIPTIONS_DIR/models"

BASE=https://storage.googleapis.com/ithaca-resources/models

# Greek (Ithaca)
curl -o "$INSCRIPTIONS_DIR/iphi.json"                       $BASE/iphi.json
curl -o "$INSCRIPTIONS_DIR/models/ithaca_153143996_2.pkl"    $BASE/ithaca_153143996_2.pkl
curl -o "$INSCRIPTIONS_DIR/models/iphi_emb_xid153143996.pkl" $BASE/iphi_emb_xid153143996.pkl

# Latin (Aeneas)
curl -o "$INSCRIPTIONS_DIR/led.json"                        $BASE/led.json
curl -o "$INSCRIPTIONS_DIR/models/aeneas_117149994_2.pkl"    $BASE/aeneas_117149994_2.pkl
curl -o "$INSCRIPTIONS_DIR/models/led_emb_xid117149994.pkl"  $BASE/led_emb_xid117149994.pkl
```

The Docker image downloads all six files at build time, so this step is only
needed for local runs. Each language initializes independently: if its files are
missing the service logs a warning, startup continues, and the corresponding
endpoints report the model as unavailable.

## Running

### Development

```bash
uv run fastapi dev src/main.py
```

The API will be available at http://localhost:8000

### API Documentation

Visit http://localhost:8000/docs for interactive API documentation (Swagger UI).
The docs are only mounted when `DEBUG=True`; in production `/docs` and `/redoc`
are disabled.

## Project Structure

`src/` is the Python root, so modules use absolute imports (`from config import
settings`). Anything run outside `fastapi dev` needs `PYTHONPATH=./src`.

```
backend/src/
├── main.py              # FastAPI app + startup sequence
├── config.py            # Pydantic settings groups (misc/auth/llm/database/assets)
├── database.py          # Engine, SessionLocal, get_db dependency
├── models/              # SQLAlchemy models
│   ├── user.py
│   ├── text.py          # LiteraryText / LangVersion / TextSegment
│   ├── inscription.py   # Inscription / InscriptionSegment (PHI)
│   └── annotation.py
├── routers/             # API route handlers
│   ├── texts.py
│   ├── auth.py
│   ├── analysis.py
│   ├── inscriptions.py  # Browsing + Ithaca/Aeneas endpoints
│   ├── annotations.py
│   └── translate_assist.py
├── services/            # Business logic
│   ├── morphology.py    # CLTK Greek/Latin analysis
│   ├── llm.py           # LLMProvider ABC + Ollama implementation
│   ├── translate_assist.py
│   └── ithaca_service/  # JAX/Flax model wrapper
├── vendor/              # Vendored DeepMind predictingthepast model code
├── parsers/             # Data parsers
│   ├── cts_metadata_parser.py   # __cts__.xml work/version metadata
│   └── perseus_xml_parser.py    # TEI segment extraction
├── middleware/          # Middleware
│   ├── auth.py
│   └── performance.py
├── utils/               # Utilities
│   └── security.py
└── scripts/             # Populators (CLI + startup entry points)
    ├── init_db.sql
    ├── populate_database.py
    ├── populate_database_llm.py
    └── load_phi_inscriptions.py
```

## Data Population

Populators run automatically at startup and are also usable as CLIs. They are
resumable and idempotent — existing records are prefetched and inserts use
`ON CONFLICT DO NOTHING` — so re-running them is safe.

```bash
# Parse without inserting
PYTHONPATH=./src uv run python src/scripts/populate_database.py --dry-run --limit 5

# Insert a subset, then everything
PYTHONPATH=./src uv run python src/scripts/populate_database.py --limit 100
PYTHONPATH=./src uv run python src/scripts/populate_database.py
```

Files that fail lxml parsing are recorded to `lxml_failures.json` next to the
Perseus data directory. On the next startup, `populate_database_llm.py` retries
those through OpenRouter — but only when `OPENROUTER_API_KEY` is set; otherwise
the step is skipped with a log message.

## API Endpoints

### Health Check
- `GET /health` - Health check endpoint

### Authentication
- `GET /api/auth/login/google` - Redirect to Google OAuth
- `GET /api/auth/callback/google` - OAuth callback
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout
- `POST /api/auth/dev-login` - Issue a token for the dev user; returns 403 unless `DEBUG=True`
- `GET /api/auth/status` - Current user if authenticated, otherwise null

### Texts
- `GET /api/texts/` - List/search texts
- `GET /api/texts/authors/list` - List distinct authors
- `GET /api/texts/stats/summary` - Corpus statistics
- `GET /api/texts/{text_id}` - Get a text with paginated segments
- `GET /api/texts/{text_id}/segment/{reference}` - Get one segment by reference (e.g. `1.1`)

`text_id` is the integer id of a `LiteraryTextLangVersion` — a specific language
edition, not a CTS URN and not the parent work.

### Word Analysis
- `POST /api/analyze/word` - Analyze a Greek/Latin word (CLTK morphology)

### Translation Assist (LLM)
- `POST /api/translate-assist` - Translation suggestion for a Greek passage
- `GET /api/translate-assist/status` - Service availability and configured model

`POST /api/translate-assist` returns HTTP 503 when `LLM_ENABLED=False`; the
status endpoint stays reachable and reports `enabled: false`.

### Inscriptions (PHI browsing + Ithaca/Aeneas AI)
- `GET /api/inscriptions/` - List/search inscriptions
- `GET /api/inscriptions/regions` - Inscription counts by region
- `GET /api/inscriptions/stats` - Inscription statistics
- `GET /api/inscriptions/{text_id}` - Get one inscription with its segments
- `POST /api/inscriptions/restore` - Restore damaged text
- `POST /api/inscriptions/attribute` - Geographic/date attribution
- `POST /api/inscriptions/contextualize` - Find similar inscriptions
- `GET /api/inscriptions/model/status` - Per-language model availability
- `POST /api/inscriptions/model/initialize` - Load models on demand

### Annotations
- `POST /api/annotations/` - Create annotation
- `GET /api/annotations/` - List user annotations
- `GET /api/annotations/{annotation_id}` - Get one annotation
- `PUT /api/annotations/{annotation_id}` - Update annotation
- `DELETE /api/annotations/{annotation_id}` - Delete annotation
- `GET /api/annotations/version/{version_id}/summary` - Annotation summary for an edition

## Development

### Adding a New Router

1. Create router file in `routers/`
2. Define endpoints
3. Import and include in `main.py`

### Database Schema

There are no migrations. `main.py` calls `Base.metadata.create_all()` on startup,
which creates missing tables but never alters existing ones. Changing a model
therefore has no effect on a database that already has that table — apply the
change by hand with SQL, or drop the volume and let startup recreate the schema:

```bash
docker compose down -v && docker compose up -d   # destroys all local data
```

Adding alembic is the obvious fix if the schema starts changing regularly.

### Testing

```bash
pytest                                  # all tests
pytest src/config_test.py               # single file
pytest -v                               # verbose
```

### Formatting

```bash
uv run black .    # 88 columns; run before committing
```

Note that `black .` also rewrites `src/vendor/`, which holds vendored DeepMind
model code. There is no exclude configured, so keep vendored files out of your
commits unless you intend to diverge from upstream.

## LLM Configuration

Translation assist depends on the LLM provider defined in `services/llm.py`
(an `LLMProvider` ABC with an Ollama-backed implementation). Settings use the
`LLM_` prefix and are read through `settings.llm`:

- `LLM_ENABLED` – enable/disable translation assist (defaults to `True`)
- `LLM_BASE_URL` – Ollama endpoint (defaults to `http://localhost:11434`)
- `LLM_MODEL` – model name (defaults to `llama3.2:3b`)
- `LLM_TEMPERATURE`, `LLM_THINK`, `LLM_TIMEOUT` – generation parameters

When `LLM_ENABLED` is `False`, `POST /api/translate-assist` returns HTTP 503 and
`GET /api/translate-assist/status` reports `enabled: false`.

A separate `OPENROUTER_*` group configures the LLM-based database populator only;
it is unrelated to the runtime translation features.

## Production Deployment

See `../PRD/implementation_plan_v1.md` for deployment instructions.
