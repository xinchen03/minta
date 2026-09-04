<p align="center">
  <img src="assets/logo.png" alt="Minta" width="420">
</p>

<p align="center">
  <b>The context quality layer for AI agents.</b><br>
  Your AI remembers. Minta tells you when it remembers <i>wrong</i> — and what it's allowed to claim.
</p>

<p align="center">
  <b>English</b> · <a href="README_zh.md">中文</a> · <a href="README_ja.md">日本語</a>
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/python-3.9%2B-green"></a>
  <a href="#deepseek-harness"><img src="https://img.shields.io/badge/DeepSeek%20Harness-verified-purple"></a>
  <a href="#benchmarks"><img src="https://img.shields.io/badge/MCP-19%20tools-orange"></a>
</p>

> ⭐ New (2026-08): **open-core v2** — memory engine + research compliance engine + expert domain pack, now with **DeepSeek Harness integration (verified)**.

---

## Why Minta

> **Other memory systems store. Minta verifies what remains true.**

Memory has three tenses: it *was* true, it *is* true, and it is *still* true today. Almost every memory system optimizes the first. Minta is built for the second and third.

| What others do | What Minta does |
|---|---|
| "Here are your relevant memories" | "2 of these conflict. 1 is stale. Here's the truth." |
| Store everything forever | Detect what expired, flag it, decide with you |
| Treat all memories equally | Type-specific decay: preferences last longer than project state |
| Hope the LLM figures it out | Lifecycle scan + health score + **staged gates** (no over-claims) |

### The same agent, with or without Minta

| | Without Minta | With Minta |
|---|---|---|
| A fact expires | Keeps using the old truth | Marks it stale, archives it, shows you |
| Two memories conflict | Returns both, glues them together | Surfaces the contradiction; you decide |
| You correct the agent | Forgets by next session | Inbox → your confirm → becomes a rule |
| Context grows | 10,000 memories in one prompt | Token-budgeted context pack |

