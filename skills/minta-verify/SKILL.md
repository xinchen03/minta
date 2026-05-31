---
name: minta-verify
description: Before claiming work is complete, run a systematic verification loop — test endpoints, check live logs, confirm the system actually responds. Use when about to say "done" / "completed" / "fixed", before committing, before reporting status, or after any implementation that touches Minta server code.
---

# Minta Verify

**Core discipline**: Evidence before assertions. Never claim "done" without running the live system.

## The Feedback Loop

If you can't answer "how do I know it works?", you're not done.

1. **Identify the signal** — what observable behavior proves correctness?
2. **Run the check** — curl the endpoint, tail the log, query the DB
3. **Read the output** — do not assume; actually parse the response
4. **Compare against expected** — does the output match the claim?

## Verification Checklist

### Minta API
- [ ] `curl http://127.0.0.1:8772/ping` → `{"ok": true}`
- [ ] Login works: POST `/api/auth/login`
- [ ] Context read works (with token)
- [ ] Expert infer works (with token)
- [ ] MCP tools respond: POST `18721/mcp` with `tools/list`

### Minta Frontend
- [ ] `curl http://127.0.0.1:8772/` returns HTML (dist exists)
- [ ] New user can register and see non-blank page

### Database
- [ ] MySQL/SQLite accessible
- [ ] Tables exist: users, context_objects, slots, skills, inference_log

### Privacy/Security
- [ ] No hardcoded secrets in config.py (grep for passwords, API keys)
- [ ] No IP logging in production mode
- [ ] CORS not `*` in production

## Anti-Patterns

| Don't | Do |
|-------|-----|
| "The code looks right" | Run it and check the response |
| "The file exists" | Check its contents are correct |
| "It worked last time" | Test it now |
| "The other endpoints work so this one does too" | Test each independently |
| Read old memory files for status | Check live system |

## Red Flags

If any check fails, the task is NOT complete. Fix the issue, re-verify, then report.
