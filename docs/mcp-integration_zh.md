# Minta MCP 集成指南

> 🌐 中文 | [English](mcp-integration.md)

将 Minta 接入 Claude Code、Cursor 及自定义 AI Agent，通过 Model Context Protocol（MCP）。

---

## 目录

1. [什么是 MCP](#什么是-mcp)
2. [Claude Code 集成](#claude-code-集成)
3. [Cursor 集成](#cursor-集成)
4. [自定义 Agent 集成](#自定义-agent-集成)
5. [MCP 工具参考](#mcp-工具参考)
6. [HTTP 传输（远程）](#http-传输远程)
7. [故障排除](#故障排除)

---

## 什么是 MCP

**Model Context Protocol（MCP）** 是一个开放标准，让 AI agent 安全地连接到外部工具和数据源。Minta 通过 MCP 工具暴露其记忆管理功能，让你的 AI agent 能够：

- **读取**你的偏好、规则和项目上下文（回答前自动载入）
- **写入**新记忆（当了解到关于你的新信息时）
- **捕获**纠正（当你指出错误时自动记录反例）
- **搜索**与当前话题相关的历史记忆
- **管理**收件箱中待审查的记忆

Minta 提供两种 MCP 传输方式：
1. **标准 MCP（stdio）** — 用于 Claude Code 等本地工具
2. **HTTP MCP** — 用于远程 agent 和自定义集成（端口 18721）

---

## Claude Code 集成

### 第一步：启动 Minta

```bash
minta start
# 仪表盘：http://localhost:8772
# MCP HTTP：http://localhost:18721/mcp
```

### 第二步：配置 Claude Code MCP

在 Claude Code MCP 配置文件中添加 Minta：

**macOS/Linux：** `~/.claude/claude_desktop_config.json`
**Windows：** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "minta": {
      "command": "python",
      "args": ["-m", "server.minta_mcp"],
      "env": {
        "MINTA_API_KEY": "minta_你的API密钥",
        "MINTA_API_URL": "http://127.0.0.1:8772"
      }
    }
  }
}
```

### 第三步：找到你的 API 密钥

```bash
# API 密钥在 .minta_api_key 文件里
cat .minta_api_key

# 或检查环境变量
echo $MINTA_API_KEY
```

### 第四步：重启 Claude Code

添加 MCP 配置后，重启 Claude Code。你就能在工具列表中看到 Minta 工具了。

### 第五步：测试

在 Claude Code 中试试：

```
帮我读一下我的 Minta 记忆，看看我保存了哪些偏好。
```

Claude Code 会调用 `minta_read_context`（`type_filter="preference"`）并总结找到的内容。

### Claude Code 中可用的工具

接入后，Claude Code 获得以下 Minta 工具：

| 工具 | Claude 能做什么 |
|------|----------------|
| `minta_read_context` | 读取你的记忆对象（可按类型过滤） |
| `minta_write_context` | 写入新的记忆对象 |
| `minta_search_context` | 语义搜索你的记忆 |
| `minta_get_pack` | 生成当前会话的完整上下文包 |
| `minta_append_inbox` | 把纠正或观察添加到你的收件箱 |
| `minta_list_inbox` | 查看待处理的收件箱条目 |
| `minta_confirm_inbox` | 确认收件箱条目并转为记忆对象 |
| `minta_get_slot` | 读取特定记忆槽位 |
| `minta_update_slot` | 更新记忆槽位内容 |
| `minta_autopilot_preflight` | 回答前读取相关记忆 |
| `minta_autopilot_postflight` | 回答后检查是否需要写入记忆 |

---

## Cursor 集成

### 方式一：通过 MCP JSON（推荐）

在 Cursor MCP 配置中添加（项目 `.cursor/mcp.json` 或全局 Cursor 设置）：

```json
{
  "mcpServers": {
    "minta": {
      "command": "python",
      "args": ["-m", "server.minta_mcp"],
      "env": {
        "MINTA_API_KEY": "minta_你的API密钥",
        "MINTA_API_URL": "http://127.0.0.1:8772"
      }
    }
  }
}
```

### 方式二：通过 HTTP 传输

如果更喜欢 HTTP 传输（适合远程 Cursor 会话）：

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

> 💡 HTTP 传输也适合 Minta 运行在远程服务器的场景。把 `localhost` 换成服务器地址即可。

---

## 自定义 Agent 集成

### 通过 MCP stdio（Python）

```python
import subprocess
import json

def call_minta_tool(tool_name: str, arguments: dict) -> dict:
    """通过 stdio 调用 Minta MCP 工具"""
    proc = subprocess.Popen(
        ["python", "-m", "server.minta_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **__import__("os").environ,
            "MINTA_API_KEY": "minta_你的API密钥",
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

    # 读取响应
    response_line = proc.stdout.readline()
    proc.terminate()
    return json.loads(response_line)

# 示例：读取偏好
result = call_minta_tool("minta_read_context", {
    "username": "你的用户名",
    "password": "你的密码",
    "type_filter": "preference",
})
print(result)
```

### 通过 HTTP API（任意语言）

```python
import requests

MINTA_API = "http://127.0.0.1:8772"
API_KEY = "minta_你的API密钥"

# 登录获取 JWT token
resp = requests.post(f"{MINTA_API}/api/auth/login", json={
    "username": "你的用户名",
    "password": "你的密码",
})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}", "X-API-Key": API_KEY}

# 读取记忆对象
resp = requests.get(f"{MINTA_API}/api/contextObjects?type=preference", headers=headers)
for obj in resp.json():
    print(f"[{obj['type']}] {obj['title']}: {obj['summary']}")

# 写入新记忆
resp = requests.post(f"{MINTA_API}/api/contextObjects", headers=headers, json={
    "type": "lesson_learned",
    "title": "异步代码用 httpx 而非 requests",
    "summary": "在我们的异步代码中，始终使用 httpx.AsyncClient，不要用 requests",
    "tags": ["python", "async", "http-client"],
    "confidence": 4,
})
print(resp.json())

# 生成上下文包
resp = requests.get(f"{MINTA_API}/api/slots/pack/generate?scene=coding", headers=headers)
context_pack = resp.json()
print(context_pack["pack"])
```

### 通过 MCP HTTP 传输

MCP HTTP 服务默认在端口 18721 运行：

```python
import requests
import json

MCP_URL = "http://localhost:18721/mcp"

def mcp_call(tool_name: str, arguments: dict) -> dict:
    """MCP JSON-RPC 调用"""
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

# 读取 workflow 类型的记忆
result = mcp_call("minta_read_context", {
    "username": "你的用户名",
    "password": "你的密码",
    "type_filter": "workflow",
})
print(json.dumps(result, indent=2, ensure_ascii=False))
```

---

## MCP 工具参考

### 认证工具

#### `minta_login`

登录 Minta。使用需要认证的工具前必须先调用。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）"
}
```

### 记忆读取工具

#### `minta_read_context`

列出你的记忆对象，可按类型过滤。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "type_filter": "字符串（可选）— preference, workflow, project_context, decision_criteria, lesson_learned, writing_style, rule, ai_brief, work_profile"
}
```

#### `minta_search_context`

语义搜索你的记忆对象。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "query": "字符串（必填）— 自然语言搜索查询"
}
```

#### `minta_get_pack`

从你的记忆槽位生成上下文包。这是将你的个人上下文注入 AI 会话的主要方式。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "scene": "字符串（可选）— auto, coding, writing, research, general（默认 auto）"
}
```

#### `minta_get_slot`

读取单个记忆槽位。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "label": "字符串（必填）— persona, preferences, knowledge, counter_examples, skills, pending, rules"
}
```

### 记忆写入工具

#### `minta_write_context`

写入新的记忆对象。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "title": "字符串（必填）— 简短描述性名称",
  "type": "字符串（必填）— 9 种类型之一",
  "summary": "字符串（可选）— 一句话说明",
  "body": "字符串（可选）— 完整细节",
  "tags": "字符串（可选）— 逗号分隔，如 'python,测试,异步'"
}
```

#### `minta_update_slot`

更新记忆槽位内容。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "label": "字符串（必填）— persona, preferences, knowledge, counter_examples, skills, pending, rules",
  "content": "字符串（必填）— 新槽位内容"
}
```

### 收件箱工具

#### `minta_append_inbox`

将纠正、观察或发现添加到收件箱。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "text": "字符串（必填）— 纠正或观察内容",
  "confidence": "数值（可选）— 0.0 到 1.0，默认 0.8",
  "tags": "字符串（可选）— 逗号分隔"
}
```

#### `minta_list_inbox`

列出收件箱条目。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "status": "字符串（可选）— pending 或 archived（默认 pending）"
}
```

#### `minta_confirm_inbox`

确认收件箱条目并转为记忆对象。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "inbox_id": "整数（必填）",
  "context_type": "字符串（可选）— 新记忆对象的类型"
}
```

#### `minta_discard_inbox`

丢弃收件箱条目（误报或无用的）。

```json
{
  "username": "字符串（必填）",
  "password": "字符串（必填）",
  "inbox_id": "整数（必填）"
}
```

### Autopilot 工具（无需用户名密码 — 使用 API Key）

#### `minta_autopilot_preflight`

在回答用户消息之前读取相关记忆。使用 API Key 认证。

```json
{
  "user_message": "字符串（必填）— 用户的消息",
  "project_id": "字符串（可选）— 项目标识符，用于上下文过滤"
}
```

#### `minta_autopilot_postflight`

在对话后检查是否需要写入记忆。使用 API Key 认证。

```json
{
  "user_message": "字符串（必填）— 用户的原始消息",
  "assistant_response": "字符串（必填）— AI 的回复",
  "project_id": "字符串（可选）— 项目标识符"
}
```

---

## HTTP 传输（远程）

MCP HTTP 服务器用于无法启动本地 stdio 进程的远程 agent。

### 启动 HTTP 服务

```bash
# 通过 CLI（默认端口 18721）
minta start

# 独立运行（调试或自定义端口）
python -m server.minta_mcp_http
# → 监听 http://0.0.0.0:18721/mcp

# 自定义端口
MCP_HTTP_PORT=18722 python -m server.minta_mcp_http
```

### 端点

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
      "username": "……",
      "password": "……",
      "type_filter": "preference"
    }
  }
}
```

### 支持的 MCP 方法

| 方法 | 说明 |
|------|------|
| `initialize` | MCP 握手 |
| `tools/list` | 列出全部 19 个可用工具 |
| `tools/call` | 调用指定工具 |

> ⚠️ **安全提醒：** 通过 `minta start` 启动的 HTTP MCP 服务绑定 `127.0.0.1`。只有独立运行时才绑定 `0.0.0.0`。不要将 MCP HTTP 端口暴露到公网，除非配置了认证。

---

## 故障排除

### Claude Code 中提示 "Tool not found"

1. 确认 Minta 正在运行：`minta status`
2. 检查 MCP 配置文件路径是否正确
3. 添加 MCP 配置后重启 Claude Code
4. 确认 API 密钥正确：`cat .minta_api_key`

### "Not authenticated" 错误

1. 确认已先注册用户账号（通过仪表盘或 API）
2. Autopilot 工具（`preflight`、`postflight`）需要 `MINTA_API_KEY` 已设置
3. 普通用户工具需要用户名密码正确

### 端口 18721 "Connection refused"

```bash
# 检查 MCP HTTP 服务是否运行
netstat -ano | grep 18721

# 没运行的话启动 Minta
minta start

# 或独立启动
python -m server.minta_mcp_http
```

### MCP stdio 进程挂起

如果 stdio MCP 进程无法正常退出：

```bash
# 杀掉残留 MCP 进程
pkill -f "minta_mcp"

# Windows
taskkill /F /IM python.exe /FI "WINDOWTITLE eq minta_mcp*"
```

### 在远程服务器上接入 Minta

如果 Minta 运行在另一台机器上：

1. **安全第一：** 建议用 SSH 隧道，或用 HTTPS + 认证
2. 使用 HTTP 传输 + 远程 URL
3. 设置 `MINTA_CORS_ORIGINS` 包含远程客户端的来源

```bash
# SSH 隧道（安全——不暴露端口）
ssh -L 18721:localhost:18721 user@你的服务器

# 然后像本地一样连接 localhost:18721
```
