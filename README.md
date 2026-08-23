<p align="center">
  <img src="assets/logo.png" alt="Minta" width="420">
</p>

<p align="center">
  <b>The context quality layer for AI agents.</b><br>
  Your AI remembers. Minta tells you when it remembers <i>wrong</i> — and what it's allowed to claim.
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/python-3.9%2B-green"></a>
  <a href="#deepseek-harness"><img src="https://img.shields.io/badge/DeepSeek%20Harness-verified-purple"></a>
  <a href="#benchmarks"><img src="https://img.shields.io/badge/MCP-19%20tools-orange"></a>
</p>

> ⭐ New (2026-08): **open-core v2** — memory engine + research compliance engine + expert domain pack, now with **DeepSeek Harness integration (verified)**. The paper behind the quality layer is under review at *Information Processing & Management*.

---

## Why Minta

Every memory system stores more. Minta's job is to make sure what the agent knows is **still true** — and that it doesn't claim what it hasn't done.

| What others do | What Minta does |
|---|---|
| "Here are your relevant memories" | "2 of these conflict. 1 is stale. Here's the truth." |
| Store everything forever | Detect what expired, flag it, decide with you |
| Treat all memories equally | Type-specific decay: preferences last longer than project state |
| Hope the LLM figures it out | Lifecycle scan + health score + **staged gates** (no over-claims) |

Three layers, one engine:

```
L1 Memory governance   →  stale / conflict / redundant / fragile, found not stored
L2 Expert knowledge    →  rules promoted from your corrections, domain-typed
L3 Claim gates         →  the agent cannot claim a stage it never did (math-model
                          / research workflows) — with calibrated confidence
```

## Quick Start

**60 seconds.** Local-first, no cloud, no API subscription for the open core.

```bash
git clone https://github.com/xinchen03/minta.git
cd minta
python -m pip install -r server/requirements.txt
python minta_cli.py start          # API :8772 · Autopilot :18730 · MCP :18721
```

Or Docker: `docker compose up -d`. Then connect your agent:

```bash
# any MCP-capable editor/agent — Claude Code / Codex / Cursor / dsh
python minta_cli.py connect claude
# DeepSeek Harness (verified) → see docs/dsh-integration.md
```

The web UI opens at `http://127.0.0.1:8772` — memory health dashboard, 3D knowledge graph, inbox review, expert panels.

## Features

| Layer | Feature | What you get |
|---|---|---|
| Memory | Hybrid retrieval (vector + BM25 + entities + FTS) | Picks the right memory, not the most |
| Memory | Lifecycle engine (decay/conflict/redundancy/fragmentation) | Quality checks run *on schedule*, not on faith |
| Correction loop | Inbox + counter-example capture (hooks: SessionStart → UserPromptSubmit → PostToolUse → Stop) | What you correct becomes a rule — after your confirm |
| Expert domains | Multi-domain rules (ankle/knee/c-spine injury, ISO9001, PRISMA…) + CUMCM staged workflow | Domain-typed reasoning with trust metrics |
| Research | Manuscript inventory + compliance rule evaluator | "Does this draft meet the venue checklist?" — before submission |
| Metacognition | Conformal confidence (calibrated, data-locked) | The agent says what it knows with a coverage guarantee |
| Delivery | Dist web UI + MCP (19 tools, stdio + HTTP) + DSH plugin verified | Three entry points, one memory |

## Open-Core: Open Code, Locked Assets

| In this repo (Apache-2.0, free) | Via API key / Enterprise license |
|---|---|
| Memory engine — full, runnable | Managed engine + monitoring |
| Quality-kernel algorithms (conformal, rule promotion, DGM, compiler) | Full precision: auto-calibration, private domains |
| Research compliance engine + domain pack (CUMCM stages) | Sports-medicine / clinical packs |
| Web dist · MCP · DSH integration · 12 guides | Data flywheel: calibration sets, weights, rule bases |

**The commercial line is `accumulated precision`, not code.** You can clone everything; you can't clone what 1,000 users corrected into the calibration.

## Benchmarks

<img src="assets/benchmark_comparison.png" alt="Memory quality comparison — only Minta measures conflict and staleness">

| Detection | Metric | Score | Mem0 | Hindsight |
|---|---|---|---|---|
| Conflict | F₁ | 0.81 (held-out, 5 unseen domains) | N/A | N/A |
| Staleness | UFA | 0.86 (12 fact-pair templates) | N/A | N/A |
| Redundancy | Compression RR | 0.67 (25 clusters) | N/A | N/A |
| Fragmentation | MCR | 0.746 (15 fragment sets) | N/A | N/A |
| Retrieval (LoCoMo) | Recall@20 | 97.1% | — | — |

## Research first

Minta started as the memory layer of a research workflow — literature notes, manuscript checklists, journal compliance, verdict-gated claim tracking. See `runtime/compliance/` and `docs/interaction-guide.md`.

Companion execution skills (Apache-2.0, separate repo): [nature-skills](https://github.com/Yuan1z0825/nature-skills) — reading, figures, citations, polishing.

**Cite:** Chen X., et al. *A Governance Framework for Quality–Utility–Privacy Trade-Offs in Synthetic Athlete Monitoring Data.* Journal of Science and Medicine in Sport (in review); and the IP&M memory-quality paper (available on request).

## DeepSeek Harness

Verified integration (2026-08): connect Minta as an MCP server in DSH in 2 minutes — see `docs/dsh-integration.md` for the exact `cordis.patch.yml` insert. The open-core plugin bundle is published on npm (`@minta/dsh-plugin`).

## Building & contributing

```bash
python scripts/build_open_release.py   # sync publish lineage (A-level only)
python -m pytest tests/                # server test suite
```

We welcome good-first-issue PRs: `entity_linker` English patterns, richer demo scenarios. More in `CONTRIBUTING.md`.

## Guides

[Interaction Guide](docs/interaction-guide.md) · [Startup Order](docs/startup-chain.md) · [DSH Integration](docs/dsh-integration.md) · [Configuration](docs/configuration.md) · [User Guide](docs/user-guide.md) · [MCP Integration](docs/mcp-integration.md)

## Data & Privacy

- Local-first: database, vectors and logs stay on your machine. No telemetry by default.
- Data export / delete: `GET /api/user/export-data` · `DELETE /api/user/delete-data` (authenticated).
- Secrets: generated on first run into `.minta_api_key` (never committed); `MINTA_ADMIN_IDS` gates admin APIs (unset = nobody).
- See `SECURITY.md` for disclosure policy.

## Roadmap

- 2026 Q4 — hosted API (full precision, monitoring), sports-medicine domain pack
- 2027 Q1 — enterprise private deployment + governance audit reports
- v2.1 — paper reproduction scripts (IP&M)

## License

Apache-2.0. Upstream bundled resources retain their own licenses — see `skills/` notes if added later.
