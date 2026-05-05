"""HTTP/SSE server for MCP protocol with Bearer token authentication."""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
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


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Obsidian RAG MCP Server",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "tools": "/tools",
            "call": "/call",
            "sse": "/sse",
        },
        "authentication": "Bearer token" if BEARER_TOKEN else "None",
    }


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