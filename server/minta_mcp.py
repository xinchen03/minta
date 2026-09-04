"""
Minta MCP Server — 让 Claude 通过工具直接读写 Minta API。
暴露 tools 给 Claude Code，不再写本地 .md 文件。
"""

import json
import os
import sys
import time
import urllib.parse
from typing import Any, Dict

import requests
import subprocess
import urllib.request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MINTA_API = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")
_api_key_env = os.environ.get("MINTA_API_KEY", "")
api_key_ready = False
if not _api_key_env:
    try:
        from config import MINTA_API_KEY as _config_key
        if _config_key:
            _api_key_env = _config_key
    except Exception:
        pass
API_KEY = _api_key_env

# ── Shared session with connection pooling + retry + timeout ──

_SESSION = None


def _get_session():
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=4,
            pool_maxsize=8,
        )
        _SESSION.mount("http://", adapter)
        _SESSION.mount("https://", adapter)
    return _SESSION


def _auth_headers(token: str = "") -> dict:
    """Build auth headers: prefer API Key (env var), fall back to Bearer token."""
    h = {"Content-Type": "application/json; charset=utf-8"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    elif token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _api(method: str, path: str, token: str = "", body: dict = None) -> dict:
    """Call Minta API and return JSON. 15s timeout, 3 retries on connection errors."""
    url = f"{MINTA_API}{path}"
    headers = _auth_headers(token)
    kwargs = dict(method=method, url=url, headers=headers, timeout=15)
    if body:
        kwargs["json"] = body
    try:
        resp = _get_session().request(**kwargs)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "API timeout after 15s"}
    except requests.exceptions.ConnectionError as e:
        return {"error": f"API connection failed (retries exhausted): {e}"}
    except requests.exceptions.HTTPError as e:
        try:
            err_body = e.response.text[:500]
        except Exception:
            err_body = "(unable to read response body)"
        return {"error": f"HTTP {e.response.status_code}: {err_body}"}
    except Exception as e:
        return {"error": str(e)}


TOKEN_CACHE: Dict[str, Dict[str, str]] = {}  # username -> {"token": str, "expires": float}


def _resolve_auth(username: str, password: str) -> str:
    """Unified auth: API Key takes precedence; falls back to username/password login.
    Returns token string, or empty string on failure."""
    # API Key mode — no username/password needed
    if API_KEY:
        return "__api_key__"
    # Username/password mode — must provide both
    if not username or not password:
        return ""
    cache_key = f"{username}:{password}"
    cached = TOKEN_CACHE.get(cache_key)
    if cached and cached["expires"] > time.time():
        return cached["token"]
    r = _api("POST", "/api/auth/login", body={"username": username, "password": password})
    if "accessToken" in r:
        TOKEN_CACHE[cache_key] = {"token": r["accessToken"], "expires": time.time() + 82800}
        return r["accessToken"]
    return ""


# ── MCP Tool Handlers ──

def minta_login(username: str, password: str) -> str:
    """登录 Minta 账号，返回登录结果。必须先登录才能用其他工具。"""
    token = _resolve_auth(username, password)
    if token:
        return f"✅ 登录成功 ({username})"
    return f"❌ 登录失败，请检查用户名密码"


def minta_read_context(username: str, password: str, type_filter: str = "") -> str:
    """读取用户的 Context Objects 列表。可传入 type_filter 按类型筛选。"""
    token = _resolve_auth(username, password)
    if not token:
        return "❌ 请先登录"
    qs = f"?type={urllib.parse.quote(type_filter)}" if type_filter else ""
    r = _api("GET", f"/api/contextObjects{qs}", token=token)
    if isinstance(r, list):
        if not r:
            return "📭 暂无 Context Objects"
        lines = [f"共 {len(r)} 条："]
        for item in r:
            lines.append(f"  • {item['title'][:50]} | {item['type']} | {item.get('source','?')}")
        return "\n".join(lines)
    return json.dumps(r, ensure_ascii=False)


