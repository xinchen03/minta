# @minta/dsh-plugin

Minta — context quality layer for DeepSeek Harness.
Memory quality governance, expert domains, and claim-stage gates through the Minta MCP server.

## Prerequisites

- DeepSeek Harness (`npx @deepseek-ai/dsh web`)
- Minta engine running locally: `python minta_cli.py start` (serves MCP at 127.0.0.1:18721 and API at 8772)

## Install (verified 2026-08-23)

Minta MCP server connects via the DSH `mcp-client` plugin — see
`docs/dsh-integration.md` for the exact `cordis.patch.yml` insert.

```
# ~/.dsh/profiles/web/cordis.patch.yml
- insert:
    - id: mcp-client-minta
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: streamable-http
        serverName: minta
        url: http://127.0.0.1:18721/mcp
        failOnStartupError: false
```

Then restart `dsh web`. This package will carry the Minta skills and
lifecycle plugin in a later release.