**Contents** · [Why Minta](#why-minta) · [Quick Start](#quick-start) · [Features](#features) · [Open-Core](#open-core-open-code-locked-assets) · [Benchmarks](#benchmarks) · [DeepSeek Harness](#deepseek-harness) · [Roadmap](#roadmap)

## Product UI

The full Minta workspace (`Personal Context Layer`, V8.3 engine UI). The layers you see — research cockpit, expert infer, memory health — map to the engine tiers below; the open-core dist ships the memory hub UI, and the rest activate through the same API.

| | | |
|---|---|---|
| <img src="assets/ui/ui-hero.png" width="420"> | <img src="assets/ui/ui-context-draw.png" width="420"> |
| **Context Hub** — "Stop re-onboarding your AI" | **Context Draw** — 3D knowledge graph + card recall |
| <img src="assets/ui/ui-health.png" width="420"> | <img src="assets/ui/ui-inbox.png" width="420"> |
| **Context Health** — lifecycle dashboard (decay/conflict at a glance) | **Inbox** — confirm/discard corrections, counter-example review |
| <img src="assets/ui/ui-skills.png" width="420"> | <img src="assets/ui/ui-research.png" width="420"> |
| **Skills Library** — 50 registered workflows | **Research Workspace** — projects, evidence, run packages |

</p>

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
# DeepSeek Harness: dsh plugin --profile web add @xxinchen/dsh-plugin  (or connect via MCP → docs/dsh-integration.md)
```

The web UI opens at `http://127.0.0.1:8772` — memory health dashboard, 3D knowledge graph, inbox review, expert panels.

### Configuration & Keys (first run)

```bash
cp .env.example .env    # then edit secrets
python -c "import secrets; print('MINTA_API_KEY=minta_'+secrets.token_hex(32))"  # generate a secure key
```

**Register the key**: the `minta_` prefix alone is not enough — the API accepts a key only if it exists in the keys table. While the engine runs, create the record in the Web UI (`Settings → API keys`) or call `POST /api/keys` with a user token. Write-path tools (inbox, `write_context`) require a registered key; read tools do not.

| Variable | Default | What it does |
|---|---|---|
| `MINTA_DATABASE_URL` | `sqlite:///./minta.db` | Zero-config SQLite; switch to MySQL in one line |
| `MINTA_JWT_SECRET` | *(must set)* | Session signing secret — generate, don't copy |
| `MINTA_API_KEY` | auto-generated on first run | Programmatic access + MCP (connect your editor → `python minta_cli.py connect claude`) |

Full variable reference, SMTP, CORS, feature flags → [`docs/configuration.md`](docs/configuration.md).
Agent integration per editor → [`docs/mcp-integration.md`](docs/mcp-integration.md).

## Features

| Layer | Feature | What you get |
|---|---|---|
| Memory | Semantic search — `POST /api/search` (local-vector, per-user isolated, compact → full → pack disclosure) | Auto-indexed on every write; finds *your* memory, not somebody else’s |
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

The hosted tiers above are roadmap features — the open core is always a complete, runnable memory system.

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

Minta started as the memory layer of a research workflow — literature notes, manuscript checklists, journal compliance, verdict-gated claim tracking. See `runtime/compliance/` and `docs/interaction-guide.md`. Manuscripts describing the framework (memory quality; data governance) are in preparation.

Companion execution skills (Apache-2.0, separate repo): [nature-skills](https://github.com/Yuan1z0825/nature-skills) — reading, figures, citations, polishing.


## DeepSeek Harness

Verified integration (2026-08): `dsh plugin --profile web add @xxinchen/dsh-plugin` wires Minta into DSH in 2 minutes — the plugin composes the official `dsh-mcp-client` row for the locally-run engine (which provides the 19 `minta_*` tools). A manual `cordis.patch.yml` insert is also supported; see `docs/dsh-integration.md`. The plugin also ships the `minta` agent preset (per-turn memory protocol): copy `dsh-plugin/presets/minta` into `~/.dsh/.agent-presets/` and pick it in the session picker.

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
- Secrets: generated on first run into `.minta_api_key` (never committed); privileged APIs are off by default unless explicitly configured.
- See `SECURITY.md` for disclosure policy.

## Vision: Where This Is Going

Memory is the easy part; *truth* is the product. The agent era already has plenty of
"remember more" systems. The bottleneck is the opposite — AIs confidently serve stale,
contradicted, or unearned claims. Minta's answer is a **context quality layer**:
the memory knows its own health (`stale / conflict / redundant / fragile`), the expert
layer knows its own limits (calibrated coverage), and the claim gates know what was
actually done. The long thesis:

- **Personal**: every AI assistant, every session starts from a context hub that
  already understands you — stop re-onboarding your AI.
- **Team / enterprise**: memory, expertise, and compliance checks shared across a
  research group or a clinical unit — with audit trails and governance reports.
- **Vertical**: sports-medicine, clinical-triage, and manufacturing expert packs
  layered on the same engine, tuned by their users' corrections (data flywheel).

## Roadmap

- **2026 Q4** — **hosted API** (full precision, monitoring), sports-medicine domain pack, npm plugin v1 release
- **2027 Q1** — enterprise private deployment + governance audit reports; SME (structure-mapping) engine public
- **2027** — multi-agent shared memory workspaces (team context layers)

## Community & Contact

- 🐛 **GitHub Issues** — bugs, feature requests (we respond fast)
- 💬 **GitHub Discussions** — questions, RFCs, show-your-work
- 📧 **Contact**: xxinchen03@gmail.com (direct; research collaboration, consulting)
  are the publishable signs of this repo's claims; HackerNews/DSH plugin discussions
  welcome at every release.

## Star Us

🔭 **If Minta saved you an hour, give it a ★.** One click, three seconds —
and it tells the next contributor, integrator, and journal reviewer that this
experiment deserves their attention.

## References & Lineage

Where the ideas come from (and how Minta differs):

| Work | What Minta took | What Minta differs in |
|---|---|---|
| **Mem0 / MemOS** | Memory store + hybrid retrieval | They store; Minta *verifies* quality (decay, conflict, redundancy, fragmentation) |
| **Vovk (2005), conformal prediction** | Distribution-free coverage guarantee | Used as the *metacognitive gate*, not just an estimator |
| **JEPA (LeCun)** | Predict in latent space, not raw space | Domain rules > JEPA — predictions only fire when history exists |
| **Ebbinghaus-inspired decay** (MemoryBank et al.) | Time-aware forgetting | Type-specific half-lives: preferences > project state |
| **Paperclip doc-maintenance** | Audit-driven maintenance | Same discipline, now for AI memory, not files |

## License

Apache-2.0. Upstream bundled resources retain their own licenses — see `skills/` notes if added later.