def minta_write_context(username: str, password: str, title: str, type: str,
                        summary: str = "", body: str = "", tags: str = "") -> str:
    """写入一条 Context Object 到 Minta。
    type可选值: preference, workflow, project_context, decision_criteria, lesson_learned, writing_style, rule, ai_brief, work_profile"""
    try:
        token = _resolve_auth(username, password)
        if not token:
            return "❌ 请先登录"
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        body_data = {
            "title": title,
            "type": type,
            "summary": summary,
            "body": body,
            "tags": tag_list,
            "source": "conversation",
            "status": "active",
            "confidence": 4,
        }
        r = _api("POST", "/api/contextObjects", token=token, body=body_data)
        if "id" in r:
            return f"✅ 已保存为 Context Object: {r['id']}"
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        try:
            _dbg = os.environ.get("MINTA_MCP_DEBUG_LOG", "")
            if _dbg:
                with open(_dbg, "a", encoding="utf-8") as f:
                    f.write(f"=== minta_write_context CRASH ===\n{tb}\n")
        except Exception:
            pass
        return json.dumps({"error": f"write_context exception: {e}\n{tb}"})


def minta_append_inbox(username: str, password: str, text: str, confidence: float = 0.8, tags: str = "") -> str:
    """写入一条反例/提醒到 Inbox（收件箱）。
    当用户纠正你的行为、告诉你做错了什么时，立即调用此工具。"""
    token = _resolve_auth(username, password)
    if not token:
        return "❌ 请先登录"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    qs = f"?text={urllib.parse.quote(text)}&confidence={confidence}"
    r = _api("POST", f"/api/inbox/append{qs}", token=token, body=tag_list)
    if r.get("success"):
        return f"✅ 已写入 Inbox (id={r['id']})"
    return json.dumps(r, ensure_ascii=False)


def minta_search_context(username: str, password: str, query: str) -> str:
    """搜索 Context Objects（匹配标题、摘要、标签）。"""
    token = _resolve_auth(username, password)
    if not token:
        return "❌ 请先登录"
    r = _api("GET", "/api/contextObjects", token=token)
    if not isinstance(r, list):
        return json.dumps(r, ensure_ascii=False)
    q = query.lower()
    matched = [x for x in r if q in x.get("title", "").lower()
               or q in x.get("summary", "").lower()
               or any(q in t.lower() for t in x.get("tags", []))]
    if not matched:
        return f"🔍 未找到包含「{query}」的条目"
    lines = [f"找到 {len(matched)} 条："]
    for item in matched:
        lines.append(f"  • {item['title'][:50]} | {item['type']}")
    return "\n".join(lines)


# ── MCP Protocol: 工具定义 ──

def minta_list_inbox(username: str, password: str, status: str = "pending") -> str:
    """列出 Inbox 中的条目。"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("GET", f"/api/inbox?status={urllib.parse.quote(status)}", token=token)
    if isinstance(r, dict):
        items = r.get("pending", r.get("archived", []))
        if isinstance(items, list):
            r = items
    if isinstance(r, list):
        if not r:
            return "Inbox is empty"
        lines = [f'{len(r)} items:']
        for item in r[:20]:
            text = (item.get("text", "") if isinstance(item, dict) else str(item))[:100]
            lines.append(f'  [{item.get("id", "?")}] {text}')
        return "\n".join(lines)
    return json.dumps(r, ensure_ascii=False)


def minta_confirm_inbox(username: str, password: str, inbox_id: int, context_type: str = "lesson_learned") -> str:
    """确认一条 Inbox 条目，转为 Context Object。"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("POST", f"/api/inbox/{inbox_id}/confirm", token=token,
             body={"type": context_type})
    if r.get("success"):
        return f"Confirmed inbox #{inbox_id} -> {r.get('contextId', '?')}"
    return json.dumps(r, ensure_ascii=False)


def minta_discard_inbox(username: str, password: str, inbox_id: int) -> str:
    """丢弃一条 Inbox 条目。"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("POST", "/api/inbox/discard", token=token, body=[inbox_id])
    if r.get("success"):
        return f"Discarded inbox #{inbox_id}"
    return json.dumps(r, ensure_ascii=False)


def minta_get_pack(username: str, password: str, scene: str = "auto") -> str:
    """获取 Context Pack —— 从 7 个槽位自动生成的 AI 上下文注入文本。"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("GET", f"/api/slots/pack/generate?scene={urllib.parse.quote(scene)}", token=token)
    if isinstance(r, dict) and "content" in r:
        return r["content"]
    return json.dumps(r, ensure_ascii=False)


