"""
Minta MCP HTTP Server — 让远程 agent 通过 HTTP 调用 Minta API。
兼容标准 MCP Streamable HTTP 传输协议。
"""
import json
import sys
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# 复用核心逻辑
sys.path.insert(0, os.path.dirname(__file__))
from minta_mcp import TOOL_DEFINITIONS, handle_call

# ── Logging ──
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
mcp_log = LOG_DIR / f"mcp-http-{datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    filename=str(mcp_log),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("minta-mcp-http")


def create_mcp_app():
    """Create a FastAPI app that serves MCP tools over HTTP."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Minta MCP HTTP Server", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"ok": True, "server": "minta-mcp-http"}

    @app.get("/mcp")
    async def mcp_sse(request: Request):
        """SSE transport — for agents that support SSE (Cline, etc.)."""
        from sse_starlette.sse import EventSourceResponse
        import asyncio

        async def event_generator():
            # Send tools list on connect
            tools_msg = {
                "jsonrpc": "2.0",
                "id": 0,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "minta-mcp", "version": "1.0.0"},
                },
            }
            yield {"event": "endpoint", "data": json.dumps({"endpoint": "/mcp"})}
            yield {"event": "message", "data": json.dumps({"type": "initialized"})}

            # Wait for messages via POST
            while True:
                await asyncio.sleep(30)

        return EventSourceResponse(event_generator())

    @app.post("/mcp")
    async def mcp_http(request: Request):
        """Streamable HTTP transport — single POST endpoint."""
        import traceback as _tb
        raw = await request.body()
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception as _e:
            logger.error(f"Parse error: {_e}")
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": f"Parse error: {_e}"}},
                status_code=400,
            )
        method = body.get("method", "")
        params = body.get("params", {})
        msg_id = body.get("id", 1)

        if method == "initialize":
            logger.info("Client initialized")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "minta-mcp", "version": "1.0.0"},
                },
            }
        elif method == "tools/list":
            logger.info(f"tools/list requested ({len(TOOL_DEFINITIONS)} tools)")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOL_DEFINITIONS},
            }
        elif method == "tools/call":
            name = params.get("name", "")
            logger.info(f"tools/call: {name}")
            try:
                result = handle_call(name, params.get("arguments", {}))
                ok = '"error"' not in result[:60]
                logger.info(f"tools/call {name} -> {'OK' if ok else 'ERROR'}")
            except Exception as e:
                logger.error(f"tools/call {name} crashed: {e}\n{_tb.format_exc()}")
                result = json.dumps({"error": f"Unhandled: {e}"})
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }
        elif method == "notifications/initialized":
            return JSONResponse(content={"jsonrpc": "2.0"}, status_code=202)
        else:
            logger.warning(f"Unknown method: {method}")
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                },
                status_code=404,
            )

    return app


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("MCP_HTTP_PORT", 18721))
    app = create_mcp_app()
    print(f"Minta MCP HTTP Server starting on :{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
