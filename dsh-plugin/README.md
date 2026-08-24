# @xxinchen/dsh-plugin

Minta — context quality layer for DeepSeek Harness.

Installing this package adds the Minta MCP wiring to a DSH profile: it composes
the `mcp-client-minta` row (official `@deepseek-ai/dsh-mcp-client`) pointing at
the local Minta engine's streamable-HTTP endpoint. The capabilities — memory
quality governance, expert domains, claim-stage gates, 19 `minta_*` tools —
are provided by the Minta engine itself, which runs separately (see
Prerequisites). See `docs/dsh-integration.md` in the repo for the verified
end-to-end flow.

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

## Roadmap

The Minta skills and lifecycle plugin (autopilot pre/post-flight hooks) are
planned for a later release; today the package only wires the MCP client.
