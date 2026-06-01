# Configuration Guide

> 🌐 [中文版](configuration_zh.md) | English

Everything you can configure in Minta — environment variables, database, email, CORS, and more.

---

## Table of Contents

1. [Quick Start: .env File](#quick-start-env-file)
2. [All Environment Variables](#all-environment-variables)
3. [Database Setup](#database-setup)
4. [Email Verification (SMTP)](#email-verification-smtp)
5. [CORS Configuration](#cors-configuration)
6. [API Key Management](#api-key-management)
7. [Autopilot Settings](#autopilot-settings)
8. [Production Checklist](#production-checklist)

---

## Quick Start: .env File

Minta loads configuration from a `.env` file in the project root. Copy the example and edit:

```bash
cp .env.example .env
```

### Minimal Production .env

```bash
# Required
MINTA_DATABASE_URL=sqlite:///./minta.db
MINTA_JWT_SECRET=<generate a random string>
MINTA_API_KEY=<generate a random string>
MINTA_ENV=production

# Optional (for email verification)
MINTA_SMTP_HOST=smtp.qq.com
MINTA_SMTP_PORT=465
MINTA_SMTP_USER=your-email@qq.com
MINTA_SMTP_PASS=your-smtp-password
```

### Generate Secure Secrets

```bash
# Generate a JWT secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate an API key
python -c "import secrets; print('minta_' + secrets.token_urlsafe(32))"
```

> ⚠️ **Important:** If you don't set `MINTA_JWT_SECRET` in production, Minta will **refuse to start** with a `RuntimeError`. This is intentional — the auto-generated fallback is only for development.

---

## All Environment Variables

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MINTA_ENV` | `production` | `production` or `development`. Dev mode enables `/docs` (Swagger UI), permissive CORS, and more verbose logging. |
| `MINTA_DATABASE_URL` | `sqlite:///./minta.db` | Database connection string. Supports SQLite, MySQL, and PostgreSQL. |
| `MINTA_JWT_SECRET` | auto-generated (dev only) | Secret key for signing JWT tokens. **Required in production.** |
| `MINTA_API_KEY` | auto-generated | API key for programmatic access and MCP tools. Auto-generated on first run if not set. |

### Email (SMTP)

| Variable | Default | Description |
|----------|---------|-------------|
| `MINTA_SMTP_HOST` | `smtp.qq.com` | SMTP server hostname |
| `MINTA_SMTP_PORT` | `465` | SMTP port (465 for SSL, 587 for TLS) |
| `MINTA_SMTP_USER` | `""` (empty) | SMTP username / email address |
| `MINTA_SMTP_PASS` | `""` (empty) | SMTP password or authorization code |

> 💡 **Note:** Without SMTP configured, email verification auto-passes in development. A warning is printed at startup.

### CORS

| Variable | Default | Description |
|----------|---------|-------------|
| `MINTA_CORS_ORIGINS` | `http://localhost:8772` | Comma-separated list of allowed origins. Only used in `production` mode. Dev mode allows all origins (`*`). |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `MINTA_AUTOPILOT_ENABLED` | `true` | Enable/disable the autopilot memory management |

### Advanced

| Variable | Default | Description |
|----------|---------|-------------|
| `MINTA_API_URL` | `http://127.0.0.1:8772` | Minta server URL (used internally by MCP HTTP server) |
| `MCP_HTTP_PORT` | `18721` | Port for the MCP HTTP server |
| `MINTA_JWT_EXPIRE_MINUTES` | `1440` (24 hours) | JWT token expiry duration |

---

## Database Setup

### SQLite (Default — Zero Configuration)

```bash
# .env
MINTA_DATABASE_URL=sqlite:///./minta.db
```

No additional setup needed. The database file is created automatically in the project root on first run.

> ⚠️ SQLite is perfect for personal use. For multi-user or high-concurrency scenarios, use MySQL or PostgreSQL.

### MySQL

```bash
# .env
MINTA_DATABASE_URL=mysql+pymysql://user:password@localhost:3306/minta
```

**Requirements:**
```bash
pip install pymysql
```

**Setup steps:**
```sql
CREATE DATABASE minta CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'minta'@'localhost' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON minta.* TO 'minta'@'localhost';
FLUSH PRIVILEGES;
```

Tables are created automatically on first startup (`Base.metadata.create_all()`).

### PostgreSQL

```bash
# .env
MINTA_DATABASE_URL=postgresql://user:password@localhost:5432/minta
```

**Requirements:**
```bash
pip install psycopg2-binary
```

**Setup steps:**
```sql
CREATE DATABASE minta;
CREATE USER minta WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE minta TO minta;
```

---

## Email Verification (SMTP)

Minta can send email verification codes during registration. This requires SMTP configuration.

### QQ Mail Setup (Recommended for Chinese Users)

1. Log in to QQ Mail → Settings → Account
2. Enable **POP3/SMTP service**
3. Copy the **authorization code** (not your login password)
4. Configure in `.env`:

```bash
MINTA_SMTP_HOST=smtp.qq.com
MINTA_SMTP_PORT=465
MINTA_SMTP_USER=your-email@qq.com
MINTA_SMTP_PASS=your-authorization-code
```

### Gmail Setup

1. Enable **2-Factor Authentication** on your Google Account
2. Generate an **App Password** (Google Account → Security → App passwords)
3. Configure in `.env`:

```bash
MINTA_SMTP_HOST=smtp.gmail.com
MINTA_SMTP_PORT=587
MINTA_SMTP_USER=your-email@gmail.com
MINTA_SMTP_PASS=your-app-password
```

### Testing Email

```bash
# After configuring SMTP, register a new user and check for the verification email
minta start
# Then POST to /api/auth/register
```

If SMTP is not configured, Minta prints a warning and auto-passes verification in development mode.

---

## CORS Configuration

### Development (Permissive)

```bash
MINTA_ENV=development
# CORS: allows all origins (*)
# /docs: enabled
```

### Production (Strict)

```bash
MINTA_ENV=production
MINTA_CORS_ORIGINS=http://localhost:8772,https://your-domain.com
# CORS: only the listed origins
# /docs: hidden
```

### Common CORS Scenarios

**Local development only:**
```bash
MINTA_CORS_ORIGINS=http://localhost:8772
```

**With a reverse proxy (Nginx):**
```bash
MINTA_CORS_ORIGINS=https://minta.your-domain.com
```

**Multiple origins:**
```bash
MINTA_CORS_ORIGINS=http://localhost:8772,http://localhost:3000,https://minta.example.com
```

> ⚠️ Never use `MINTA_CORS_ORIGINS=*` in production. This is a security risk. Use `MINTA_ENV=development` if you need permissive CORS temporarily.

---

## API Key Management

### Built-in API Key

On first run, Minta auto-generates an API key and saves it to `.minta_api_key` (file permissions `0600`). You can override it:

```bash
MINTA_API_KEY=minta_YOUR_CUSTOM_KEY_HERE
```

### Creating Additional API Keys

1. Log in to the dashboard
2. Go to **Settings → API Keys**
3. Click **Create New Key**
4. Copy the key immediately — it's shown only once

### Using API Keys

```bash
# In HTTP requests
curl -H "X-API-Key: minta_..." http://localhost:8772/api/contextObjects/stats

# In MCP tools (automatic)
# The MCP server reads MINTA_API_KEY from the environment
```

### Revoking Keys

```bash
# Via API
curl -X DELETE -H "X-API-Key: minta_..." http://localhost:8772/api/keys/{key_id}

# Or in the dashboard → Settings → API Keys → Revoke
```

---

## Autopilot Settings

The **Autopilot** is Minta's memory management agent. It automatically reads context before your AI conversations and suggests memory updates afterward.

### Enable/Disable

```bash
# In .env
MINTA_AUTOPILOT_ENABLED=true   # Enable (default)
MINTA_AUTOPILOT_ENABLED=false  # Disable
```

### How It Works

1. **Preflight** (`/api/autopilot/preflight`): Analyzes your message and retrieves relevant memories
2. **Postflight** (`/api/autopilot/postflight`): Analyzes the conversation and decides whether to:
   - Write new memory
   - Capture a counter-example (correction)
   - Update existing memory

### Decision Logging

Autopilot decisions are logged for review:
- `GET /api/autopilot/logs` — View recent decisions
- `GET /api/autopilot/status` — Check autopilot health

---

## Production Checklist

Before deploying Minta for production use:

- [ ] Set `MINTA_ENV=production`
- [ ] Generate a strong `MINTA_JWT_SECRET` (≥32 bytes random)
- [ ] Generate a strong `MINTA_API_KEY`
- [ ] Configure `MINTA_CORS_ORIGINS` to your actual domain(s)
- [ ] Set up a proper database (MySQL or PostgreSQL, not SQLite)
- [ ] Configure SMTP for email verification
- [ ] Place Minta behind a reverse proxy (Nginx/Caddy) with HTTPS
- [ ] Review the security headers (HSTS, X-Frame-Options, etc. are on by default)
- [ ] Run `minta-audit` (if using the development toolkit)
- [ ] Read [SECURITY.md](../../SECURITY.md) for vulnerability reporting

### Nginx Reverse Proxy Example

```nginx
server {
    listen 443 ssl;
    server_name minta.example.com;

    ssl_certificate /etc/ssl/certs/minta.pem;
    ssl_certificate_key /etc/ssl/private/minta.key;

    location / {
        proxy_pass http://127.0.0.1:8772;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> 💡 Minta binds to `127.0.0.1` by default, so it's safe to run behind a reverse proxy without additional firewall rules.