def minta_get_slot(username: str, password: str, label: str) -> str:
    """读取某个槽位的内容。label: persona/preferences/knowledge/counter_examples/skills/pending/rules"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("GET", f"/api/slots/{urllib.parse.quote(label)}", token=token)
    if isinstance(r, dict) and "content" in r:
        return f'[{r["label"]}] ({"auto" if r.get("autoReflected") else "manual"})\n{r["content"]}'
    return json.dumps(r, ensure_ascii=False)


def minta_update_slot(username: str, password: str, label: str, content: str) -> str:
    """更新某个槽位的内容。"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("PUT", f"/api/slots/{urllib.parse.quote(label)}", token=token,
             body={"content": content})
    if "id" in r:
        return f'Updated slot "{label}" ({len(content)} chars)'
    return json.dumps(r, ensure_ascii=False)


# ── Expert Inference Handlers ──

def minta_expert_infer(username: str, password: str, message: str, domain: str) -> str:
    """Run expert inference on a user message (symptom/question)."""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    session_id = f"mcp-{username}"
    body = {"message": message, "session_id": session_id, "domain": domain}
    r = _api("POST", "/api/expert/infer", token=token, body=body)
    return json.dumps(r, ensure_ascii=False)


def minta_expert_list(username: str, password: str) -> str:
    """List available experts and their rule counts."""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("GET", "/api/expert/meta/experts", token=token)
    if isinstance(r, list):
        if not r:
            return "暂无可用专家"
        lines = [f"共 {len(r)} 个专家："]
        for expert in r:
            domain = expert.get("domain", "?")
            rules = expert.get("ruleCount", expert.get("rule_count", 0))
            trust = expert.get("trustLevel", expert.get("trust_level", "N/A"))
            lines.append(f"  • {domain} | 规则数: {rules} | 信任等级: {trust}")
        return "\n".join(lines)
    return json.dumps(r, ensure_ascii=False)


def minta_expert_consult(username: str, password: str, message: str,
                          primary_domain: str, consult_domain: str) -> str:
    """Cross-domain consultation — ask another expert for opinion."""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    session_id = f"mcp-{username}"
    primary_body = {"message": message, "session_id": session_id, "domain": primary_domain}
    primary_r = _api("POST", "/api/expert/infer", token=token, body=primary_body)
    consult_body = {"message": message, "session_id": session_id, "domain": consult_domain}
    consult_r = _api("POST", "/api/expert/infer", token=token, body=consult_body)
    result = {
        "primary_domain": primary_domain,
        "primary_result": primary_r,
        "consult_domain": consult_domain,
        "consult_result": consult_r,
    }
    return json.dumps(result, ensure_ascii=False)


def minta_expert_trust(username: str, password: str, domain: str) -> str:
    """Get trust/confidence metrics (Goldman metrics) for a domain."""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    r = _api("GET", f"/api/expert/trust/{urllib.parse.quote(domain)}", token=token)
    return json.dumps(r, ensure_ascii=False)


def minta_expert_feedback(username: str, password: str, log_id: int, signal: str) -> str:
    """提交 Expert 推理反馈。signal 为 'positive'（诊断正确）或 'negative'（诊断错误）。"""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    if signal not in ("positive", "negative"):
        return "signal 必须为 'positive' 或 'negative'"
    body = {"log_id": log_id, "signal": signal}
    r = _api("POST", "/api/expert/feedback", token=token, body=body)
    if isinstance(r, dict) and r.get("ok"):
        return r.get("message", "反馈已记录")
    return json.dumps(r, ensure_ascii=False)


def minta_chat(username: str, password: str, message: str) -> str:
    """Main conversation entry — detects if message relates to any expert domain and routes."""
    token = _resolve_auth(username, password)
    if not token:
        return "请先登录"
    body = {"message": message}
    r = _api("POST", "/api/chat", token=token, body=body)
    if isinstance(r, dict):
        parts = []
        for key in ("response", "text", "result", "reply"):
            if key in r:
                parts.append(str(r[key])[:500])
                break
        suggested = r.get("suggestedExperts", r.get("suggested_experts"))
        if suggested:
            s = ", ".join(suggested) if isinstance(suggested, list) else str(suggested)
            parts.append(f"建议的专家: {s}")
        confirmed = r.get("expertConfirmed", r.get("expert_confirmed"))
        if confirmed:
            parts.append(f"已确认专家: {confirmed}")
        return "\n".join(parts) if parts else json.dumps(r, ensure_ascii=False)
    return json.dumps(r, ensure_ascii=False)


