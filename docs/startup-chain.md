# Startup Order: Services First, Agent Second

> Minta's launcher design, documented for self-hosters. The handshake order
> is deliberate — an MCP client that starts before the MCP/API server sees an
> empty tool list and never re-negotiates.

## The Design

```
1. Start services            API 8772 → Autopilot → MCP HTTP 18721 (+ optional counter 18720)
2. Verify runtime identity   health check + version probe
3. Start the agent           Claude Code / Codex / Cursor / dsh — YOUR choice, or none
```

The agent step is **optional and pluggable**. Use Minta as:

- a pure API/DB backend (skip step 3 entirely),
- an editor memory layer (point any MCP-capable editor at `http://127.0.0.1:18721/mcp`),
- or a DeepSeek Harness sidecar (see `dsh-integration.md`).

## Commands

```bash
# 1. services only
python minta_cli.py start

# 2. connect your agent (choose one)
claude                 # Claude Code
codex                  # Codex CLI
npx @deepseek-ai/dsh web   # DeepSeek Harness
# or open Cursor / Cline / 通义灵码 and add the MCP server manually
```

## Why the Order Matters

- `minta_cli.py status` → all three services green, then handshake.
- MCP relies on the HTTP endpoint being up before the editor enumerates tools;
  a late server yields `tools/list` failures that agents rarely retry.
- The launcher kills orphaned ports first (8772/18721/18730) so a stale half
  stack never survives a restart.

## Optional Convenience

The local launcher (`start_minta_next.bat`) bundles this sequence and can
launch a preferred agent afterward. Self-hosters can wrap the two commands
above in their own script — no agent is required.
