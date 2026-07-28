# Helios_v3 Security Best Practices Report

**Date:** 2026-05-12
**Scope:** Full-stack security audit of Helios_v3 (Python/FastAPI backend + React/TypeScript frontend)
**References:** OWASP Cheat Sheet Series, FastAPI Security Spec, React Security Spec

---

## Executive Summary

Helios_v3 has **5 critical**, **4 high**, and **3 medium** severity security findings. The most urgent issues are: live OAuth credentials exposed in `.env`, debug mode enabled in production configuration, a hardcoded frontend auth bypass, wildcard CORS with credentials, and a placeholder JWT signing key. These issues collectively mean that if the application is deployed as-is, it would be trivially exploitable.

---

## Findings

### CRITICAL

---

#### SEC-001: Live secrets committed in `.env` file

**Rule:** GO-CONFIG-001
**Severity:** Critical
**Location:** `.env:20-21`

**Evidence:**
```
GOOGLE_CLIENT_ID="9074946723760-19o3he5i3301972rmie23fper847sk8t.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="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"
POSTGRES_PASSWORD=changeme
```

**Impact:** The Google OAuth client secret is a live credential. Anyone with this secret can impersonate the application's OAuth flow, potentially hijacking user accounts. The database password `changeme` is trivially guessable. Although `.gitignore` includes `.env`, the file exists on disk and could be accidentally committed or exposed.

**Fix:** Rotate the Google OAuth credentials immediately in the Google Cloud Console. Set a strong, random database password. Ensure `.env` is never committed.

---

#### SEC-002: Debug mode enabled in production configuration

**Rule:** FASTAPI-DEPLOY-002
**Severity:** Critical
**Location:** `.env:10,17`, `backend/src/main.py:41-43`, `backend/src/config.py:92`

**Evidence:**
```python
# .env
DEBUG=True

# main.py:41-43
app = FastAPI(
    title=settings.misc.APP_NAME,
    debug=settings.misc.DEBUG,
    docs_url="/docs" if settings.misc.DEBUG else None,
    redoc_url="/redoc" if settings.misc.DEBUG else None,
)

# config.py:92
DEBUG: bool = True  # Set to False in production
```

**Impact:** Debug mode exposes interactive API docs (`/docs`, `/redoc`), detailed error tracebacks to clients, and enables the auth bypass in the middleware. An attacker can learn internal API structure, database schemas, and stack traces.

**Fix:** Set `DEBUG=False` in `.env` for production. Change the default in `config.py` to `False`.

---

#### SEC-003: Frontend authentication bypass hardcoded

**Rule:** REACT-AUTH-001
**Severity:** Critical
**Location:** `frontend/src/contexts/AuthContext.tsx:6,26-30`

**Evidence:**
```typescript
// DEV MODE: Set to false for production with Google OAuth
const DEV_MODE = true;

// In initAuth:
if (DEV_MODE) {
    console.warn('[Auth] DEV MODE: Using mock user, skipping authentication');
    setUser({ id: 1, email: 'dev@helios.local', created_at: new Date().toISOString() });
    setIsLoading(false);
    return;
}
```

**Impact:** The frontend completely bypasses authentication regardless of the backend state. Even if backend auth is fixed, the frontend will accept any request as authenticated. This is a hardcoded constant that must be manually changed before deployment.

**Fix:** Replace `const DEV_MODE = true` with `const DEV_MODE = import.meta.env.DEV;` which is `true` only during Vite dev server and `false` in production builds.

---

#### SEC-004: Wildcard CORS with credentials

**Rule:** FASTAPI-CORS-001
**Severity:** Critical
**Location:** `.env:18`, `backend/src/main.py:57-63`

**Evidence:**
```python
# .env
CORS_ORIGINS=["*"]

# main.py:57-63
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.misc.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Impact:** `allow_origins=["*"]` with `allow_credentials=True` allows any website to make credentialed cross-origin requests to the API. An attacker's site can steal user data and perform actions on behalf of authenticated users. While most CORS middleware rejects this specific combination, the intent is clearly insecure.

**Fix:** Replace with explicit origin allowlist matching the actual frontend URL(s).

---

#### SEC-005: Placeholder JWT signing key

**Rule:** FASTAPI-AUTH-004
**Severity:** Critical
**Location:** `.env:16`, `backend/src/config.py:72`

**Evidence:**
```
# .env
SECRET_KEY="your-secret-key-change-in-production"

# config.py:72
SECRET_KEY: str = "dev-secret-key-change-in-production"
```

**Impact:** Anyone who knows this placeholder value (which is in the source code) can forge valid JWT tokens for any user, including admin accounts. This completely breaks authentication integrity.

**Fix:** Generate a cryptographically random key: `openssl rand -hex 32`. Update both `.env` and the default in `config.py`.

---

### HIGH

---

#### SEC-006: JWT token exposed in URL after OAuth callback

**Rule:** FASTAPI-AUTH-002
**Severity:** High
**Location:** `backend/src/routers/auth.py:127`

**Evidence:**
```python
redirect_url = f"{frontend_url}/?token={access_token}"
```

**Impact:** The JWT token is placed in the URL query parameter. It will appear in: browser history, HTTP `Referer` headers on subsequent requests, server access logs, proxy/CDN logs, and potentially shared URLs. This is a classic token leakage vector.

**Fix:** Use the URL fragment (`#token=...`) instead of query parameter (`?token=...`). Fragments are never sent to servers in HTTP requests.

