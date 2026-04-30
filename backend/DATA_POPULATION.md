# Text Database Population

This document describes how Greek and Latin texts from the Perseus canonical literature collection are loaded into the Helios database.

## Overview

On application startup, the backend runs the populator against the Perseus XML data. The populator is **idempotent and resumable**: already-imported language versions are skipped per-version, so it is safe to start the backend repeatedly without re-ingesting work.

Two populators are available:

1. **`populate_database.py`** — the default lxml/CTS-aware parser. Used by the auto-startup flow and is the recommended path for full ingestion.
2. **`populate_database_llm.py`** — an alternative that uses an LLM (via OpenRouter) to extract structured data from raw TEI XML. Useful when the lxml path fails on edge-case files or for experimentation.

## Data Source

The texts come from the `canonical-greekLit` directory, which contains TEI XML files from the Perseus Digital Library.

## How It Works

### Automatic Population on Startup

1. When the FastAPI application starts, `populate_on_startup` runs unconditionally.
2. It walks the configured data directory and, for each language version, calls `should_process_version` to skip ones already present in the DB.
3. New versions are parsed (segments, metadata, CTS structure) and inserted.
4. The script logs `inserted_versions` and `skipped` counts on completion.

### File Locations

- **Development (docker-compose)**: The `canonical-greekLit` folder is mounted into the backend container at `/app/assets/canonical-greekLit`.
- **Production (Docker image)**: The Dockerfile `COPY`s `./assets/canonical-greekLit` into the image at build time (see `backend/Dockerfile`).

## Setup Instructions

### For Development (docker-compose)

No additional setup needed:

```bash
docker compose up
```

### For Local Development (without Docker)

Set the `PERSEUS_DATA_DIR` environment variable to point to the data directory:

```bash
export PERSEUS_DATA_DIR="../canonical-greekLit/data"
# or in .env file
PERSEUS_DATA_DIR=../canonical-greekLit/data
```

## Manual Population (lxml-based)

Run the default populator directly:

```bash
cd backend
PYTHONPATH=./src uv run python src/scripts/populate_database.py [flags]
```

Flags:

| Flag | Description |
|------|-------------|
| `--limit N` | Process at most N XML files (useful for testing) |
| `--dry-run` | Walk files and log what would be done; no DB writes |
| `--languages grc lat en` | Filter to specific language codes |
| `--batch-size N` | Commit every N versions (default 100) |
| `--fail-fast` | Abort on the first error (default: on) |
| `--data-dir PATH` | Override the Perseus data directory |

## LLM-based Population (alternative)

`populate_database_llm.py` is an alternative path that sends raw TEI XML chunks to an OpenRouter-hosted LLM and parses the structured JSON response. It requires an OpenRouter API key.

### Configuration

The script reads `OPENROUTER_*` env vars (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | *(empty)* | **Required.** Get a free key at https://openrouter.ai/keys |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API endpoint |
| `OPENROUTER_MODEL` | `meta-llama/llama-3.1-8b-instruct:free` | Default model ID |
| `OPENROUTER_TEMPERATURE` | `0.1` | Sampling temperature |
| `OPENROUTER_MAX_TOKENS` | `4096` | Max tokens per LLM call |

### Running

```bash
cd backend

# Dry run — discover files only, no LLM calls, no DB writes
PYTHONPATH=./src uv run python src/scripts/populate_database_llm.py --limit 5 --dry-run

# Live run with a specific free model
PYTHONPATH=./src uv run python src/scripts/populate_database_llm.py \
    --model google/gemma-2-9b-it:free --limit 10
```

Flags:

| Flag | Description |
|------|-------------|
| `--limit N` | Process at most N XML files |
| `--dry-run` | Discover files only; do not call the LLM or write to DB |
| `--model ID` | OpenRouter model ID (overrides `OPENROUTER_MODEL`) |
| `--languages grc lat en` | Filter to specific language codes |
| `--batch-size N` | Commit batch size (default 50) |
| `--fail-fast` | Abort on the first error (default: off) |
| `--data-dir PATH` | Override the Perseus data directory |

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `PERSEUS_DATA_DIR` | `/app/assets/canonical-greekLit/data` | Path to the Perseus XML data directory |
| `OPENROUTER_API_KEY` | *(empty)* | OpenRouter API key (LLM populator only) |
| `OPENROUTER_MODEL` | `meta-llama/llama-3.1-8b-instruct:free` | Default OpenRouter model |

## Troubleshooting

### "Data directory not found"

Ensure the `canonical-greekLit` directory exists and contains the `data` subdirectory with XML files.

### Population is slow

The full corpus contains thousands of XML files. During development, use `--limit` to test with a smaller subset. The LLM-based populator is significantly slower than the lxml one due to per-file API calls.

### Re-running

Both populators are resumable — already-ingested versions are skipped. To force a full re-import, clear the relevant tables (`literary_text`, `literary_text_lang_version`, `text_segment`) and re-run.

### `OPENROUTER_API_KEY` errors

The LLM populator fails fast if the key is empty. Set it in `.env` (see `.env.example`).
