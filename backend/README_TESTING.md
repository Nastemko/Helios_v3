# Testing Guide for Helios Backend

This guide explains how to run and write tests for the Helios backend.

## Test Structure

```
backend/tests/
├── conftest.py              # Test configuration and fixtures
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_security.py     # Security utilities tests
│   ├── test_morphology_service.py  # Morphology service tests
│   └── test_config.py       # Configuration tests
└── integration/             # Integration tests (real dependencies)
    ├── test_database.py     # Database CRUD operations
    ├── test_text_endpoints.py  # Text API endpoints
    ├── test_annotation_endpoints.py  # Annotation API endpoints
    └── test_analysis_endpoints.py   # Word analysis endpoints
```

## Running Tests

### Install Test Dependencies

```bash
cd backend
uv sync --extra dev
```

### Run All Tests

```bash
uv run pytest
```

### Run Specific Test Suites

```bash
# Run only unit tests
uv run pytest tests/unit

# Run only integration tests
uv run pytest tests/integration

# Run a specific test file
uv run pytest tests/unit/test_security.py

# Run a specific test
uv run pytest tests/unit/test_security.py::TestPasswordHashing::test_password_hashing_and_verification
```

### Run Tests with Coverage

```bash
# Generate coverage report
uv run pytest --cov=src --cov-report=html --cov-report=term

# View HTML coverage report
open htmlcov/index.html
```

### Run Tests with Markers

```bash
# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Skip slow tests
uv run pytest -m "not slow"
```

### Verbose Output

```bash
# More detailed output
uv run pytest -v

# Even more detailed with full traceback
uv run pytest -vv --tb=long
```

## Test Philosophy

### Minimal Mocking

We minimize mocking to test real behavior:

- ✅ **Use Real Database**: SQLite in-memory for tests
- ✅ **Use Real Services**: CLTK for morphology, actual XML parsing
- ✅ **Use Real Framework**: FastAPI TestClient
- ❌ **Only Mock External APIs**: Google OAuth, external HTTP calls

### Test Categories

#### Unit Tests
- Fast (< 1 second each)
- Test single functions/classes
- No external dependencies
- Examples: security functions, config loading

#### Integration Tests
- Test multiple components working together
- Use real database and services
- Test API endpoints end-to-end
- Examples: CRUD operations, API endpoints

## Writing Tests

### Using Fixtures

Fixtures are defined in `conftest.py` and available to all tests:

```python
def test_example(db_session, test_user, sample_text):
    """
    db_session: Database session
    test_user: A test user
    sample_text: A sample text
    """
    # Your test code here
    pass
```

### Available Fixtures

- `db_session`: Database session for each test
- `client`: FastAPI test client
- `authenticated_client`: Test client with auth headers
- `test_user`: A test user in the database
- `auth_token`: Valid JWT token
- `sample_text`: A sample text
- `sample_segment`: A sample text segment
- `sample_annotation`: A sample annotation
- `multiple_texts`: Multiple texts for testing lists/search

### Example Unit Test

```python
def test_password_hashing():
    """Test password hashing works correctly."""
    password = "SecurePassword123"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong", hashed) is False
```

### Example Integration Test

```python
def test_create_annotation(authenticated_client, sample_segment):
    """Test creating an annotation via API."""
    data = {
        "text_id": sample_segment.text_id,
        "segment_id": sample_segment.id,
        "word": "test",
        "note": "Test note"
    }
    
    response = authenticated_client.post("/api/annotations", json=data)
    
    assert response.status_code == 200
    result = response.json()
    assert result["word"] == "test"
```

## Test Configuration

### pytest.ini

Test discovery and execution settings.

### .coveragerc

Coverage reporting configuration.

### Environment Variables

Tests use test-specific environment variables:

```bash
DATABASE_URL=sqlite:///:memory:  # In-memory database
SECRET_KEY=test_secret_key       # Test secret
DEBUG=True                       # Enable debug mode
```

## Continuous Integration

Tests run automatically on:
- Push to `main`, `develop`, or feature branches
- Pull requests to `main` or `develop`

See `.github/workflows/test.yml` for CI configuration.

## Coverage Goals

- **Unit Tests**: 80%+ coverage
- **Integration Tests**: 100% of critical paths
- **Overall**: 75%+ coverage

## Troubleshooting

### Tests are slow

Run only unit tests:
```bash
uv run pytest tests/unit
```

Or skip slow tests:
```bash
uv run pytest -m "not slow"
```

### Database errors

Ensure PostgreSQL service is running (for integration tests):
```bash
docker compose up -d postgres
```

### Import errors

Make sure dependencies are installed:
```bash
uv sync --extra dev
```

### CLTK download errors

CLTK may need to download models on first run. This is expected and only happens once.

## Best Practices

1. **Test naming**: Use descriptive names starting with `test_`
2. **One assertion focus**: Each test should verify one specific behavior
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Use fixtures**: Don't repeat setup code
5. **Test edge cases**: Empty inputs, invalid data, boundary conditions
6. **Test error handling**: Verify errors are handled gracefully
7. **Keep tests fast**: Unit tests should be < 1 second
8. **Test documentation**: Add docstrings explaining what is tested

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Testing Best Practices](https://docs.pytest.org/en/latest/goodpractices.html)

