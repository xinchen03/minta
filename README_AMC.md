# Minta — Agent Memory Challenge (Cycle 2) Submission

## System

- **Name**: Minta — the context quality layer for AI agents
- **Version**: `amc-2026-cycle2-v1`
- **Repository**: https://github.com/xinchen03/minta
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

## Known Boundaries

- Long-document exact-entity reference (CLBench-style) and ordering-type
  list questions are areas of acknowledged difficulty in local, non-official
  rehearsal.
- Full evaluation results will be reported by the platform; no private
  benchmark data, gold answers or credentials are included in this repository.

## Data / Privacy

- Evaluation data is held in-memory per container; 30-day TTL default,
  log discipline: no request bodies, memory content, queries or keys logged.
- Red-line self-checks are enforced by tests shipped in `server/tests/`.
