"""HTTP/SSE server for MCP protocol with Bearer token authentication."""

from __future__ import annotations
import httpx

import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .config import load_config
from .server import (
    search_notes,
    get_similar,
    get_note_context,
    get_stats,
    reindex,
    couch_reindex,
    couch_index_note,
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Obsidian RAG MCP Server",
    description="Semantic search over Obsidian notes via MCP protocol",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bearer token from environment
BEARER_TOKEN = os.environ.get("MCP_SERVER_TOKEN")


def verify_token(authorization: Optional[str] = Header(None)) -> bool:
    """Verify Bearer token if configured."""
    if not BEARER_TOKEN:
        return True  # No token required
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization[7:]  # Remove "Bearer " prefix
    if token != BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return True


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        stats = get_stats()
        return {
            "status": "healthy",
            "documents": stats.get("count", 0),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Dashboard with system status and instructions."""
    config = load_config()
    
    # 1. Сбор статистики RAG
    try:
        stats = get_stats()
        rag_status = f"🟢 Connected ({stats.get('count', 0)} notes)"
    except Exception:
        rag_status = "🔴 Error (Check index path)"

    # 2. Сбор статистики CouchDB
    if config.is_couchdb_mode():
        couch_status = "🟢 Enabled" # Можно расширить проверкой доступности БД
    else:
        couch_status = "⚪ Disabled (Local mode)"

    # 3. Проверка Local LLM (например, Ollama или LM Studio)
    llm_url = os.environ.get("LLM_API_BASE", "http://localhost:11434") # По умолчанию Ollama
    try:
        # Быстрая проверка доступности порта
        async with httpx.AsyncClient() as client:
            await client.get(llm_url, timeout=1.0)
        llm_status = f"🟢 Online ({llm_url})"
    except Exception:
        llm_status = f"🔴 Offline or Unreachable ({llm_url})"

    token_status = "Active" if BEARER_TOKEN else "Disabled"
    auth_header = f"Bearer {BEARER_TOKEN}" if BEARER_TOKEN else "None"
    
    return f"""
    <html>
        <head>
            <title>Obsidian RAG Control Center</title>
            <style>
                body {{ font-family: -apple-system, sans-serif; line-height: 1.6; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #24292e; background: #f0f2f5; }}
                .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #e1e4e8; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px; }}
                .stat-card {{ background: #fff; padding: 15px; border-radius: 10px; border-top: 4px solid #0366d6; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
                .stat-card h3 {{ margin: 0; font-size: 14px; color: #586069; text-transform: uppercase; }}
                .stat-card p {{ margin: 10px 0 0; font-weight: bold; font-size: 14px; }}
                code {{ background: #f1f8ff; padding: 2px 5px; border-radius: 4px; font-family: monospace; color: #0366d6; }}
                pre {{ background: #f6f8fa; padding: 15px; overflow-x: auto; border-radius: 6px; border: 1px solid #d1d5da; font-size: 12px; }}
                .btn {{ background: #28a745; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-weight: bold; }}
                .btn:hover {{ background: #218838; }}
                h2 {{ color: #0366d6; font-size: 20px; }}
            </style>
        </head>
        <body>
            <h1>🚀 Obsidian RAG Control Center</h1>

            <div class="grid">
                <div class="stat-card">
                    <h3>RAG Local Index</h3>
                    <p>{rag_status}</p>
                </div>
                <div class="stat-card" style="border-top-color: #6f42c1;">
                    <h3>CouchDB Sync</h3>
                    <p>{couch_status}</p>
                </div>
                <div class="stat-card" style="border-top-color: #f66a0a;">
                    <h3>Local LLM</h3>
                    <p>{llm_status}</p>
                </div>
            </div>

            <div class="card" style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>Auth Token:</strong> <code>{token_status}</code>
                </div>
                <button id="reindexBtn" class="btn" onclick="runReindex()">🔄 Full Reindex</button>
            </div>

            <div class="card">
                <h2>📖 Connection Instructions</h2>
                <p><strong>Claude Desktop:</strong> Add to <code>claude_desktop_config.json</code>:</p>
                <pre>{{ "mcpServers": {{ "obsidian": {{ "command": "curl", "args": ["-H", "Authorization: {auth_header}", "http://localhost:3000/sse"] }} }} }}</pre>
                
                <p><strong>LM Studio:</strong> Connect via <code>http://localhost:3000/sse</code> with header <code>Authorization: {auth_header}</code></p>
            </div>

            <div id="log" style="font-family: monospace; font-size: 12px; color: #666; padding-left: 10px;"></div>

            <script>
                async function runReindex() {{
                    const btn = document.getElementById('reindexBtn');
                    const log = document.getElementById('log');
                    btn.disabled = true;
                    btn.innerText = '⌛ Processing...';
                    try {{
                        const res = await fetch('/call', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json', 'Authorization': '{auth_header}' }},
                            body: JSON.stringify({{ tool: 'reindex', parameters: {{ clear: false }} }})
                        }});
                        const data = await res.json();
                        log.innerText = 'Status: ' + JSON.stringify(data.result);
                    }} catch (e) {{
                        log.innerText = 'Error: ' + e.message;
                    }} finally {{
                        btn.disabled = false;
                        btn.innerText = '🔄 Full Reindex';
                    }}
                }}
            </script>
        </body>
    </html>
    """




@app.get("/tools")
async def list_tools(authorization: Optional[str] = Header(None)):
    """List available MCP tools."""
    verify_token(authorization)
    
    config = load_config()
    
    tools = [
        {
            "name": "search_notes",
            "description": "Search notes using semantic similarity",
            "parameters": {
                "query": {"type": "string", "required": True, "description": "Search query text"},
                "limit": {"type": "integer", "required": False, "description": "Maximum number of results"},
                "note_type": {"type": "string", "required": False, "description": "Filter by note type (daily/note)"},
            },
        },
        {
            "name": "get_similar",
            "description": "Find notes similar to a given note",
            "parameters": {
                "note_path": {"type": "string", "required": True, "description": "Path to the note"},
                "limit": {"type": "integer", "required": False, "description": "Number of similar notes"},
            },
        },
        {
            "name": "get_note_context",
            "description": "Get a note with related context",
            "parameters": {
                "note_path": {"type": "string", "required": True, "description": "Path to the note"},
                "limit": {"type": "integer", "required": False, "description": "Number of similar notes"},
            },
        },
        {
            "name": "get_stats",
            "description": "Get index statistics",
            "parameters": {},
        },
        {
            "name": "reindex",
            "description": "Re-index the vault",
            "parameters": {
                "clear": {"type": "boolean", "required": False, "description": "Clear existing index"},
                "path_filter": {"type": "string", "required": False, "description": "Path prefix filter"},
            },
        },
    ]
    
    # Add CouchDB-specific tools if in CouchDB mode
    if config.is_couchdb_mode():
        tools.extend([
            {
                "name": "couch_reindex",
                "description": "Re-index from CouchDB",
                "parameters": {
                    "clear": {"type": "boolean", "required": False, "description": "Clear existing index"},
                    "path_filter": {"type": "string", "required": False, "description": "Path prefix filter"},
                },
            },
            {
                "name": "couch_index_note",
                "description": "Re-index a single note from CouchDB",
                "parameters": {
                    "note_path": {"type": "string", "required": True, "description": "Path to the note"},
                },
            },
        ])
    
    return {"tools": tools}


@app.post("/call")
async def call_tool(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Call an MCP tool."""
    verify_token(authorization)
    
    try:
        body = await request.json()
        tool_name = body.get("tool")
        params = body.get("parameters", {})
        
        if not tool_name:
            raise HTTPException(status_code=400, detail="Tool name required")
        
        # Route to appropriate function
        if tool_name == "search_notes":
            result = search_notes(**params)
        elif tool_name == "get_similar":
            result = get_similar(**params)
        elif tool_name == "get_note_context":
            result = get_note_context(**params)
        elif tool_name == "get_stats":
            result = get_stats()
        elif tool_name == "reindex":
            result = reindex(**params)
        elif tool_name == "couch_reindex":
            result = couch_reindex(**params)
        elif tool_name == "couch_index_note":
            result = couch_index_note(**params)
        else:
            raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
        
        return {"result": result}
    
    except Exception as e:
        logger.error(f"Error calling tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sse")
async def sse_endpoint(
    authorization: Optional[str] = Header(None)
):
    """Server-Sent Events endpoint for streaming MCP responses."""
    verify_token(authorization)
    
    async def event_generator():
        """Generate SSE events."""
        # Send initial connection event
        yield f"data: {json.dumps({'type': 'connected', 'message': 'MCP server connected'})}\n\n"
        
        # Keep connection alive with periodic heartbeats
        import asyncio
        while True:
            await asyncio.sleep(30)
            yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': str(asyncio.get_event_loop().time())})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def run_http_server(
    host: str = "0.0.0.0",
    port: int = 3000,
    log_level: str = "info",
):
    """Run the HTTP/SSE MCP server."""
    logger.info(f"Starting MCP HTTP server on {host}:{port}")
    
    if BEARER_TOKEN:
        logger.info("Bearer token authentication enabled")
    else:
        logger.warning("No bearer token configured - server is open!")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
    )


if __name__ == "__main__":
    # Get configuration from environment
    host = os.environ.get("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_SERVER_PORT", "3000"))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()
    
    run_http_server(host=host, port=port, log_level=log_level)