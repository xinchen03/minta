---
name: minta-audit
description: Systematic security and privacy audit for Minta codebase. Scans for hardcoded secrets, IP logging, weak CORS, missing rate limits, exposed credentials. Use when preparing code for public release, before deployment, after adding new routes, or when user says "安全检查" / "隐私审计" / "公开版".
---

# Minta Audit

Security and privacy audit for the Minta codebase. Every finding must be fixed before public release.

## Phase 1 — Secret Scan

Run these checks against the target directory:

```bash
# Hardcoded passwords / API keys
grep -rn "minta2026\|api_key.*=\|password.*=\|secret.*=" --include="*.py" .

# JWT secrets
grep -rn "SECRET_KEY\|JWT_SECRET\|_FALLBACK.*=" --include="*.py" .

# Email addresses
grep -rn "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" --include="*.py" .

# IP addresses / host logging
grep -rn "client\.host\|request\.client" --include="*.py" .
```

## Phase 2 — Configuration Audit

| Check | What to look for |
|-------|-----------------|
| Database URL | No hardcoded credentials; use env var with no fallback |
| API Key | No hardcoded default; generate random if unset |
| JWT Secret | No static fallback in production; `secrets.token_urlsafe(32)` |
| SMTP | No hardcoded user/pass; warn at runtime, don't crash |
| CORS | Default strict (`production`); `*` only in `development` |

## Phase 3 — Network Security

| Check | Implementation |
|-------|---------------|
| Rate limiting | Login: 10/60s; Register: 3/300s; Email: 3/120s |
| Body size limit | 10 MB max request body |
| Security headers | X-Content-Type-Options, X-Frame-Options, HSTS, CSP |
| Docs exposure | `/docs` hidden in production |
| Request logging | No IP addresses logged |

## Phase 4 — Data Privacy

| Check | Implementation |
|-------|---------------|
| User data export | GET /api/user/export (authenticated) |
| User data delete | DELETE /api/user/me (authenticated) |
| Privacy notice | Frontend page accessible |
| Consent form | Available before data collection |

## Output

After audit, produce:
1. List of findings with severity (CRITICAL / HIGH / MEDIUM / LOW)
2. Each finding: file:line, what's exposed, fix applied
3. Final status: CLEAN or list remaining issues
