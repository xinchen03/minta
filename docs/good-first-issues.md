# Good First Issues

Copy-paste ready. Go to https://github.com/xinchen03/minta/issues/new and create each one.

---

## Issue 1: Translate Chinese comments in server code to English

**Title:** Translate remaining Chinese comments/docstrings to English

**Labels:** `good first issue` `documentation`

**Body:**

Several Python files under `server/` still contain Chinese comments and docstrings. This makes the codebase harder for international contributors to navigate.

### Files to check
- `server/minta_mcp.py`
- `server/minta_mcp_http.py`
- `server/services/` (various)
- `server/routers/` (various)

### What to do
1. Find Chinese comments/docstrings
2. Translate to idiomatic English
3. Preserve all code logic — only touch comments
4. Run `python -m pytest server/tests/ -v` to confirm nothing broke

### Example
```python
# Before:
# 复用核心逻辑

# After:
# Reuse core logic
```

---

## Issue 2: Add more demo scenarios to seed_demo.py

**Title:** Add more realistic demo scenarios to seed_demo.py

**Labels:** `good first issue` `enhancement`

**Body:**

`server/seed_demo.py` currently seeds demo data for the `/story` page. We need more scenarios that show real-world memory problems (especially staleness and redundancy).

### What to do
1. Read `server/seed_demo.py` to understand the format
2. Add 3–5 new demo entries that demonstrate:
   - A stale memory (something true before but not anymore)
   - A redundant pair (same info in two different contexts)
   - A fragmentation case (related facts scattered across entries)
3. Test: `minta start` → open `/story` → run "Run Memory Health Scan"

### Inspiration
- A startup's tech stack evolving (REST → GraphQL → tRPC)
- A team growing from 3 to 10 people
- A project being renamed mid-development

---

## Issue 3: Add English entity extraction patterns to entity_linker.py

**Title:** Add English domain entity extraction patterns to entity_linker.py

**Labels:** `good first issue` `enhancement`

**Body:**

`server/services/entity_linker.py` currently has stronger support for Chinese entity patterns. We need equivalent patterns for English technical content.

### What to do
1. Read `server/services/entity_linker.py`
2. Add regex patterns for English entities:
   - Framework names (React, Django, Spring Boot, etc.)
   - Database names (PostgreSQL, MongoDB, Redis, etc.)
   - Tool names (Docker, Kubernetes, Webpack, etc.)
3. Add test cases in `server/tests/`
4. Run `python -m pytest server/tests/ -v`

---

## Issue 4: Improve test coverage for lifecycle_scanner

**Title:** Add unit tests for lifecycle_scanner edge cases

**Labels:** `good first issue` `tests`

**Body:**

`server/services/lifecycle_scanner.py` is the core memory health engine but has no dedicated unit tests.

### What to test
1. Staleness: recently-used objects should NOT be flagged
2. Redundancy: objects at exactly 0.80 similarity boundary
3. Fragmentation: fewer than threshold items should NOT trigger
4. Conflict: non-conflicting recommendations should NOT flag
5. Empty database: scanner handles zero objects gracefully

### What to do
1. Create `server/tests/test_lifecycle_scanner.py`
2. Use a test SQLite database (create/setup/teardown per test)
3. Add at least 8 test cases
4. Run `python -m pytest server/tests/ -v -k lifecycle`
