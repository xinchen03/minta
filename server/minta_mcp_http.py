"""
Minta MCP HTTP Server — allows remote agents to call the Minta API via HTTP.
Compatible with the standard MCP Streamable HTTP transport protocol.
"""
import json
import sys
import os
from typing import Any, Dict

# Reuse core logic
sys.path.insert(0, os.path.dirname(__file__))
from minta_mcp import TOOL_DEFINITIONS, handle_call


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
        body = await request.json()
        method = body.get("method", "")
        params = body.get("params", {})
        msg_id = body.get("id", 1)

        if method == "initialize":
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
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOL_DEFINITIONS},
            }
        elif method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = handle_call(name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }
        elif method == "notifications/initialized":
            return JSONResponse(content={"jsonrpc": "2.0"}, status_code=202)
        else:
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
