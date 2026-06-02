# Minta — Memory That Checks Itself

<p align="center">
  <img src="assets/logo.png" alt="Minta Logo" width="500">
</p>

<p align="center">
  <b>Your AI remembers. Minta tells you when it remembers <i>wrong</i>.</b>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.9%2B-green"></a>
  <a href="#"><img src="https://img.shields.io/badge/MCP-20%20tools-purple"></a>
  <a href="README_zh.md"><img src="https://img.shields.io/badge/README-中文-red"></a>
</p>

> **An AI memory engine with built-in self-correction & memory quality governance.**

---

**Contents** &nbsp; [What Minta Handles](#what-minta-handles) · [Quick Start](#️-quick-start-30-seconds) · [Docs](#-documentation) · [Memory Health](#the-difference-memory-health-not-just-memory) · [Architecture](#️-architecture) · [Benchmarks](#-benchmarks) · [vs Competitors](#-vs-competitors) · [Research](#-research-foundation) · [Vision](#-where-this-is-going) · [License](#-license)

---

## You've felt this.

You told your AI assistant you switched from NextAuth to Clerk. Two weeks later, it confidently suggests a NextAuth configuration.

You mentioned your team grew from 3 to 7 people. The AI still asks "how's your 3-person team doing?"

You spent 3 months building a project with it. But ask "what framework am I using?" and it searches through 10,000 scattered memories, guesses, and gets it wrong.

**This isn't a bug. It's memory decay.** Every AI that remembers you is slowly filling up with stale facts, contradictory preferences, and redundant copies of the same information. No one is checking.

## We are.

Minta is the **first memory quality layer** for AI. While every other memory system focuses on *storing more*, Minta focuses on *staying correct*.

| What others do | What Minta does |
|---------------|-----------------|
| "Here are your relevant memories" | "2 of these conflict. 1 is stale. Here's the truth." |
| Store everything forever | Detect what expired, flag it, archive it |
| Treat all memories equally | Type-specific decay: preferences last longer than project state |
| Hope the LLM figures it out | Run a lifecycle scan. Show you the health score. Let you decide. |

## The Difference: Memory Health, Not Just Memory

Other memory systems are like a hard drive — they store bits. Minta is like an immune system — it detects what's wrong.

**Five dimensions of memory health, continuously monitored:**

```
D_S  Staleness     "You said this 200 days ago. Still true?"
D_R  Redundancy    "You said the same thing 3 times. Merge?"
D_C  Conflict      "These two facts contradict. Which is right?"
D_F  Fragmentation "Team info scattered across 4 entries. Group?"
D_V  Schema        "This memory has no source. Can we trust it?"
```

Every dimension is computed locally, with zero API calls. Your data never leaves your machine.

## The Story: Alex in 60 Seconds

Alex is a startup founder. Their AI coding assistant has been learning for 3 months. But something is rotting in its memory...

→ **After installing:** run `minta start` and open `http://localhost:8772/story`. Seeds 25 demo memories with 6 built-in problems. Watch Minta detect them all in under a second.

---

<p align="center">
  <video src="assets/demo.mp4" autoplay muted loop playsinline width="800"></video>
</p>

## What Minta Handles

Minta ingests the content you already work with. We ship what's stable, and we're upfront about what's next.

| | Status | |
|---|:---:|---|
| **Text & chat** | ✅ Now | Conversations, documents, notes — the core. Everything becomes searchable memory. |
| **Images & screenshots** | ✅ Now | OCR + caption extraction. Search your whiteboard photos like text. |
| **Email** | ✅ Now | Parse .eml files. Your inbox becomes part of your memory. |
| **Voice** | 🔜 Next | Meeting recordings, voice notes — light integration, fast iteration. |
| **Video** | 📋 Later | Frame extraction + transcript + scene recognition — enterprise meetings, training. |

Everything runs locally. No uploads. No cloud. Three-second install.

## ⚡ Get Started

**Install anywhere — C drive, D drive, desktop, doesn't matter.** Python 3.9–3.11 recommended (3.12+ may fail on some package builds).

### Step 1: Install

```bash
git clone https://github.com/xinchen03/minta.git
cd minta
pip install -r requirements.txt   # 3-5 min, depending on network
```

### Step 2: Configure Environment

```bash
cp .env.example .env              # Copy the template
```

Edit `.env`, at minimum change:

```ini
MINTA_JWT_SECRET=change-to-a-random-string
MINTA_API_KEY=minta_your_key_here  # leave empty to auto-generate
```

> `.env` is loaded automatically via `python-dotenv`. If you skip this step, Minta auto-generates secrets — but explicit config gives you more control.

### Step 3: Connect Your AI Editor

```bash
python minta_cli.py connect       # Auto-configures MCP for your AI editors
```

This one command configures **Claude Code, Cursor, Codex, and VS Code** for MCP.

**Claude Code, Cursor, and Codex** use stdio mode — the editor auto-starts Minta on demand. No manual launch needed.

**VS Code** uses HTTP mode — start Minta first with `python minta_cli.py start`.

Open **http://localhost:8772** in your browser. You should see the login/register page.

> **Restart your AI editor** after running `minta connect` to pick up the new MCP configuration.

### Step 4: Register on the Web

1. Click **Register** at http://localhost:8772 — pick a username, email, and password
2. Log in and go to the dashboard
3. Find your **API Key** in Settings (auto-generated if not set in `.env`)

### Step 5: Verify Everything Works

```bash
python minta_cli.py verify       # 10-point health check
```

You should see `10/10 checks passed`. If anything fails, the output tells you exactly what's wrong.

### ✅ Done

**Restart your AI editor.** Ask it: *"What does Minta remember about me?"* If it responds, you're connected.

> **Real-world time: ~5 minutes.** Install 3 min, `.env` 30 sec, `minta launch` 10 sec, register 1 min.

---

### Which AI Can I Use?

`minta connect` configures all supported editors. Use a flag to pick just one:

| Command | AI Editor | Mode | Config |
|---------|-----------|------|--------|
| `minta connect` (default) | **All editors** | mixed | All four |
| `minta connect --claude` | Claude Code | stdio | `~/.claude/settings.json` |
| `minta connect --cursor` | Cursor IDE | stdio | `~/.cursor/mcp.json` |
| `minta connect --codex` | Codex CLI | stdio | `~/.codex/mcp.json` |
| `minta connect --vscode` | VS Code / Copilot | HTTP | `~/.vscode/mcp.json` |

> **stdio** = editor auto-starts Minta on demand. **HTTP** = start Minta first with `minta start`.

### Day-to-Day

```bash
minta status               # Are services healthy?
minta verify               # Full 10-point end-to-end check
minta stop                 # Shut down background services
minta start                # Start them again
```

### Day-to-Day

**With stdio mode (Claude Code, Cursor, Codex):** Nothing to do. Open your editor — Minta auto-starts when needed.

**With HTTP mode (VS Code):** Start Minta before opening VS Code:
```bash
python minta_cli.py start     # Start Minta services
```

### One-Time Setup

```bash
python minta_cli.py connect    # Configures MCP for your AI editors
python minta_cli.py verify     # Confirm all checks pass
```

Restart your AI editor. Done.

### After Reboot

**stdio editors (Claude, Cursor, Codex):** No action needed — auto-starts on demand.

**HTTP editors (VS Code):** Run `python minta_cli.py start` or use the desktop launcher.

| Method | What to do | Works for |
|--------|-----------|-----------|
| Auto (stdio) | Just open your editor | Claude Code, Cursor, Codex |
| Manual | `python minta_cli.py start` | VS Code, custom agents |
| Launcher | `Start-Minta.vbs` (Win) / `Start-Minta.sh` (Mac/Linux) | HTTP editors |
| Desktop shortcut | Run `Setup-Desktop-Shortcut.ps1` (Win) / `.command` (Mac) once to create an icon | All editors |
| Auto-start on boot | Win: Startup folder · Mac: LaunchAgent · Linux: autostart | All editors |
| Claude Code hooks | Copy `hooks/` to `~/.claude/hooks/` — Claude asks if you want Minta when it opens | Claude Code only, but covers most users |

<details>
<summary><b>macOS / Linux setup</b></summary>

```bash
chmod +x scripts/minta-start-silent.sh

# Auto-start on login (macOS):
cp scripts/com.minta.starter.plist ~/Library/LaunchAgents/
# Then edit the plist to point to the full path of minta-start-silent.sh

# Auto-start on login (Linux):
cp scripts/minta-start-silent.sh ~/.config/autostart/
```
</details>

> **Desktop / web-coding users:** The silent launcher is for you. Double-click, no terminal, Minta runs in the background. Then open your AI — it connects automatically if you've run `minta launch --all` once.

### Docker

```bash
git clone https://github.com/xinchen03/minta.git && cd minta
docker compose up -d       # Start (http://localhost:8772)
docker compose down        # Stop
```

Data persists in a Docker volume. MCP runs at `http://localhost:18721/mcp`.

> **How connections work:** `minta connect` writes MCP config to your editor. stdio editors (Claude, Cursor, Codex) auto-start Minta on demand. HTTP editors (VS Code) need `minta start` first.
>
### Double Insurance: Hooks

Even with the Golden Rule, it's easy to forget. The **SessionStart hook** catches it:

```
You open Claude → Hook fires → Minta not running?
  → Claude asks: "Want Minta mode? (y/n)"
  → Yes: "Run: python minta_cli.py connect → restart me"
  → No:  Continue without Minta

You open Claude → Hook fires → Minta already running?
  → Context injected silently → You can use Minta tools
```

Install once:

```bash
# Claude Code
cp -r hooks/* ~/.claude/hooks/

# Other editors: hooks are Claude Code-specific.
# Use 'minta launch' for Cursor / VS Code / Codex instead.
```

> The hook never crashes your session. If Minta's API is unreachable, it silently passes — you just don't get context injection that session.

### FAQ

<details>
<summary><b>Q: Can I install on D drive? Does location matter?</b></summary>

**No, location doesn't matter.** Minta is fully local — it works from C drive, D drive, desktop, or even an external drive. Just avoid paths with spaces or non-ASCII characters (e.g. prefer `D:/minta` over `D:/My Folder/minta`).
</details>

<details>
<summary><b>Q: Does using Conda / venv / system Python make a difference?</b></summary>

- **Version matters more:** Python 3.9–3.11 is most stable. 3.12+ may fail building sentence-transformers.
- **Speed difference is negligible:** Conda downloads may be slightly slower, but runtime speed is the same.
- **Recommendation:** Use whatever you're comfortable with. If you have Conda, `conda activate` first. System Python + `pip install` works fine.

**Getting "tokenizers build failed"?** Switch to Python 3.10 or 3.11, or run: `pip install --only-binary :all: sentence-transformers`.
</details>

<details>
<summary><b>Q: Why do I need to register on the web first, then configure the API key?</b></summary>

Minta has two components:

1. **Data server (port 8772):** Stores your memories, runs lifecycle scans. Needs user accounts to separate data.
2. **MCP server:** Lets your AI call Minta tools. stdio mode (default for Claude/Cursor/Codex) auto-starts on demand. HTTP mode (VS Code, custom agents) runs on port 18721.

The flow is: **Register on web → get API Key → AI uses the key to connect.** Same idea as registering on GitHub before setting up an SSH key. Set `MINTA_API_KEY` in `.env`, or find it in the web dashboard Settings page after starting.
</details>

---

## 📖 Documentation

Beyond this README, we have detailed guides for every use case:

| Document | What's Inside |
|----------|---------------|
| **[User Guide](docs/user-guide.md)** | Step-by-step: dashboard, memory objects, inbox, health scanning, semantic search, context packs, skills, community sharing, troubleshooting |
| **[Configuration Guide](docs/configuration.md)** | All env vars, MySQL/PostgreSQL setup, SMTP email verification, CORS, API keys, autopilot, production deployment with Nginx |
| **[MCP Integration Guide](docs/mcp-integration.md)** | Connect Minta to Claude Code, Cursor, and custom agents via MCP. Full tool reference (19 tools) with Python/JavaScript examples for both stdio and HTTP transports |

> 💡 **New to Minta?** Start with the [User Guide](docs/user-guide.md). **Setting up for a team?** Check the [Configuration Guide](docs/configuration.md). **Want your AI to use Minta?** See [MCP Integration](docs/mcp-integration.md).

---

## 🔌 MCP Tools

11 tools available via standard MCP protocol:

| Category | Tools |
|----------|-------|
| Context CRUD | `minta_read_context`, `minta_write_context`, `minta_search_context`, `minta_get_pack`, `minta_get_slot`, `minta_update_slot` |
| Inbox | `minta_list_inbox`, `minta_append_inbox`, `minta_confirm_inbox`, `minta_discard_inbox` |
| Autopilot | `minta_autopilot_preflight`, `minta_autopilot_postflight` |
| Auth | `minta_login` |

```bash
# Auto-configure for your AI editor:
minta connect           # Claude Code
minta connect --cursor  # Cursor IDE
minta connect --codex   # Codex CLI (coming soon)

# Or manually:
claude mcp add minta --url http://localhost:18721/mcp
```

---

## 🧠 What Makes Minta Different

### Four Lifecycle Mechanisms (Zero LLM Cost)

| Mechanism | What It Detects | How |
|-----------|----------------|-----|
| **Staleness** | Facts unused too long | Type-specific exponential decay (100–200 day half-lives) |
| **Conflict** | Contradictory memories | Logistic regression + negation bypass gating |
| **Redundancy** | Near-duplicate entries | Cosine similarity with calibrated thresholds |
| **Fragmentation** | Scattered related facts | DBSCAN clustering on shared tags |

### Counter-Example Learning
Minta detects when you correct your AI → automatically captures the lesson → never repeats the same mistake.

### Human-in-the-Loop
All automated findings go to your **Inbox** for review. Nothing changes without your approval.

### Platform Independent
Generate **Context Packs** that work with any AI — Claude, ChatGPT, Gemini, Cursor, local models.

---

## 📊 Benchmarks

### Memory Quality (Minta's unique category — no competitor does this)

| Detection | Metric | Score | Mem0 | Hindsight |
|-----------|--------|-------|------|-----------|
| Conflict | F₁ | 0.81 (held-out, 5 unseen domains) | N/A | N/A |
| Staleness | UFA | 0.86 (12 fact-pair templates) | N/A | N/A |
| Redundancy | Compression RR | 0.67 (25 clusters) | N/A | N/A |
| Fragmentation | MCR | 0.746 (15 fragment sets, median 115d) | N/A | N/A |

> *All metrics measured on held-out evaluation sets disjoint from calibration data. Full paper in preparation.*

### We Also Run the Standard Tests

On the LoCoMo benchmark (1,986 questions across 10 long conversations, 11,958 facts):

| What we measure | Result | In plain English |
|----------------|:------:|------------------|
| Find the right conversation? | **97.1%** | Almost never miss the relevant chat |
| Find the right fact? | **82.6%** | Pinpoint the answer in 12K tiny facts |
| Answer correctly? (AI-judged) | **53.1%** | Getting better — our reranker is ready, expect ~55-58% |

> These are sanity checks. Minta's real contribution is the Memory Quality table above — four metrics no one else measures.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│  Claude Code / Cursor / Any AI                   │
│         │  MCP (19 tools)                        │
├─────────┼────────────────────────────────────────┤
│  Minta API Server (:8772)                        │
│  ├── Context Objects (typed memory store)        │
│  ├── Lifecycle Scanner (4 mechanisms)            │
│  ├── Autopilot (preflight/postflight)            │
│  └── Context Pack Builder                        │
├──────────────────────────────────────────────────┤
│  Storage Layer                                   │
│  ├── SQLite (structured data, FTS5 search)       │
│  └── ChromaDB (vector embeddings, 768-dim)       │
└──────────────────────────────────────────────────┘
```

**Memory Hierarchy:**
- **L0 Working Memory** (RAM): 7 pinned Slots, recent context (<1ms)
- **L1 Recent Memory** (RAM cache + disk): ChromaDB LRU + SQLite page cache (~5ms)
- **L2 Long-term Memory** (disk): Full vector + text storage (unlimited)

**Zero external dependencies.** No Docker. No Redis. No API keys required.

---

## 🆚 vs Competitors

### Feature Matrix

| | **Minta** | Mem0 | Letta | Zep | LangMem | Hindsight | MemoryLake |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Open Source** | ✅ MIT | ✅ Apache 2.0 | ✅ Apache 2.0 | ✅️ Community | ✅ MIT | ✅ MIT | ❌ |
| **Local-First** | ✅ pip install | ✅ SDK | ✅ pip | ❌ Neo4j+Docker | ✅ pip | ❌ Docker | ❌ Cloud |
| **Structured Memory Types** | ✅ 5 types | ❌ Flat | ✅ Agent-scoped | ✅ Graph | ❌ Buffer | ❌ | ✅ 6 types |
| **Conflict Detection** | ✅ F₁=0.81 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Staleness Detection** | ✅ Type-specific | ❌ | ❌ | ⚠️ Time edges | ❌ | ❌ | ❌ |
| **Redundancy Detection** | ✅ Cosine+Jaccard | ⚠️ Basic dedup | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Fragmentation Detection** | ✅ DBSCAN | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Counter-Example Learning** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Human-in-the-Loop (Inbox)** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Git-like Versioning** | ✅ Inbox audit | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Cross-Platform Context Pack** | ✅ MCP | ❌ API-only | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Multi-Agent Memory Share** | ✅ | ❌ | ❌ Agent-bound | ✅️ | ❌ | ❌ | ✅ |
| **Zero LLM Cost (lifecycle)** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **MCP Protocol** | ✅ 11 tools | ❌ | ❌ | ❌ | ✅ SDK | ❌ | ❌ |

![Benchmark Comparison](assets/benchmark_comparison.png)

### What Minta Measures That Nobody Else Does

Other systems compete on retrieval accuracy. Minta competes on **memory quality** — a category it created.

| Metric | Minta Score | What It Means | Industry Status |
|--------|:---------:|---------------|-----------------|
| **Conflict Detection** | F₁ = 0.81 | Finds contradictory memories (held-out, 5 unseen domains) | 🥇 First and only |
| **Staleness Detection** | UFA = 0.86 | Detects outdated facts before they cause harm (12 templates) | 🥇 First and only |
| **Redundancy Compression** | RR = 0.67 | Identifies near-duplicate entries (25 clusters) | 🥇 First and only |
| **Fragmentation Detection** | MCR = 0.746 | Groups scattered related facts (15 sets, median 115d) | 🥇 First and only |
| **LoCoMo open-domain (Semantic)** | 59.7% | LLM-judged semantic accuracy on 145 open-domain questions | Transparent pipeline |
| **Evidence Recall@20** | 82.6% | Correct answer is in top-20 retrieved sessions (7-channel hybrid) | Competitive |
| **Oracle Ceiling (Token F1)** | 36.9% | Upper bound of token-overlap F1 on LoCoMo — harsh metric ceiling | Benchmark property |

> All metrics measured on held-out evaluation sets disjoint from calibration data. Full paper in preparation.

### Industry Context (LoCoMo)

For reference, here's how other systems perform on the LoCoMo benchmark. **Note:** scores are not directly comparable — different answer models, prompts, and evaluation methods were used.

| System | Reported LoCoMo | Deployment | Open Source |
|--------|:---------------:|------------|:-----------:|
| MemoryLake | 94.03% | Cloud-only | ❌ |
| Backboard | 90.1% | SaaS | ❌ |
| Hindsight | 89.6% | Docker | ✅ MIT |
| Memobase | 75.8% | SaaS | ❌ |
| Zep | 75.1% | Neo4j + Docker | ✅ Community |
| Mem0 | 66.9% | SDK | ✅ Apache 2.0 |
| LangMem | 58.1% | pip | ✅ MIT |

> Sources: [Backboard.io LoCoMo Benchmark](https://github.com/Backboard-io/Backboard-Locomo-Benchmark), Vectorize.io, ACL 2024. Scores self-reported by each system. Minta is not included as it measures a different category (memory quality, not just retrieval).

### Why Minta Is Different

Other memory systems help AI **remember**. Minta helps AI **remember correctly**.

| | Other Memory Systems | Minta |
|---|---------------------|-------|
| **Conflict** | "Here are 10 relevant memories" | "3 of your memories conflict. Here's which one is right." |
| **Staleness** | "I stored your preference" | "Your preference changed 2 weeks ago. Updating now." |
| **Correction** | Repeats the same mistake | Learns from correction, never repeats |
| **Quality** | 10,000 memories, 15% stale | 10,000 memories, <1% stale (auto-maintained) |
| **Portability** | Locked to one AI | Context Pack works with any AI |

---

## 📄 Research Foundation

Minta's memory quality mechanisms are grounded in **Context Debt theory** — a formal framework defining how AI memory degrades and how to detect it. The full paper is in preparation for journal submission.

Key findings from our evaluation:

- Type-specific decay constants (S_type: 100–200 day half-lives), calibrated on N=60 human annotations
- Conflict detection: 5-fold CV F₁=0.683, held-out F₁=0.81 across 5 unseen domains
- Cross-dimensional effects: isolated staleness interventions amplify fragmentation — the four mechanisms must work together

All benchmarks, evaluation data, and calibration parameters are included in this repository.

---

## 🔌 MCP Tools

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md).

**Good first issues** are tagged for newcomers.

---

## 📜 License

**Open-source scope:** The core memory engine, all four quality detection mechanisms, the hybrid retrieval pipeline, MCP tools, CLI, benchmarks, and evaluation scripts are fully open-source (MIT). Enterprise features — multi-tenancy, visual rule editor, domain expert modules, and calibrated rule packs — will ship separately.

Core engine: **MIT** — use freely, modify, distribute.  
Expert rules and calibration data: **BSL** — free for personal use, commercial license required.

See [LICENSE](LICENSE) for details.

---

## 🔭 Where This Is Going

Every AI will need memory. But memory without quality control is just a dumpster with a search bar.

We're building the **memory quality layer** for the AI era — the same way databases got ACID, CI/CD got testing, and code got linting. Memory needs its own correctness guarantee. Minta is that guarantee.

**The vision:**

> Every AI will have memory. The question won't be "can it remember?" — it will be "can it be trusted?" Minta is building the trust layer for AI memory. First we detect what's wrong. Then we understand how memories relate. Then we predict what will change.

**Where we're going:**

```
Now        Memory Health     Staleness, conflict, redundancy, fragmentation.
                             4 metrics nobody else measures. Zero API calls.
                             Text, images, email — all parsed offline.

Next       Memory Structure  From isolated facts to a living knowledge graph.
                             Dependencies mapped, cascading updates,
                             voice input added. Beliefs that evolve.

Then       Memory Reasoning  A world model that predicts how memories change.
                             Expert systems that reason across domains.
                             Video processing for enterprise meetings, training.

Beyond     Memory Platform   Multimodal, multi-tenant, enterprise-grade.
                             Visual rule editor for domain experts.
                             MIT core. Pro for teams and verticals.
```

---

## 👥 Join Us

This is early. The memory quality category doesn't exist yet — we're creating it.

If you're working on AI agents, RAG systems, or personal AI assistants, you've felt the memory decay problem. You know that storing memories isn't enough — someone has to check if they're still true.

**We're looking for:**
- **Early users** — Run Minta on your own AI workflows. Tell us what breaks.
- **Contributors** — The core engine is MIT. Graph memory, multimodal ingestion, evaluation tools — pick a direction and build.
- **Researchers** — If you work on agent memory, context engineering, or knowledge management, let's talk. The Context Debt framework is fully documented and reproducible.
- **Design partners** — Building an AI product that needs trustworthy memory? Minta can be your memory quality backend.

**This is not a startup pitch. This is an invitation to define a category.**

→ [xxinchen03@gmail.com](mailto:xxinchen03@gmail.com) | [github.com/xinchen03/minta](https://github.com/xinchen03)

---

## 📜 License

Core engine: **MIT** — use freely, modify, distribute.

Expert rules and calibration data: **BSL** — free for personal use, commercial license required.

See [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>Built by <a href="https://github.com/xinchen03">Xin Chen</a></b> &middot; Tianjin, China
</p>