def handle_call(tool_name: str, arguments: dict) -> str:
    handlers = {
        "minta_login": minta_login,
        "minta_read_context": minta_read_context,
        "minta_write_context": minta_write_context,
        "minta_append_inbox": minta_append_inbox,
        "minta_search_context": minta_search_context,
        "minta_list_inbox": minta_list_inbox,
        "minta_confirm_inbox": minta_confirm_inbox,
        "minta_discard_inbox": minta_discard_inbox,
        "minta_get_pack": minta_get_pack,
        "minta_get_slot": minta_get_slot,
        "minta_update_slot": minta_update_slot,
        "minta_expert_infer": minta_expert_infer,
        "minta_expert_list": minta_expert_list,
        "minta_expert_consult": minta_expert_consult,
        "minta_expert_trust": minta_expert_trust,
        "minta_expert_feedback": minta_expert_feedback,
        "minta_chat": minta_chat,
    }
    # Autopilot tools don't need auth (use API key from env)
    if tool_name in ("minta_autopilot_preflight", "minta_autopilot_postflight"):
        return autopilot_handler(tool_name, arguments)
    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    # Inject default empty username/password when API_KEY is set (not needed for auth)
    arguments.setdefault("username", "")
    arguments.setdefault("password", "")
    return handler(**arguments)


