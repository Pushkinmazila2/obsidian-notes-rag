# Multi-stage build for obsidian-notes-rag MCP server
FROM python:3.11-slim as builder

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src ./src

# Install dependencies
RUN uv pip install --system --no-cache .

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 obsidian && \
    mkdir -p /data /config && \
    chown -R obsidian:obsidian /data /config

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application
COPY --chown=obsidian:obsidian src /app/src

WORKDIR /app

# Switch to non-root user
USER obsidian

# Environment variables with defaults
ENV OBSIDIAN_RAG_SOURCE=couchdb \
    OBSIDIAN_RAG_DATA=/data \
    OBSIDIAN_RAG_PROVIDER=openai \
    OBSIDIAN_RAG_COUCH_URL=http://couchdb:5984 \
    OBSIDIAN_RAG_COUCH_DB=obsidian \
    MCP_SERVER_HOST=0.0.0.0 \
    MCP_SERVER_PORT=3000 \
    LOG_LEVEL=info \
    PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Default command: run HTTP/SSE MCP server
CMD ["python", "-m", "obsidian_rag.http_server"]

# Expose MCP HTTP/SSE port
EXPOSE 3000

# Volumes
VOLUME ["/data", "/config"]