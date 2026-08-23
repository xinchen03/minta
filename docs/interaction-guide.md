# Interaction Guide: How Minta Talks to Your Agent

> The three ways to drive Minta: **hooks** (automatic), **commands** (explicit),
> and **natural language** (what you say to the agent). This guide maps all three.

---

## 1. Hooks — What Happens Automatically

Hooks are the automatic layer. They run *without you asking*. Installed via
Claude Code `settings.json` (see `mcp-integration.md`) — all fail-open: if the
Minta API is unreachable, your session keeps working in a degraded state.

| Hook event | What Minta does at that moment |
|---|---|
| `SessionStart` | Double-insurance MCP connection: tries to reconnect to 18721 + loads context |
| `UserPromptSubmit` | Stage detection (research → evidence_collection etc.) + counter-example capture + expert-domain injection |
| `PreToolUse` | Minimal security hard-gates only (never blocks normal work) |
| `PostToolUse` | Detects *correction signals* in tool output (e.g. "不对", "应该先…") → captures as counter-example |
| `PostToolUseFailure` | Failed tool calls are auto-marked as counter-examples (R5C pipeline) |
| `PreCompact` | Flushes current state *before* context compression (nothing is lost) |
| `Stop` | Reflection pass + research auto-checkpoint (throttled: max once per X minutes) |
| `SessionEnd` | Best-effort flush + event log write |

Everything the hooks capture lands in the **Inbox** (pending), where you
confirm or discard — nothing modifies your memory silently.

## 2. Commands — Explicit Controls

```
/反例开启          start the counter-example capture server (port 18720)
/反例关闭          stop it
/反例              register a counter-example manually
/反例面板          open the review panel (web)
/project-new       create a project (academic-paper / math-model competition...)
/project-status    show project state + next gate
/resume            resume the latest checkpoint
```

Counter-examples, once confirmed, become **lesson-learned** context objects
that change future behavior — this is the correction loop, not a log.

## 3. Natural Language — Say What You Mean

You don't need to know tool names. The agent routes based on *intent*:

| You say | Effect |
|---|---|
| “记住:以后 X 步骤用 Y” | `write_context` → preference/workflow object, typed & searchable |
| “不对!应该先 Z” | Correction signal → Inbox candidate, you confirm or discard |
| “这个和上次说的一样 / 重复了” | Redundancy detection → merge suggestion (lifecycle scan) |
| “查一下我之前关于 … 的记录” | Hybrid retrieval (vector + BM25 + entities + tags) |
| “审计知识库 / 知识库健康” | `kb-audit` skill: stale / misclassified / broken links / orphans |
| “帮我看看这篇稿子符不符合投稿要求” | `runtime/compliance/` manuscript inventory + rule evaluator |
| “按这个论文做 PPT / 精读 / 校验引用 / 画图” | Companion skills (nature-skills, see README) |
| Expert domains: 踝 / 膝 / 颈椎 / 标准 / PRISMA questions | `minta_chat` → domain routing → expert inference with confidence |

## 4. Effects Overview

```
Memory quality  → stale/conflict/redundant/fragmented are found, not just stored
Correction loop → what you correct becomes a rule (after confirmation)
Research states → stage detection: the agent knows which stage you're in
Expert domains → calibrated inference + confidence (engine tier, see README)
```

**Rule of thumb:** automatic (hooks) for hygiene, explicit (commands) for
control, natural language for everything else. All three converge on the same
memory, same inbox, same audit trail.