TOOL_DEFINITIONS = [
    {
        "name": "minta_login",
        "description": "登录 Minta 账号。使用其他工具前必须先登录。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "Minta 用户名"},
                "password": {"type": "string", "description": "Minta 密码"},
            },
            "required": [],
        },
    },
    {
        "name": "minta_read_context",
        "description": "读取用户的 Context Objects 列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "type_filter": {"type": "string", "description": "按类型筛选（可选）"},
            },
            "required": [],
        },
    },
    {
        "name": "minta_write_context",
        "description": "写入一条 Context Object。当用户在对话中提到偏好、项目背景、决策、写作风格、工作流程、规则等时调用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "title": {"type": "string", "description": "标题"},
                "type": {"type": "string", "description": "类型: preference/workflow/project_context/decision_criteria/lesson_learned/writing_style/rule/ai_brief/work_profile"},
                "summary": {"type": "string", "description": "一句话摘要"},
                "body": {"type": "string", "description": "详细内容"},
                "tags": {"type": "string", "description": "逗号分隔的标签"},
            },
            "required": ["title", "type"],
        },
    },
    {
        "name": "minta_append_inbox",
        "description": "写入反例/纠正到 Inbox。当用户纠正你的行为、指出错误、告诉你正确做法时调用。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "text": {"type": "string", "description": "错误行为→正确做法"},
                "confidence": {"type": "number", "description": "置信度 0-1"},
                "tags": {"type": "string", "description": "逗号分隔的标签"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "minta_search_context",
        "description": "搜索 Context Objects。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "query": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "minta_list_inbox",
        "description": "列出 Inbox 收件箱条目。可筛选 status: pending 或 archived。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "status": {"type": "string", "description": "pending 或 archived"},
            },
            "required": [],
        },
    },
    {
        "name": "minta_confirm_inbox",
        "description": "确认一条 Inbox 条目，将其转为正式的 Context Object。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "inbox_id": {"type": "integer", "description": "Inbox 条目 ID"},
                "context_type": {"type": "string", "description": "Context 类型: lesson_learned/preference/rule/workflow 等"},
            },
            "required": ["inbox_id"],
        },
    },
    {
        "name": "minta_discard_inbox",
        "description": "丢弃一条 Inbox 条目。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "inbox_id": {"type": "integer", "description": "Inbox 条目 ID"},
            },
            "required": ["inbox_id"],
        },
    },
    {
        "name": "minta_get_pack",
        "description": "获取 Context Pack —— 从 7 个槽位自动生成的上下文文本，可直接粘贴到 AI 对话开头。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "scene": {"type": "string", "description": "场景: auto/coding/writing/research/general"},
            },
            "required": [],
        },
    },
    {
        "name": "minta_get_slot",
        "description": "读取某个槽位的内容。label: persona/preferences/knowledge/counter_examples/skills/pending/rules",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "label": {"type": "string", "description": "槽位标签"},
            },
            "required": ["label"],
        },
    },
    {
        "name": "minta_update_slot",
        "description": "手动更新某个槽位的内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "label": {"type": "string", "description": "槽位标签"},
                "content": {"type": "string", "description": "新内容"},
            },
            "required": ["label", "content"],
        },
    },
    {
        "name": "minta_expert_infer",
        "description": "Run expert inference on a user message (symptom/question) for a specific domain (e.g. ankle_injury). Returns diagnosis and reasoning from the domain expert.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "message": {"type": "string", "description": "用户的症状描述或问题"},
                "domain": {"type": "string", "description": "专家领域, e.g. ankle_injury, knee_injury, running_analysis"},
            },
            "required": ["message", "domain"],
        },
    },
    {
        "name": "minta_expert_list",
        "description": "列出所有可用的专家及每个专家的规则数和信任等级。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "minta_expert_consult",
        "description": "跨领域会诊 — 先用 primary 专家推理，再用 consult 专家提供第二意见。适用于需要多学科分析的复杂病例。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "message": {"type": "string", "description": "症状描述或问题"},
                "primary_domain": {"type": "string", "description": "主诊专家领域"},
                "consult_domain": {"type": "string", "description": "会诊专家领域"},
            },
            "required": ["message", "primary_domain", "consult_domain"],
        },
    },
    {
        "name": "minta_expert_trust",
        "description": "获取指定专家领域的三项信任指标（Goldman 指标）：可信度、可纠正性、领域覆盖度。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "domain": {"type": "string", "description": "专家领域"},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "minta_expert_feedback",
        "description": "提交 Expert 推理反馈。推理完成后调用此工具记录用户评价。signal 为 'positive'（诊断有帮助）或 'negative'（诊断不对）。反馈数据用于 JEPA 训练和规则置信度调整。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "log_id": {"type": "integer", "description": "推理返回的 feedback_id"},
                "signal": {"type": "string", "description": "positive 或 negative"},
            },
            "required": ["log_id", "signal"],
        },
    },
    {
        "name": "minta_chat",
        "description": "主对话入口 — 向 Minta 发送消息，自动检测是否与任何专家领域相关并路由。如果 API 建议专家则返回建议，如果已确认专家则展示结果。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "message": {"type": "string", "description": "用户消息"},
            },
            "required": ["message"],
        },
    },
    # ── Autopilot tools ──
    {
        "name": "minta_autopilot_preflight",
        "description": "[AUTOPILOT] Call this BEFORE answering any user request. Automatically reads relevant memory context (preferences, project context, counterexamples, skills) and returns them so you can use them in your response. Never skip this.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_message": {"type": "string", "description": "The user's latest message"},
                "project_id": {"type": "string", "description": "Current project/repo ID if known"},
            },
            "required": ["user_message"],
        },
    },
    {
        "name": "minta_autopilot_postflight",
        "description": "[AUTOPILOT] Call this BEFORE finalizing your response. Automatically detects if new memory should be saved, counterexamples captured, or memory updated. Never manually decide when to write — use this instead.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_message": {"type": "string", "description": "The user's latest message"},
                "assistant_response": {"type": "string", "description": "Your draft response to the user"},
                "project_id": {"type": "string", "description": "Current project/repo ID if known"},
            },
            "required": ["user_message", "assistant_response"],
        },
    },
]


# ── Autopilot handler (lightweight inline implementation) ──


