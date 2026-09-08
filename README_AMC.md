# Minta — Second Agent Memory Challenge (2026) Submission

This document describes the competition-specific evaluation snapshot. The
regular `main` branch remains the continuously updated public product line;
the immutable competition tag is created only after the candidate passes its
final smoke and reproducibility checks.

## System

- **Name**: Minta — the context quality layer for AI agents
- **Candidate version**: `amc-2026-cycle2-v2`
- **Repository**: https://github.com/xinchen03/minta
- **Track / division**: Textual Memory / Academic Methods
- **Submission type**: code submission (platform builds and deploys per the
  Docker instructions below)

## Running

```bash
docker build -t minta-eval .
docker run --rm -p 8000:8000 -v minta-data:/data minta-eval
```

The container runs only the evaluation adapter (Add/Search, port 8000).
Models are baked during build — no runtime network dependency.

## API Contract

| Endpoint | Behavior |
|---|---|
| `POST /add` | Synchronous ingest; request-id idempotent; echoes `success` / `request_id` / `user_id` / `session_id`; HTTP 200 only after persistence + immediate retrievability |
| `POST /search` | User-id-scoped only; `top_k ≤ 100`; returns ordered `data[]` with `id` / `content` / optional `score` / `created_at`; no answer generation |
| `GET /health` | No-auth liveness (same origin as `/add`, port 8000) |
| Auth | Optional env-gated key: set `MINTA_EVAL_API_KEY` → `X-Api-Key`, `Authorization: Bearer`, or `Authorization: Token` is required on `/add` and `/search` (401 otherwise); unset = no auth. `/health` always remains open. |
| Errors | `{"detail":{"reason":"..."}}` shape for business errors; no 202 / status endpoints / memory_ids |

## Model / Method Disclosure (originality statement)

- **Architecture**: retrieval-only memory adapter. Evidence is stored as raw
  messages with minimal provenance envelope; nothing is rewritten, merged or
  hidden at search time — re-ranking signals operate on ordering only.
- **Retrieval mainline**: dense seed → same-chunk neighbour window → dedupe →
  fill `min(top_k, 100)`; local 88MB cross-encoder re-rank pass and a
  time-expression boost are enabled as mechanism knobs (env gated).
- **Zero-LLM**: no model-backed rewriting during Add/Search; all retrievable
  content is verbatim evidence.
- **Third-party**: SQLAlchemy / FastAPI / sentence-transformers / apscheduler
  (standard public libraries, used per their licenses).

### Pre-submission rule confirmation

The second-event notice states that participants implement memory Add/Search
while the platform controls Answer and Eval, and does not prescribe the
internal database, index, vector model, or architecture. The live Full
checklist also contains a `gpt-4o-mini` item. This candidate therefore remains
zero-LLM and **must not be submitted for Full until the organizer confirms in
writing which requirement governs the second event**.

## Known Boundaries

- Long-document exact-entity reference (CLBench-style) and ordering-type
  list questions are areas of acknowledged difficulty in local, non-official
  rehearsal.
- Full evaluation results will be reported by the platform; no private
  benchmark data, gold answers or credentials are included in this repository.
- Benchmark numbers that appear in repo docs (A/B matrices, proxy tables) are
  **local proxy-caliber methodology records** (DeepSeek judge, relative-only)
  — they describe configuration choices, not official standings.

## Data / Privacy

- Evaluation data is persisted in the container's SQLite evaluation database
  so synchronous Add results remain immediately searchable. A 720-hour
  (30-day) TTL cleanup is enabled by default; destroying the evaluation
  container/volume deletes the run data sooner.
- Log discipline: no request bodies, memory content, queries or keys are
  logged.
- Red-line self-checks are enforced by tests shipped in `server/tests/`.
