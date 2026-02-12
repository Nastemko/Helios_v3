# Helios Backend Agent Guidelines

This document provides essential guidelines for AI agents working on the Helios backend codebase.

## Project Overview

**Technology Stack:**
- Python 3.13+ with FastAPI
- PostgreSQL database with SQLAlchemy 2.0+
- Pydantic for configuration and data validation
- Black for code formatting
- pytest for testing

**Architecture:**
- FastAPI with routers for API endpoints
- Services for business logic separation
- SQLAlchemy models for database entities
- Configuration via Pydantic Settings with environment variables

## Essential Commands

### Development Environment
```bash
# Install dependencies
uv sync

# Run development server
uv run fastapi dev src/main.py

# Run production server
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Code Quality
```bash
# Format code (always run before committing)
uv run black .

# Run all tests
pytest

# Run single test file
pytest src/config_test.py

# Run specific test method
pytest src/config_test.py::TestConfig::test_settings_load_from_env

# Run with verbose output
pytest -v
```

## Code Style Guidelines

### Import Organization (Strict Order)
```python
# 1. Standard library imports
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# 2. Third-party imports
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

# 3. Local imports (always use absolute imports)
from config import settings
from database import SessionLocal
from models.text import LiteraryText, Language
```

### Formatting Standards
- **Formatter**: Black (max line length: 88 characters)
- **Type Hints**: Required on all function parameters and return values
- **Docstrings**: Triple quotes, descriptive format for all public functions
- **Union Types**: Use `|` syntax (Python 3.10+): `str | None` instead of `Optional[str]`

### Naming Conventions
- **Classes**: PascalCase (`MorphologyService`, `UserResponse`)
- **Functions/Variables**: snake_case (`get_db`, `analyze_word`)
- **Constants**: UPPER_SNAKE_CASE (`CORS_ORIGINS`, `SECRET_KEY`)
- **Private Methods**: Prefix with underscore (`_analyze_greek_word`)
- **Configuration Classes**: Descriptive suffix (`LLMSettings`, `DatabaseSettings`)

## Type System Guidelines

### Type Hints (Required Everywhere)
```python
def process_text(
    text: str, 
    language: Language,
    options: Dict[str, str] | None = None
) -> Dict[str, any]:
    """Process text with given options."""
    pass

def optional_param(data: Optional[List[str]] = None) -> None:
    """Function with optional parameter."""
    pass
```

### Common Patterns
- Use `Dict`, `List`, `Optional` from typing module
- Return `Dict[str, any]` for API responses
- Use `Language` enum instead of string literals
- Use `bool` for boolean values, not `0/1` or `"true"/"false"`

## Error Handling Standards

### Logging Patterns (Always Include Context)
```python
logger = logging.getLogger(__name__)

try:
    result = perform_operation()
    return result
except Exception as e:
    logger.error(f"Error processing '{input_data}': {e}")
    raise HTTPException(
        status_code=500, 
        detail=f"Failed to process data: {str(e)}"
    )
```

### API Error Responses
```python
# Use appropriate HTTP status codes
if not found:
    raise HTTPException(status_code=404, detail="Item not found")

if validation_error:
    raise HTTPException(status_code=422, detail="Invalid input")

if permission_denied:
    raise HTTPException(status_code=403, detail="Access denied")
```

### Service Error Handling
```python
def analyze_word(word: str, language: Language) -> Dict:
    try:
        # Primary operation
        result = llm_service.analyze(word, language)
        return result
    except Exception as e:
        logger.warning(f"Primary service failed for '{word}': {e}")
        # Graceful fallback
        return fallback_analysis(word, language)
```

## Database Patterns

### SQLAlchemy 2.0+ Usage
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

def get_literary_text(db: Session, text_id: int) -> LiteraryText | None:
    """Get literary text by ID."""
    stmt = select(LiteraryText).where(LiteraryText.id == text_id)
    return db.scalar(stmt)

def create_text(db: Session, text_data: Dict) -> LiteraryText:
    """Create new literary text."""
    text = LiteraryText(**text_data)
    db.add(text)
    db.commit()
    db.refresh(text)
    return text
```

### Bulk Operations (Preferred for Performance)
```python
from sqlalchemy.dialects.postgresql import insert

def bulk_create_texts(db: Session, texts: List[Dict]) -> None:
    """Bulk create texts with conflict handling."""
    stmt = (
        insert(LiteraryText)
        .values(texts)
        .on_conflict_do_nothing(index_elements=["local_id"])
    )
    db.execute(stmt)
    db.commit()
```

## Configuration Patterns

### Environment-Based Settings
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class ServiceSettings(BaseSettings):
    """Service configuration."""
    
    BASE_URL: str = "http://localhost:8080"
    TIMEOUT: int = 30
    ENABLED: bool = True
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="SERVICE_",
    )
```

## Testing Standards

### Test Structure
```python
import unittest
from unittest.mock import patch

class TestService(unittest.TestCase):
    """Unit tests for service functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = Service()
    
    def test_method_success(self):
        """Test successful operation."""
        result = self.service.method("input")
        self.assertEqual(result, "expected")
    
    @patch.dict(os.environ, {"SERVICE_URL": "test-url"})
    def test_with_env_override(self):
        """Test with environment variable override."""
        # Test implementation
        pass
```

## Important Project-Specific Rules

### Database Models
- Always use `Language` enum, never string literals
- Separate `LiteraryText` (for literary texts) from `Inscription` (for PHI inscriptions)
- Use `TextMetadata` for shared metadata across language versions
- All models must inherit from `Base` in `database.py`

### API Development
- All routers must use `APIRouter` with descriptive prefix
- Use Pydantic models for request/response validation
- Include proper HTTP status codes in error responses
- Always add logging with request context

### Script Development
- Use absolute imports: `from config import settings`
- Include comprehensive error handling and logging
- Use dataclasses for configuration (`@dataclass`)
- Implement batched processing for performance
- Always include `if __name__ == "__main__":` CLI interface

### Environment Variables
- Use `ENV_PREFIX_` naming convention in settings classes
- Provide sensible defaults for all configuration
- Never hardcode URLs, credentials, or paths
- Use `.env` file for local development

## Code Review Checklist

Before submitting code, verify:

- [ ] Code formatted with `uv run black .`
- [ ] All tests pass: `pytest`
- [ ] Type hints on all function signatures
- [ ] Error handling with proper logging
- [ ] Documentation for public functions
- [ ] No hardcoded values (use configuration)
- [ ] Database operations use proper transactions
- [ ] API endpoints include appropriate error responses

## Working with This Codebase

When making changes:
1. Always run tests before and after changes
2. Use existing patterns and conventions
3. Follow the import organization strictly
4. Include context in all log messages
5. Test with realistic data volumes
6. Check performance for database operations
7. Verify environment variable handling

This codebase prioritizes maintainability, type safety, and performance. Follow these guidelines to ensure consistency and quality.