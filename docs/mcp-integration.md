# MCP Integration Guide

Connect Minta to Claude Code, Cursor, and other AI tools via the Model Context Protocol (MCP).

---

## Table of Contents

1. [What is MCP?](#what-is-mcp)
2. [Claude Code Integration](#claude-code-integration)
3. [Cursor Integration](#cursor-integration)
4. [Custom Agent Integration](#custom-agent-integration)
5. [MCP Tool Reference](#mcp-tool-reference)
6. [HTTP Transport (Remote)](#http-transport-remote)
7. [Troubleshooting](#troubleshooting)

---

## What is MCP?

The **Model Context Protocol (MCP)** is an open standard that lets AI agents securely connect to external tools and data sources. Minta exposes its memory management features as MCP tools, so your AI agent can:

- **Read** your preferences, rules, and project context before answering
- **Write** new memories when it learns something about you
- **Capture** corrections when you point out mistakes (counter-examples)
- **Search** your memory for relevant past context
- **Manage** your inbox of pending memory reviews

Minta provides two MCP transports:
1. **Standard MCP (stdio)** — For local tools like Claude Code
2. **HTTP MCP** — For remote agents and custom integrations (port 18721)

---

## Claude Code Integration

### Step 1: Start Minta

```bash
minta start
# Dashboard: http://localhost:8772
# MCP HTTP:  http://localhost:18721/mcp
```

### Step 2: Configure Claude Code MCP

Add Minta to your Claude Code MCP configuration file:

**macOS/Linux:** `~/.claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "minta": {
      "command": "python",
      "args": ["-m", "server.minta_mcp"],
      "env": {
        "MINTA_API_KEY": "minta_your_api_key_here",
        "MINTA_API_URL": "http://127.0.0.1:8772"
      }
    }
  }
}
```

### Step 3: Find Your API Key

```bash
# The API key is in the .minta_api_key file
cat .minta_api_key

# Or check the env var
echo $MINTA_API_KEY
```

### Step 4: Restart Claude Code

After adding the MCP config, restart Claude Code. You should see Minta tools available.

### Step 5: Test It

In Claude Code, try:

```
Can you read my Minta context and tell me what preferences I have saved?
```

Claude Code will call `minta_read_context` with `type_filter="preference"` and summarize what it finds.

### Available Tools in Claude Code

Once connected, Claude Code gains these Minta tools:

| Tool | What Claude Can Do |
|------|-------------------|
| `minta_read_context` | Read your memory objects (filter by type) |
| `minta_write_context` | Write a new memory object |
| `minta_search_context` | Search your memory semantically |
| `minta_get_pack` | Generate a full context pack for the session |
| `minta_append_inbox` | Add a correction or observation to your inbox |
| `minta_list_inbox` | Check your pending inbox items |
| `minta_confirm_inbox` | Confirm and convert an inbox item to memory |
| `minta_get_slot` | Read a specific memory slot |
| `minta_update_slot` | Update a memory slot's content |
| `minta_autopilot_preflight` | Read relevant memory before answering |
| `minta_autopilot_postflight` | Check if memory should be written after answering |

---

## Cursor Integration

### Method 1: Via MCP JSON (Recommended)

Add to your Cursor MCP configuration (`.cursor/mcp.json` in your project or global Cursor settings):

```json
{
  "mcpServers": {
    "minta": {
      "command": "python",
      "args": ["-m", "server.minta_mcp"],
      "env": {
        "MINTA_API_KEY": "minta_your_api_key_here",
        "MINTA_API_URL": "http://127.0.0.1:8772"
      }
    }
  }
}
```

### Method 2: Via HTTP Transport

If you prefer the HTTP transport (useful for remote Cursor sessions):

```json
{
  "mcpServers": {
    "minta": {
      "type": "http",
      "url": "http://localhost:18721/mcp"
    }
  }
}
```

> 💡 The HTTP transport is also useful when running Minta on a remote server. Change `localhost` to your server's address.

---

## Custom Agent Integration

### Via MCP stdio (Python)

```python
import subprocess
import json

def call_minta_tool(tool_name: str, arguments: dict) -> dict:
    """Call a Minta MCP tool via stdio."""
    proc = subprocess.Popen(
        ["python", "-m", "server.minta_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **__import__("os").environ,
            "MINTA_API_KEY": "minta_your_api_key",
            "MINTA_API_URL": "http://127.0.0.1:8772",
        }
    )

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()

    # Read response
    response_line = proc.stdout.readline()
    proc.terminate()
    return json.loads(response_line)

# Example: Read preferences
result = call_minta_tool("minta_read_context", {
    "username": "your_username",
    "password": "your_password",
    "type_filter": "preference",
})
print(result)
```

### Via HTTP API (Any Language)

```python
import requests

MINTA_API = "http://127.0.0.1:8772"
API_KEY = "minta_your_api_key"

# Login and get JWT token
resp = requests.post(f"{MINTA_API}/api/auth/login", json={
    "username": "your_username",
    "password": "your_password",
})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "X-API-Key": API_KEY}

# Read context objects
resp = requests.get(f"{MINTA_API}/api/contextObjects?type=preference", headers=headers)
for obj in resp.json():
    print(f"[{obj['type']}] {obj['title']}: {obj['summary']}")

# Write a new memory
resp = requests.post(f"{MINTA_API}/api/contextObjects", headers=headers, json={
    "type": "lesson_learned",
    "title": "Use httpx instead of requests for async",
    "summary": "In our async codebase, always use httpx.AsyncClient, not requests.",
    "tags": ["python", "async", "http-client"],
    "confidence": 4,
})
print(resp.json())

# Generate a context pack
resp = requests.get(f"{MINTA_API}/api/slots/pack/generate?scene=coding", headers=headers)
context_pack = resp.json()
print(context_pack["pack"])
```

### Via MCP HTTP Transport

The MCP HTTP server runs on port 18721 by default:

```python
import requests
import json

MCP_URL = "http://localhost:18721/mcp"

# MCP JSON-RPC call
def mcp_call(tool_name: str, arguments: dict) -> dict:
    resp = requests.post(MCP_URL, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    })
    return resp.json()

# Read workflow-type memories
result = mcp_call("minta_read_context", {
    "username": "your_username",
    "password": "your_password",
    "type_filter": "workflow",
})
print(json.dumps(result, indent=2))
```

---

## MCP Tool Reference

### Authentication Tools

#### `minta_login`

Login to Minta. Required before using other tools that need authentication.

```json
{
  "username": "string (required)",
  "password": "string (required)"
}
```

### Context Reading Tools

#### `minta_read_context`

List your memory objects, optionally filtered by type.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "type_filter": "string (optional) - preference, workflow, project_context, decision_criteria, lesson_learned, writing_style, rule, ai_brief, work_profile"
}
```

#### `minta_search_context`

Search your memory objects by semantic similarity.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "query": "string (required) - natural language search query"
}
```

#### `minta_get_pack`

Generate a Context Pack from your memory slots. This is the primary way to inject your personal context into an AI session.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "scene": "string (optional) - auto, coding, writing, research, general (default: auto)"
}
```

#### `minta_get_slot`

Read a single memory slot.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "label": "string (required) - persona, preferences, knowledge, counter_examples, skills, pending, rules"
}
```

### Context Writing Tools

#### `minta_write_context`

Write a new memory object.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "title": "string (required) - short descriptive name",
  "type": "string (required) - one of the 9 types",
  "summary": "string (optional) - one-sentence description",
  "body": "string (optional) - full details",
  "tags": "string (optional) - comma-separated, e.g. 'python,testing,async'"
}
```

#### `minta_update_slot`

Update a memory slot's content.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "label": "string (required) - persona, preferences, knowledge, counter_examples, skills, pending, rules",
  "content": "string (required) - new slot content"
}
```

### Inbox Tools

#### `minta_append_inbox`

Add a correction, observation, or finding to your inbox.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "text": "string (required) - the correction or observation",
  "confidence": "number (optional) - 0.0 to 1.0, default 0.8",
  "tags": "string (optional) - comma-separated"
}
```

#### `minta_list_inbox`

List items in your inbox.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "status": "string (optional) - pending or archived (default: pending)"
}
```

#### `minta_confirm_inbox`

Confirm an inbox item and convert it to a memory object.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "inbox_id": "integer (required)",
  "context_type": "string (optional) - type for the new context object"
}
```

#### `minta_discard_inbox`

Discard an inbox item (false positive or not useful).

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "inbox_id": "integer (required)"
}
```

### Expert System Tools

#### `minta_expert_infer`

Run expert inference for a clinical domain.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "message": "string (required) - patient case description",
  "domain": "string (required) - ankle_injury, knee_injury, cervical_spine_injury"
}
```

#### `minta_expert_list`

List all available expert domains with rule counts and trust levels.

```json
{
  "username": "string (required)",
  "password": "string (required)"
}
```

#### `minta_expert_consult`

Cross-domain expert consultation.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "message": "string (required) - case description",
  "primary_domain": "string (required)",
  "consult_domain": "string (required)"
}
```

#### `minta_expert_trust`

Get trust metrics for a domain expert.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "domain": "string (required)"
}
```

#### `minta_expert_feedback`

Submit feedback on an expert inference.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "log_id": "integer (required)",
  "signal": "string (required) - positive or negative"
}
```

