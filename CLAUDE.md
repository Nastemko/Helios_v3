# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Backend-specific conventions (import order, type hints, error handling, SQLAlchemy patterns) live in `backend/AGENTS.md` — read it before writing backend Python.

## Commands

### Backend (`backend/`, Python 3.13 + uv)

```bash
uv sync                                  # install deps
uv run fastapi dev src/main.py           # dev server on :8000 (docs at /docs when DEBUG=True)
uv run black .                           # format (88 cols) — run before committing
pytest                                   # all tests
pytest src/config_test.py                # single file
pytest src/config_test.py::TestConfig::test_settings_load_from_env   # single test
```

If pytest dies at collection with `error parsing value for field "CORS_ORIGINS"`,
an exported shell variable is shadowing `.env` (env vars win over the file).
`CORS_ORIGINS` is a `list[str]` and must be valid JSON — `["http://a","http://b"]`,
with the URLs quoted. Unset the stray variable rather than editing config:
`env -u CORS_ORIGINS uv run pytest`.

**`src/` is the Python root.** Modules use absolute imports (`from config import settings`, not `from src.config import ...`). Any script run outside `fastapi dev` needs `PYTHONPATH=./src`:

```bash
PYTHONPATH=./src uv run python src/scripts/populate_database.py --dry-run --limit 5
PYTHONPATH=./src uv run python src/scripts/populate_database.py --limit 100
```

**Tests are the exception** — `[tool.pytest.ini_options] pythonpath = ["src"]` in
`pyproject.toml` puts `src/` on `sys.path`, so plain `pytest` resolves those same
absolute imports without the env var. Without that setting tests fail at collection
with `ModuleNotFoundError: No module named 'config'`; don't remove it.

### Frontend (`frontend/`)

```bash
npm install
npm run dev        # Vite on :3000, proxies /api → localhost:8000
npm run build      # tsc && vite build
npx tsc --noEmit   # typecheck only
npm run lint       # eslint 10, flat config
```

No test runner is configured. `npm run lint` runs eslint 10 (flat config in
`eslint.config.js`, typescript-eslint + react-hooks + react-refresh). It currently
reports 8 pre-existing findings in application code — mostly `no-explicit-any` and
two `react-hooks/set-state-in-effect` — so it is **not** clean yet; treat new
findings as regressions rather than expecting a zero exit.

### Full stack

```bash
docker compose up -d     # `docker` is rootless podman on this machine
```

Ports: frontend 8888, backend 8000, postgres (internal), ollama 11434, perseus-db 3307, adminer 8080.

## Architecture

Three data sources feed one FastAPI backend:

1. **Perseus TEI XML** (`backend/assets/canonical-greekLit/data/`) → parsed into PostgreSQL as literary texts.
2. **PHI inscriptions** (`iphi.json`, under `INSCRIPTIONS_DIR`) → loaded into the `inscriptions` tables.
3. **Perseus MariaDB dumps** (`perseus/dumps/`, ~839MB) → loaded into the `perseus-db` container. **Not yet wired into the backend** — currently browse-only via Adminer. This is the in-flight work on `feature/perseus-db-setup`.

### Backend layout (`backend/src/`)

- `main.py` — app assembly + the startup sequence (see below).
- `config.py` — `settings` is a plain `Settings` object composing five `BaseSettings` groups: `settings.misc`, `.auth`, `.llm`, `.database`, `.assets`. Each has its own env prefix (`LLM_`, `DATABASE_`; `auth`/`misc`/`assets` are unprefixed). Always read config through `settings.<group>.<KEY>`.
- `database.py` — engine + `SessionLocal` + `get_db()` FastAPI dependency. Connection string is assembled from `settings.database` parts, not a single `DATABASE_URL`.
- `routers/` — `texts`, `auth`, `annotations`, `analysis`, `inscriptions`, `translate_assist`. All prefixed `/api/...`.
- `services/` — `morphology` (CLTK), `llm` (Ollama provider behind an ABC), `translate_assist`, `ithaca_service/` (JAX/Flax model wrapper).
- `vendor/predictingthepast/` — vendored DeepMind model code; `ithaca_service` imports from it. Don't "fix" vendored files. Note `uv run black .` reformats them too (no exclude is configured), so check `git status` before committing.
- `parsers/` — `cts_metadata_parser` (reads `__cts__.xml` for work/version metadata) and `perseus_xml_parser` (extracts segments).
- `scripts/` — populators; each is both a CLI (`if __name__ == "__main__"`) and an importable `*_on_startup()` coroutine called from `main.py`.