---

#### SEC-007: Secrets and tokens logged in plaintext

**Rule:** GO-CONFIG-001
**Severity:** High
**Location:** `backend/src/utils/security.py:58-59`, `backend/src/routers/auth.py:63-64,118`

**Evidence:**
```python
# security.py:58-59
logger.debug(
    f"Verifying token with SECRET_KEY: {settings.auth.SECRET_KEY[:10]}... and algorithm: {settings.auth.ALGORITHM}"
)

# auth.py:63-64
logger.info(
    f"Received token (length {len(token)}): {token[:50]}..."
)

# auth.py:118
logger.info(f"Token preview: {access_token[:80]}...")
```

**Impact:** The JWT signing key prefix and token contents are logged at INFO/DEBUG level. In production, logs are often aggregated in centralized systems with broad access. An attacker with log access can extract tokens and key material.

**Fix:** Remove all logging of secrets and token values. Log only non-sensitive metadata (user ID, token expiry).

---

#### SEC-008: Session cookie missing `https_only` flag

**Rule:** FASTAPI-SESS-001
**Severity:** High
**Location:** `backend/src/main.py:48-54`

**Evidence:**
```python
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.auth.SECRET_KEY,
    max_age=3600,
    same_site="lax",
    https_only=False,  # Set to True in production with HTTPS
)
```

**Impact:** The session cookie will be sent over unencrypted HTTP connections, making it vulnerable to man-in-the-middle interception. The comment acknowledges this should be True in production but it is hardcoded to False.

**Fix:** Make `https_only` conditional: `https_only=not settings.misc.DEBUG`.

---

#### SEC-009: Auth bypass and dev-login accessible without proper gating

**Rule:** FASTAPI-AUTH-001
**Severity:** High
**Location:** `backend/src/middleware/auth.py:46-57`, `backend/src/routers/auth.py:164-176`

**Evidence:**
```python
# middleware/auth.py:46-57
if settings.misc.DEBUG:
    logger.info("DEV MODE: No credentials provided, using dev user")
    dev_user = db.query(User).filter(User.email == "dev@helios.local").first()
    if not dev_user:
        dev_user = User(email="dev@helios.local", oauth_provider="dev", oauth_id="dev_id")
        db.add(dev_user)
        db.commit()
        db.refresh(dev_user)
    return dev_user

# routers/auth.py:173
if settings.auth.GOOGLE_CLIENT_ID and not settings.misc.DEBUG:
    raise HTTPException(status_code=403, detail="Dev login is only available in development mode")
```

**Impact:** The middleware auth bypass triggers on `DEBUG=True` alone, regardless of whether Google OAuth is configured. The dev-login endpoint check is also weak — if `GOOGLE_CLIENT_ID` is empty (which it shouldn't be, but could be misconfigured), dev-login is accessible even with `DEBUG=False`.

**Fix:** Gate both features behind `DEBUG=True` AND absence of Google credentials. Ensure dev-login is completely disabled in production.

---

### MEDIUM

---

#### SEC-010: Excessive JWT token lifetime (7 days)

**Rule:** FASTAPI-AUTH-004
**Severity:** Medium
**Location:** `backend/src/config.py:74`

**Evidence:**
```python
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 week
```

**Impact:** A stolen JWT token remains valid for 7 days with no revocation mechanism. This gives attackers a large window to exploit compromised tokens.

**Fix:** Reduce to 24 hours (1440 minutes). Consider implementing a refresh token flow for longer sessions.

---

#### SEC-011: PostgreSQL port exposed to host

**Rule:** GO-DEPLOY-002
**Severity:** Medium
**Location:** `docker-compose.yml:10-11`

**Evidence:**
```yaml
ports:
  - "5432:5432"
```

**Impact:** The database port is accessible from the host machine and potentially from the network. In production, this increases the attack surface for database brute-force and exploitation.

**Fix:** Remove the `ports` mapping. Internal services should communicate via Docker networking only.

---

#### SEC-012: Missing security headers in Caddy

**Rule:** REACT-HEADERS-001
**Severity:** Medium
**Location:** `frontend/Caddyfile:23-28`

**Evidence:**
```
header {
    X-Content-Type-Options "nosniff"
    -Server
}
```

**Impact:** Missing `X-Frame-Options` allows clickjacking attacks. Missing `Referrer-Policy` causes token URLs (SEC-006) to leak via referrer headers. Missing `Content-Security-Policy` removes a key XSS defense layer.

**Fix:** Add `X-Frame-Options "DENY"`, `Referrer-Policy "strict-origin-when-cross-origin"`, and a basic CSP.

---

## Prioritized Fix Order

1. SEC-001: Rotate `.env` secrets (Critical)
2. SEC-005: Generate real `SECRET_KEY` (Critical)
3. SEC-002: Set `DEBUG=False` (Critical)
4. SEC-003: Fix frontend `DEV_MODE` (Critical)
5. SEC-004: Fix CORS origins (Critical)
6. SEC-007: Remove secret logging (High)
7. SEC-006: Fix token-in-URL leakage (High)
8. SEC-008: Fix session cookie flags (High)
9. SEC-009: Gate dev features properly (High)
10. SEC-010: Reduce token lifetime (Medium)
11. SEC-011: Remove DB port exposure (Medium)
12. SEC-012: Add security headers (Medium)
