# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Minta, please report it privately via:

- **Email:** [xxinchen03@gmail.com]  <!-- TODO: replace with your actual email -->
- **GitHub Security Advisory:** Use the "Report a vulnerability" button on the [Security](https://github.com/xinchen03/minta/security) tab

Please do **not** open a public issue.

### What to include

- A clear description of the vulnerability and its impact
- Steps to reproduce (proof-of-concept code, screenshots, or logs)
- Affected versions (if known)
- Any suggested mitigations

## Our Commitment

| Commitment | Timeline |
|-------------|----------|
| Acknowledge receipt | Within **48 hours** |
| Triage and confirm severity | Within **5 business days** |
| Release a patch | Within **30 days** (critical: faster) |
| Publish an advisory | When the patch is released |

We will keep you informed of progress throughout the process. If we believe the vulnerability is a duplicate or out of scope, we will explain our reasoning.

## Coordinated Disclosure

We ask that you:

- **Do not publicly disclose** the vulnerability until we have released a fix and published a security advisory
- Give us reasonable time to investigate and patch before the 30-day window expires
- Delete any sensitive data obtained during research once the issue is resolved

We are happy to credit you in the advisory (with your permission) and link to any write-up you publish after the fix is released.

## Scope

Minta is a local-first personal context layer. The following are in scope:

- RCE, arbitrary file read/write via the Data API (port 8772), Autopilot (port 18730), or MCP HTTP endpoint (port 18721)
- Authentication bypass, privilege escalation
- SQL injection, command injection
- Sensitive data exposure (API keys, credentials in logs/configs)
- Cross-origin attacks affecting the local dashboard

### Out of scope

- Attacks requiring physical access to the user's machine
- Social engineering
- Denial-of-service against localhost services
- Issues that require the attacker to already have shell access on the host

## Supported Versions

Only the latest release receives security patches. We recommend always running `main` or the most recent tagged release.

| Version | Supported |
|---------|-----------|
| Latest release / `main` | ✅ |
| Older versions | ❌ |
