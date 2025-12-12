# Greek Text Database Population

This document describes how Greek texts from the Perseus canonical Greek literature collection are loaded into the Helios database.

## Overview

On application startup, the backend automatically checks if the database contains Greek texts. If the database is empty, it will populate it with texts from the Perseus XML files.

## Data Source

The Greek texts come from the `canonical-greekLit` directory, which contains TEI XML files from the Perseus Digital Library.

## How It Works

### Automatic Population on Startup

1. When the FastAPI application starts, it checks if the `texts` table has any records
2. If empty, it parses all XML files from the data directory
3. Only Greek texts (language='grc') are imported
4. Texts are inserted with their segments (lines, paragraphs, etc.)
5. Duplicate texts (by URN) are skipped

### File Locations

- **Development (docker-compose)**: The `canonical-greekLit` folder is mounted as a volume at `/app/data/canonical-greekLit`
- **Production (Docker image)**: The data must be copied into `backend/data/canonical-greekLit` before building

## Setup Instructions

### For Development (docker-compose)

No additional setup needed. The docker-compose files already mount the `canonical-greekLit` directory:

```bash
docker-compose up
# or
docker-compose -f docker-compose.dev.yml up
```

### For Production Docker Image Build

Before building the production Docker image, run the copy script:

```bash
# From the project root
./backend/scripts/copy_greek_texts.sh

# Then build the Docker image
cd backend
docker build -t helios-backend .
```

### For Local Development (without Docker)

Set the `PERSEUS_DATA_DIR` environment variable to point to the data directory:

```bash
export PERSEUS_DATA_DIR="../canonical-greekLit/data"
# or in .env file
PERSEUS_DATA_DIR=../canonical-greekLit/data
```

## Manual Population

You can also run the population script manually:

```bash
cd backend/src

# Basic population
python -m scripts.populate_on_startup

# With limit (for testing)
python -m scripts.populate_on_startup --limit 10

# Force repopulation (clears existing texts)
python -m scripts.populate_on_startup --force

# Custom data directory
python -m scripts.populate_on_startup --data-dir /path/to/data
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PERSEUS_DATA_DIR` | `/app/data/canonical-greekLit/data` | Path to the Perseus XML data directory |

## Troubleshooting

### "Data directory not found"

Ensure the `canonical-greekLit` directory exists and contains the `data` subdirectory with XML files.

### Population is slow

The full corpus contains thousands of XML files. During development, use the `--limit` flag to test with a smaller subset.

### Database already populated

If you need to repopulate with fresh data, either:
- Use the `--force` flag with the manual script
- Clear the database and restart the application
