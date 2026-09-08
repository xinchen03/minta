# Open-Source Boundary

Minta ships an **open research kernel** (`minta-open`, Apache-2.0) and a
**closed commercial control plane** (Minta-next / enterprise deployment).
This file is the source of truth for what belongs where.

## Layers

| Layer | Repository / delivery | Contains |
|---|---|---|
| Open research kernel | `minta-open` (Apache-2.0, free) | Conformal predictor, decision graph miner, Autopilot core logic, multi-signal retrieval, reranker, CLI, MCP base interface, web hub UI |
| Closed enhancement | Minta-next | Expert runtime, learning, dialogue, orchestration, research runtime, rule promotion, JEPA, complex evaluation & calibration |
| Commercial moat | closed / server-only | Proprietary data, domain knowledge packs, training & feedback corpora, enterprise governance, multi-tenancy, permission audit, managed service, SLA, team collaboration |
| Never published | never enters `minta-open` | User data, Chroma data, evaluation corpora, runtime logs, secrets, personal paths, internal commercial documents |

## Statement

The algorithmic modules listed above (conformal prediction, decision-graph
mining, Autopilot primitives, retrieval/reranking) are part of the
Apache-2.0 open research kernel. Commercial differentiation comes from the
proprietary runtime, domain assets, governance control plane, enterprise
deployment and continuous-learning capability — not from these modules
themselves. Their presence in this repo is a product-layering decision, not
a disclosure incident.

## Boundary rules

- Never commit: `docs/eval-proxy/runs/`, `data/`, `logs/`, `runtime/.minta_*`,
  `*.db`, `*.sqlite*`, `.env`, or any file containing credentials or
  personal paths.
- `minta-open main` is the curated public release. A future next-to-open export
  manifest may automate that curation, but no generated-release claim is made
  until that workflow exists.
- CI runs `scripts/check_public_boundary.py` before release. It rejects private
  workstation paths, common credential formats, runtime databases/logs and
  prohibited data directories; the product and competition Dockerfiles are
  built in separate CI jobs.