def autopilot_handler(tool_name, arguments):
    # type: (str, dict) -> str
    """Handle autopilot preflight/postflight.
    Uses policy engine directly (no HTTP). For inbox writes, calls API directly."""
    try:
        # Ensure server directory is in path for imports
        _mcp_ensure_path()
        from services.autopilot.schemas import PolicyInput
        from services.autopilot.memory_policy import decide_policy

        msg = arguments.get("user_message", "")
        project = arguments.get("project_id")
        agent = "mcp"

        api_key = os.environ.get("MINTA_API_KEY", "") or API_KEY
        api_url = os.environ.get("MINTA_API_URL", MINTA_API)

        if tool_name == "minta_autopilot_preflight":
            inp = PolicyInput(user_id="mcp", phase="pre_turn",
                              user_message=msg, project_id=project, agent=agent)
            policy = decide_policy(inp)
            result = {
                "read_triggered": policy.read.should_run,
                "reason": policy.read.reason,
                "memory_context": {},
                "log_id": "apl_mcp_%s" % str(hash(msg))[:8],
                "degraded": False,
            }
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "minta_autopilot_postflight":
            assistant_resp = arguments.get("assistant_response", "")
            inp = PolicyInput(user_id="mcp", phase="post_turn",
                              user_message=msg, assistant_response=assistant_resp,
                              project_id=project, agent=agent)
            policy = decide_policy(inp)

            created = {"inbox_items": [], "counter_items": [], "review_items": []}

            # Write to inbox via API if triggered
            if policy.write.should_run and api_key:
                _autopilot_append_inbox(api_url, api_key,
                    "[Autopilot] %s" % policy.write.reason, 0.7)

            if policy.counter_capture.should_run and api_key:
                _autopilot_append_inbox(api_url, api_key,
                    "[Autopilot Counter] %s" % policy.counter_capture.reason, 0.8)

            if policy.update.should_run and api_key:
                _autopilot_append_inbox(api_url, api_key,
                    "[Autopilot Update] %s" % policy.update.reason, 0.6)

            result = {
                "write_triggered": policy.write.should_run,
                "counter_capture_triggered": policy.counter_capture.should_run,
                "update_triggered": policy.update.should_run,
                "created": created,
                "reason": _autopilot_reason(policy),
                "log_id": "apl_mcp_%s" % str(hash(msg))[:8],
                "degraded": False,
            }
            return json.dumps(result, ensure_ascii=False)

        return json.dumps({"error": "Unknown tool: %s" % tool_name})
    except Exception as e:
        return json.dumps({"error": "Autopilot handler error: %s" % str(e)})


def _mcp_ensure_path():
    # type: () -> None
    """Ensure server directory is in sys.path for autopilot imports."""
    import sys
    server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)


def _autopilot_append_inbox(api_url, api_key, text, confidence):
    # type: (str, str, str, float) -> None
    """Quick inbox append via API. Fail silently."""
    try:
        import urllib.parse
        qs = "?text=%s&confidence=%s" % (urllib.parse.quote(text[:500]), confidence)
        data = json.dumps(["autopilot"]).encode("utf-8")
        req = urllib.request.Request(
            "%s/api/inbox/append%s" % (api_url, qs),
            data=data,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _autopilot_reason(policy):
    # type: (Any) -> str
    """Build reason string from policy decisions."""
    parts = []
    if policy.write.should_run:
        parts.append(policy.write.reason)
    if policy.counter_capture.should_run:
        parts.append(policy.counter_capture.reason)
    if policy.update.should_run:
        parts.append(policy.update.reason)
    return "; ".join(parts) if parts else "no action"


# ── MCP Stdio Protocol (JSON-RPC 2.0) ──

_REQ_ID = 0


def _ensure_api_running():
    """stdio 模式下：如果 API 服务没跑，自动拉起（最多等 12 秒）。"""
    api_health = f"{MINTA_API.rstrip('/')}/ping"
    try:
        urllib.request.urlopen(
            urllib.request.Request(api_health), timeout=2
        )
        return  # 已经在跑了
    except Exception:
        pass

    server_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "127.0.0.1", "--port", "8772",
             "--log-level", "error"],
            cwd=server_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return  # 启动失败不阻塞，tool call 会返回可读错误

    for _ in range(24):  # 最多等 12 秒
        time.sleep(0.5)
        try:
            urllib.request.urlopen(
                urllib.request.Request(api_health), timeout=1
            )
            return
        except Exception:
            pass


def _respond(id_val, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id_val, "result": result}) + "\n")
    sys.stdout.flush()

def _respond_error(id_val, code, message):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": id_val, "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()

def main():
    global _REQ_ID
    _ensure_api_running()
    # Force UTF-8 on Windows; default cp936 garbles Chinese from Claude Code
    sys.stdin.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        rid = msg.get("id", _REQ_ID)
        _REQ_ID += 1
        method = msg.get("method", "")
        params = msg.get("params", {})

        if method == "initialize":
            _respond(rid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "minta-mcp", "version": "1.0.0"},
            })
        elif method == "tools/list":
            _respond(rid, {"tools": TOOL_DEFINITIONS})
        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = handle_call(name, arguments)
            _respond(rid, {"content": [{"type": "text", "text": result}]})
        elif method == "notifications/initialized":
            pass  # no response expected
        else:
            _respond_error(rid, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