### Startup sequence (`main.py`)

`Base.metadata.create_all()` → Perseus text population → LLM population of lxml failures (only if `OPENROUTER_API_KEY` set) → PHI inscriptions → CLTK morphology → Ithaca/Aeneas models.

Every step after table creation is wrapped in try/except and logs-and-continues — a missing model file or empty data dir degrades features but must not block boot. Preserve that when adding startup work.

**There are no migrations.** No alembic setup exists; schema comes from `create_all` at startup (the README's alembic section is stale). Changing a model means the existing DB will not pick it up — plan for a manual migration or volume reset.

### Text data model

Three-level hierarchy, deliberately separating a work from its language versions:

- `LiteraryText` — language-agnostic parent, keyed by `local_id`.
- `LiteraryTextLangVersion` — one per language/translation, holds `author`/`title`/`translator`, `Language` enum column.
- `TextSegment` — a line or paragraph, ordered by `sequence`, addressed by `reference`.

`Inscription` / `InscriptionSegment` are a separate, parallel hierarchy — PHI inscriptions never go through `LiteraryText`. Structured PHI fields (`region_main`, `date_min`/`date_max`) are extracted into columns; the rest stays in the `metadata_raw` JSONB and is **not** duplicated.

Populators are resumable and idempotent: they prefetch existing `local_id`s and use `insert(...).on_conflict_do_nothing()`. Keep that property in any new loader.

### Ithaca / Aeneas models

`ithaca_service` loads two separate JAX checkpoints — Greek (Ithaca, `iphi.json` + `ithaca_*.pkl`) and Latin (Aeneas, `led.json` + `aeneas_*.pkl`) — from `settings.assets.INSCRIPTIONS_DIR`. The backend Dockerfile downloads all six files at build time; local runs need them fetched manually or the service reports unavailable and the endpoints degrade.

### Auth

Exactly two modes, selected by `DEBUG`. Google OAuth → JWT bearer token, `get_current_user` in `middleware/auth.py`; there is no dev-login, password, or other credential path.

**`DEBUG=True` disables authentication entirely** — `get_current_user` returns the shared `dev@helios.local` user (`get_or_create_dev_user`) and *deliberately ignores any token that was sent*, so every caller is the same user and annotations are shared and open. `/api/auth/status` reports that same user, and the frontend uses it to decide whether a login is needed. Never test authz behavior with `DEBUG=True`.

**`DEBUG=False` requires Google.** `validate_production()` demands `SECRET_KEY`, `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` together, and raises at startup naming whichever are missing. The JWT algorithm is pinned to `JWT_ALGORITHM` in `utils/security.py`, not read from config.

Annotations are scoped by `Annotation.user_id` inside the SQL `WHERE` on every read and write, so a non-owned row 404s rather than 403s. The costly endpoints (`POST /api/translate-assist`, inscription `restore`/`attribute`/`contextualize`/`model/initialize`) require auth; text and inscription browsing remain public.

### Frontend

React 18 + TypeScript + Vite + Tailwind, React Query for server state, axios in `src/services/api.ts` with a request interceptor injecting `localStorage.auth_token`. `VITE_API_URL` overrides the base URL (set to `http://backend:8000` in compose, unset locally so the Vite proxy handles it). Two main surfaces: the text reader (`pages/TextReader.tsx`, word-click analysis) and the inscription workbench (`pages/InscriptionWorkbench.tsx`, Ithaca restore/attribute/contextualize).

## Notes

- `perseus-db` first boot imports the dumps before accepting connections; the healthcheck has a 60-minute `start_period` for that reason. Bind mounts use `:ro,Z` for rootless podman/SELinux.
- Docs under `PRD/`, `roadmap/`, and `LOCAL_TEST_STATUS.md` describe intent and are partly outdated — trust the code over them. `backend/README.md` in particular lists routers and services that no longer exist.
