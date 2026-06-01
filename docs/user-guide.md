# Minta User Guide

> 🌐 [中文版](user-guide_zh.md) | English

A step-by-step guide to using Minta as your personal memory layer for AI agents.

> **Prerequisite:** [Installation → Quick Start](../../#quick-start) in the README. Make sure `minta start` is running and you can open `http://localhost:8772`.

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Dashboard Overview](#dashboard-overview)
3. [Working with Memory Objects](#working-with-memory-objects)
4. [The Inbox — Your Memory Review Queue](#the-inbox--your-memory-review-queue)
5. [Memory Health Scanning](#memory-health-scanning)
6. [Semantic Search](#semantic-search)
7. [Context Packs (AI Injection)](#context-packs-ai-injection)
8. [Skills Library](#skills-library)
9. [Community Sharing](#community-sharing)
10. [Expert System (Clinical Decision Support)](#expert-system-clinical-decision-support)
11. [Account & Privacy](#account--privacy)
12. [Troubleshooting](#troubleshooting)

---

## Core Concepts

Minta stores **memory objects** — structured facts about you, your work, your preferences, and your decisions. These objects feed into your AI agent so it "remembers" who you are and how you work.

### The 7 Memory Slots

Your memory is organized into 7 slots. Think of each slot as a drawer in your personal memory cabinet:

| Slot | What Goes In | Example |
|------|-------------|---------|
| **Persona** | Who you are, your role, background | "Full-stack developer, 5 years, prefers TypeScript" |
| **Preferences** | How you like things done | "Use 2-space indentation, prefer async/await over Promises" |
| **Knowledge** | Technical facts, project context | "Our API uses JWT with 24h expiry, stored in httpOnly cookies" |
| **Counter Examples** | Mistakes to avoid, corrections | "Don't use `Date.now()` in test assertions, use `vi.setSystemTime()`" |
| **Skills** | Reusable workflows | Code review checklist, deployment steps, bug triage process |
| **Pending** | Items awaiting review | Feedback from conversations not yet processed |
| **Rules** | Hard constraints, always-on rules | "Never commit .env files to git" |

### Memory Object Types

Each object has a **type** that tells Minta what kind of memory it is:

- **`preference`** — How you like to work (editor settings, code style, communication preferences)
- **`workflow`** — Reusable process or procedure (deploy steps, code review checklist)
- **`project_context`** — Facts about your projects (architecture decisions, tech stack, domain knowledge)
- **`decision_criteria`** — How you make decisions (priorities, constraints, rules of thumb)
- **`lesson_learned`** — Things you learned the hard way (bugs caught, mistakes fixed)
- **`writing_style`** — Your voice and tone preferences (formality, terminology, audience)
- **`rule`** — Hard rules the AI should always follow
- **`ai_brief`** — Context you want to give your AI before a session
- **`work_profile`** — Your professional identity and current focus

---

## Dashboard Overview

When you open `http://localhost:8772`, you land on the main dashboard. Key areas:

```
┌─────────────────────────────────────────────────────┐
│  🔍 Search bar         [Inbox (3)]  [⚙ Settings]    │
│─────────────────────────────────────────────────────│
│  Memory Health Score: 85/100                         │
│  ████████████████░░░░                                │
│─────────────────────────────────────────────────────│
│  📋 All Memories    📥 Inbox    📦 Packs    🔧 Skills│
│─────────────────────────────────────────────────────│
│  [Type filters]                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │ Memory cards with title, type, confidence... │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### Navigation Tabs

- **All Memories** — Browse, filter, and manage your memory objects
- **Inbox** — Review pending corrections, counter-examples, and scan findings
- **Packs** — View your 7 slots and generate Context Packs for AI injection
- **Skills** — Browse and manage reusable skill templates
- **Story** (`/story`) — Interactive demo with a fictional character's memory journey

### Memory Health Score

The dashboard shows a **Health Score (0–100)** computed from four dimensions:

| Metric | What It Measures | Bad Sign |
|--------|-----------------|----------|
| **D_S** (Staleness) | How many memories are unused >30 days | High → stale knowledge |
| **D_R** (Redundancy) | Duplicate or near-duplicate memories | High → fragmented knowledge |
| **D_C** (Conflict) | Contradictory memories | High → unreliable for AI |
| **D_V** (Schema) | Malformed or incomplete entries | High → data quality issues |

A score above 80 is healthy. Below 60, you should run a memory scan.

---

## Working with Memory Objects

### Creating a Memory Object

1. Click **+ New Memory** (or the add button)
2. Fill in:
   - **Title** (required) — A short, descriptive name
   - **Type** (required) — Pick from the 9 types
   - **Summary** (optional) — One-sentence description
   - **Body** (optional) — Full details, examples, context
   - **Tags** (optional) — Keywords for search, e.g. `["react", "frontend", "testing"]`
   - **Confidence** (1–5) — How sure you are this is still true
3. Click **Save**

> 💡 **Tip:** Even a one-sentence memory with good tags is useful. You don't need to write essays — the AI agent will combine memories as needed.

### Editing a Memory

Click any memory card to open the detail view, then:

- Edit title, summary, body, or tags
- Change the type or confidence level
- Toggle **Public** to share with the community
- Upload a **cover image** (useful for visual memories like screenshots)

### Deleting a Memory

Open the detail view → click **Delete**. This is permanent and cannot be undone.

### Filtering Memories

Use the type filter buttons at the top to show only:
- Preferences
- Workflows
- Project Context
- Lessons Learned
- Rules
- ...or any custom type

Combine with the search bar for fine-grained filtering.

---

## The Inbox — Your Memory Review Queue

The **Inbox** is where Minta deposits things for your review. Think of it as a notification center for your memory.

### What Goes into the Inbox?

1. **Auto-detected issues** from memory health scans (staleness, conflicts, duplicates)
2. **Counter-examples** auto-captured when you correct the AI
3. **Manual additions** you add from the dashboard
4. **Autopilot suggestions** from post-conversation analysis

### Reviewing Inbox Items

For each inbox item, you have three options:

| Action | What It Does |
|--------|-------------|
| **Confirm** | Accept the suggestion and convert it to a memory object |
| **Discard** | Dismiss it (good for false positives) |
| **Skip** | Leave it in the inbox for later |

When you confirm, you choose the memory type it becomes. For example:
- A stale memory detection → confirm as `lesson_learned`
- A conflict between two rules → confirm the corrected version as `rule`

### Inbox Statuses

- **`pending`** — Awaiting your review (default)
- **`archived`** — Reviewed and processed

---

## Memory Health Scanning

Minta automatically scans your memory for quality issues every 24 hours. You can also trigger a manual scan anytime.

### What the Scanner Detects

| Scan | What It Finds | Example |
|------|--------------|---------|
| **Staleness** | Memories not used in >30 days | "React class components" if you've moved to hooks |
| **Redundancy** | Near-duplicate memories (80%+ similar) | Two preferences both saying "use 2-space indentation" |
| **Fragmentation** | Too many memories sharing one tag | 15 memories tagged `#debugging` |
| **Conflict** | Contradictory recommendations | "Always use async/await" vs "Use .then() for Promise chains" |
| **Schema** | Incomplete or malformed entries | Memory with empty body, very low confidence |

### Running a Manual Scan

1. Go to the **Lifecycle** tab
2. Click **Run Memory Health Scan**
3. Wait ~2–5 seconds (depends on memory count)
4. Review the findings in your **Inbox**
5. Confirm or discard each finding

### Configuring Auto-Scan

```bash
# Check current auto-scan status
curl http://localhost:8772/api/lifecycle/auto-scan/status

# Change scan interval to every 6 hours
curl -X POST "http://localhost:8772/api/lifecycle/auto-scan/interval?hours=6"

# Disable auto-scan
curl -X POST "http://localhost:8772/api/lifecycle/auto-scan/toggle?enabled=false"
```

> 💡 **Tip:** If you use Minta daily, the default 24h scan is perfect. Adjust to every 1–2 hours during heavy usage.

---

## Semantic Search

Minta uses embedding-based search, which means you can search by **meaning**, not just keywords.

### How to Search

1. Type a natural language query in the search bar
2. Minta ranks results by semantic similarity
3. Results show in **progressive disclosure** layers:
   - **Compact** — Title + type (quick scan)
   - **Full** — Title + summary + tags (detailed)
   - **Pack** — Full content (deep read)

### Search Tips

```
✅ "How do I handle errors in React?"     → finds error handling patterns
✅ "My coding preferences"                → finds all preference-type memories
✅ "database connection setup"            → finds related project context
❌ "eror handlng"                         → works, but well-formed queries are better
```

> 💡 Minta searches across titles, summaries, tags, and semantic embeddings. You don't need perfect keywords.

---

## Context Packs (AI Injection)

A **Context Pack** is a compiled snapshot of your 7 memory slots, formatted for injection into an AI agent's prompt.

### Generating a Context Pack

1. Go to **Packs** tab
2. Review your 7 slots — update any that need changes
3. Click **Generate Pack**
4. Choose a scene: `auto`, `coding`, `writing`, `research`, or `general`
5. Copy the generated text

### Using the Pack with Claude Code

```bash
# Method 1: Via MCP (automatic)
# Configure in your Claude Code MCP settings — see docs/mcp-integration.md

# Method 2: Manual copy-paste
# Generate the pack, copy it, paste at the start of your conversation
```

### What Each Scene Includes

| Scene | Focus Slots | Best For |
|-------|------------|----------|
| `coding` | Preferences, Knowledge, Rules, Lessons | Programming sessions |
| `writing` | Writing Style, Persona, Preferences | Content creation |
| `research` | Knowledge, Project Context, Decision Criteria | Research and analysis |
| `general` | All 7 slots (balanced) | Any conversation |
| `auto` | Auto-detected from your current context | Default (recommended) |

---

## Skills Library

Skills are reusable templates for workflows, checklists, and procedures. They can be private or shared with the community.

### Creating a Skill

1. Go to **Skills** tab
2. Click **+ New Skill**
3. Fill in:
   - **Name** — Short identifier
   - **Group** — Category (e.g., `code-review`, `deployment`, `debugging`)
   - **Content** — The actual steps/template
4. Click **Save**

### Using Skills

Skills appear in your Context Pack under the **Skills** slot. When you generate a pack for a coding session, your code review checklist skill is automatically included.

### Community Skills

Browse publicly shared skills from other Minta users. Click **Share** on any of your skills to contribute to the community.

---

## Community Sharing

You can mark any memory object as **Public** to share it with the Minta community.

### How Sharing Works

1. Edit a memory object
2. Toggle **Public** to ON
3. The object appears in the **Community Feed**
4. Other users can:
   - View the object
   - Leave threaded comments
   - Draw cards from the public pool for inspiration

### Content Moderation

Comments are moderated with automatic content filtering. Rate limiting applies (5 comments per 60 seconds per user).

---

## Expert System (Clinical Decision Support)

Minta includes a built-in expert system with domain-specific inference engines. Currently supports clinical decision rules.

### Available Domains

| Domain | Rules Based On | What It Evaluates |
|--------|---------------|-------------------|
| `ankle_injury` | Ottawa Ankle Rules (Stiell 1992, JAMA) | Whether an ankle X-ray is needed |
| `knee_injury` | Ottawa Knee Rules (Stiell 1996, JAMA) | Whether a knee X-ray is needed |
| `cervical_spine_injury` | Canadian C-Spine Rule (Stiell 2001, JAMA) | Whether cervical spine imaging is needed |

### Using the Expert System

1. Go to **Expert** tab or open Chat
2. Select a domain (e.g., `ankle_injury`)
3. Describe the patient's symptoms
4. The system applies the clinical decision rules
5. You get a recommendation with confidence score

### Chat Interface

The `/api/chat` endpoint auto-detects the domain from your message:

```
You: "Patient with ankle pain after twisting foot, tender at lateral malleolus"
Minta: "Domain: ankle_injury. Applying Ottawa Ankle Rules...
       Rule A (lateral malleolus tenderness): POSITIVE
       → Recommendation: X-ray indicated. Confidence: 0.92"
```

> ⚠️ **Disclaimer:** The expert system is for educational and decision-support purposes only. It does not replace clinical judgment.

---

## Account & Privacy

### Account Management

- **Register** at first launch with a username and password
- **Profile** — Update avatar, email at `/api/auth/me`
- **Email Verification** — Optional; requires SMTP configuration (see [Configuration](configuration.md))

### API Keys

For programmatic access (MCP tools, scripts):

1. Go to **API Keys** in settings
2. Click **Create New Key**
3. Copy the key (shown only once!)
4. Use in requests: `X-API-Key: minta_...`

### Data Privacy

- All data is stored **locally** on your machine
- **Export** all your data: `GET /api/user/export-data`
- **Delete** all your data: `DELETE /api/user/delete-data`
- Sensitive data (API keys, passwords, emails) is **automatically filtered** from stored content
- See [SECURITY.md](../../SECURITY.md) for vulnerability reporting

---

## Troubleshooting

### "Minta won't start"

```bash
# Check if something is already on port 8772
netstat -ano | grep 8772

# Kill existing process and retry
minta stop
minta start

# Check logs
cat logs/minta-$(date +%Y-%m-%d).log
```

### "SMTP warning on startup"

This is normal. SMTP is only needed for email verification. If you don't need email verification, ignore the warning. To configure it, see [Configuration](configuration.md).

### "Login fails with 'not authenticated'"

1. Make sure you registered first
2. Check your username/password
3. JWT tokens expire after 24 hours — log in again

### "Context objects show 0 items"

1. Have you created any memory objects yet? Try `minta start` → `/story` to seed demo data
2. Check the type filter isn't hiding everything
3. Run `python -c "from server.config import engine, Base; Base.metadata.create_all(bind=engine)"` to ensure tables exist

### "Search returns no results"

1. Make sure you have memory objects with content
2. Semantic search needs the embedding service to be available
3. Try a simpler query or browse without search first

### "Port 18721 already in use"

The MCP HTTP server uses port 18721. If it's taken:
```bash
MCP_HTTP_PORT=18722 minta start
```

---

## Next Steps

- [Configuration Guide](configuration.md) — Set up MySQL, SMTP, and advanced settings
- [MCP Integration](mcp-integration.md) — Connect Minta to Claude Code and other AI tools
- [Contributing](../../CONTRIBUTING.md) — Help improve Minta