### Chat Tool

#### `minta_chat`

Main chat interface with automatic domain detection.

```json
{
  "username": "string (required)",
  "password": "string (required)",
  "message": "string (required) - natural language message"
}
```

### Autopilot Tools (No Auth — Uses API Key)

#### `minta_autopilot_preflight`

Read relevant memory before answering a user message. Uses API key for auth.

```json
{
  "user_message": "string (required) - the user's message to analyze",
  "project_id": "string (optional) - project identifier for context filtering"
}
```

#### `minta_autopilot_postflight`

Check if memory should be written after an interaction. Uses API key for auth.

```json
{
  "user_message": "string (required) - the user's original message",
  "assistant_response": "string (required) - the assistant's response",
  "project_id": "string (optional) - project identifier"
}
```

---

## HTTP Transport (Remote)

The MCP HTTP server is for remote agents that can't spawn a local stdio process.

### Starting the HTTP Server

```bash
# Via CLI (default port 18721)
minta start

# Standalone (for debugging or custom port)
python -m server.minta_mcp_http
# → Listening on http://0.0.0.0:18721/mcp

# Custom port
MCP_HTTP_PORT=18722 python -m server.minta_mcp_http
```

### Endpoint

```
POST http://localhost:18721/mcp
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "minta_read_context",
    "arguments": {
      "username": "...",
      "password": "...",
      "type_filter": "preference"
    }
  }
}
```

