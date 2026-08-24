# @xxinchen/dsh-plugin

Minta — context quality layer for DeepSeek Harness.

Installing this package composes two Cordis rows into a DSH profile:

- `mcp-client-minta` — official `@deepseek-ai/dsh-mcp-client` wired to the local
  Minta engine's streamable-HTTP endpoint (its 19 `minta_*` tools reach the agent).
- `minta-plugin` — this package as a real Cordis plugin. At mount it registers a
  runtime skill (`minta-memory-governance`, content derived from the Minta
  interaction guide) and a `agent/session-start` hook that prewarms engine
  health + recent memory over the Minta REST API (fail-open: an unreachable
  engine never breaks a session).

The memory engine itself is a separately deployed service (see Prerequisites);
the plugin is a thin DSH-native surface over it. See `docs/dsh-integration.md`
for the verified end-to-end flow.

## Prerequisites

- DeepSeek Harness (`npx @deepseek-ai/dsh web`)
- Minta engine running locally: `python minta_cli.py start` (serves MCP at
  127.0.0.1:18721 and API at 8772), or `docker compose up -d`

## Install (verified 2026-08-23)

```bash
dsh plugin --profile web add @xxinchen/dsh-plugin
```

Restart `dsh web`. The MCP client row is composed automatically — no manual
config editing. Verify in a new session: "list all tools whose name contains
minta" → the 19 `mcp__minta__*` tools.

Note: the engine must be running before the tools respond; `failOnStartupError:
false` means a stopped engine does not break DSH sessions.

## Using Minta in a session

1. **Keep the engine running** — `python minta_cli.py start` (or Docker).
2. After `dsh plugin add` + one restart of `dsh web`, start a new session and
   ask: *"list all tools whose name contains minta"* — expect the 19
   `mcp__minta__*` tools. If they are absent, restart `dsh web` once more.
3. **First session**: call `minta_login` (your Minta credentials) so the tools
   operate with your identity.
4. **Automatically at session start**: the plugin checks engine health and
   recent memory (logged; never blocks the session). The skill
   `minta-memory-governance` is registered and available to the model.
5. **Manual first answer**: say *"用 Minta 先把记忆找出来再回答"* — or just ask
   about prior work; the skilled model will `minta_search_context` first.
6. **To save something durable**: tell the model to remember it — it will
   `minta_append_inbox`, and you confirm or discard in the Minta UI
   (`http://127.0.0.1:8772`, inbox review). Your memory is never edited
   silently.
7. **Engine stopped / unreachable**: sessions keep working; tools and prewarm
   just report unavailable (fail-open).

## Minta agent preset (per-turn protocol)

For turn-level automation (DSH rc.2 has no per-step/turn-end events, so the
protocol is carried by the preset persona, which the model follows every
turn), install the preset shipped in this package:

```bash
mkdir -p ~/.dsh/.agent-presets
cp -r <node_modules>/@xxinchen/dsh-plugin/presets/minta ~/.dsh/.agent-presets/  # or cp -r the repo's dsh-plugin/presets/minta
```

Then, in DSH, pick **Minta** in the session preset picker — or set it as the
default by overriding the `agent-presets` row (in `~/.dsh/profiles/web/cordis.patch.yml`):

```yaml
- id: agent-presets
  config:
    default: minta
```

The preset persona adds the per-turn protocol: `minta_autopilot_preflight`
before answering about prior work, `minta_autopilot_postflight` after each
reply, inbox-only writes, and graceful degradation when the engine is offline.

### Migrating from the manual `cordis.patch.yml` block

If you previously set Minta up by appending the `mcp-client-minta` block to
`~/.dsh/profiles/web/cordis.patch.yml`, **remove that block before installing
this plugin**. The bundle patch and the manual block insert the same loader
entry id `mcp-client-minta`; with both present the profile fails to boot with
`duplicate loader entry id: mcp-client-minta`. Check you are clean with:

```bash
grep -A6 mcp-client-minta ~/.dsh/profiles/web/cordis.patch.yml   # expect no output
```

(A patch file containing only `[]` is valid and means "no overrides".)

## Manual alternative (no npm install)

Append to `~/.dsh/profiles/web/cordis.patch.yml`:

```yaml
- insert:
    - id: mcp-client-minta
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: streamable-http
        serverName: minta
        url: http://127.0.0.1:18721/mcp
        failOnStartupError: false
```

## Roadmap and known boundaries

Shipped: MCP wiring, runtime skill registration, session-start prewarm.

Not here yet (and why):
- **Automatic pre/post-flight per turn** — DeepSeek Harness 0.1.1-rc.2 exposes
  no per-step or turn-end agent events, so per-message autopilot stays a
  model-facing tool call (`minta_autopilot_preflight` / `minta_autopilot_postflight`,
  instructed by the registered skill) rather than a hidden automatic hook.
- **Prompt injection of the prewarm result** — the profile-level plugin cannot
  safely shadow the deployment persona (the prompt registry owns that slot);
  prewarm currently logs engine state, and the agent reads memory on demand
  through the MCP tools.
