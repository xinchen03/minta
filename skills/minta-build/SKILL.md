---
name: minta-build
description: Structured engineering workflow for Minta — verify current state, plan small vertical slice, implement, verify again, commit. Use when building Minta features, fixing Minta bugs, or doing any implementation work on the Minta project.
---

# Minta Build

**Core principle**: Small vertical slices with verification at each step. Never implement in bulk without checking.

## Workflow

```
Verify current state → Plan ONE slice → Implement → Verify → Repeat
```

## Step 0 — Verify Current State

Before touching code:
- [ ] Run `curl http://127.0.0.1:8772/ping`
- [ ] Check what's actually broken vs what memory claims
- [ ] Read the relevant code, not old status files
- [ ] Query the database if relevant

**Memory files are point-in-time snapshots. Code and live system are authoritative.**

## Step 1 — Plan ONE Slice

Pick the smallest unit of work that:
- Has a clear pass/fail signal
- Can be implemented in < 30 minutes
- Produces observable change

Ask: "What's the ONE thing that, if done, makes a visible difference?"

## Step 2 — Implement

- Write the minimal code change
- No abstractions beyond what's needed
- No future-proofing
- One file at a time, verify each

## Step 3 — Verify

Use `minta-verify` checklist:
- [ ] Does the endpoint respond correctly?
- [ ] Does the frontend show the change?
- [ ] Are there any regressions? (Check /ping, /api/auth/login)
- [ ] No new hardcoded secrets

## Step 4 — Report

When done:
- What changed (file:line)
- What verification was done
- What's next

## Anti-Patterns

| Don't | Do |
|-------|-----|
| "Based on memory, X is done" | Check the live system |
| Implement all 3 tasks at once | One slice, verify, next slice |
| Report done without verification | Show the curl output |
| Add abstractions "for later" | YAGNI — add when needed |
| Read memory files as truth | Code > live system > memory files |

## Minta-Specific Rules

- Server code: `C:\Users\Lenovo\.claude\projects\C--Users-Lenovo\memory\server\`
- Frontend: `C:\Users\Lenovo\.claude\projects\C--Users-Lenovo\memory\web\src\`
- Public copy target: `C:\Users\Lenovo\Desktop\minta-public\`
- Skills: `D:/skill/` (master) + `~/.claude/skills/` (runtime)
- Database: MySQL at localhost:3306, database `minta`
- Services: 8772 (data), 18730 (autopilot), 18721 (MCP)