### Supported MCP Methods

| Method | Description |
|--------|-------------|
| `initialize` | MCP handshake |
| `tools/list` | List all 19 available tools |
| `tools/call` | Call a specific tool |

> ⚠️ **Security note:** The HTTP MCP server binds to `127.0.0.1` when launched via `minta start`. Only the standalone mode binds to `0.0.0.0`. Do not expose the MCP HTTP port to the public internet without authentication.

---

## Troubleshooting

### "Tool not found" in Claude Code

1. Check that Minta is running: `minta status`
2. Verify the MCP configuration file path
3. Restart Claude Code after adding the MCP config
4. Check the API key is correct: `cat .minta_api_key`

### "Not authenticated" error

1. Make sure you've registered a user account first (via the dashboard or API)
2. For autopilot tools (`preflight`, `postflight`), check `MINTA_API_KEY` is set
3. For user tools, check username/password are correct

### "Connection refused" on port 18721

```bash
# Check if MCP HTTP server is running
netstat -ano | grep 18721

# If not, start Minta
minta start

# Or start standalone
python -m server.minta_mcp_http
```

### MCP stdio process hangs

If the stdio MCP process doesn't exit cleanly:

```bash
# Kill stale MCP processes
pkill -f "minta_mcp"

# Or on Windows
taskkill /F /IM python.exe /FI "WINDOWTITLE eq minta_mcp*"
```

### Adding Minta to a Remote Server

If Minta runs on a different machine:

1. **Security first:** Set up an SSH tunnel (recommended) or use HTTPS with authentication
2. Use the HTTP transport with the remote URL
3. Set `MINTA_CORS_ORIGINS` to include the remote client's origin

```bash
# SSH tunnel (safe — no exposure)
ssh -L 18721:localhost:18721 user@your-server

# Then connect to localhost:18721 as if Minta were local
```
