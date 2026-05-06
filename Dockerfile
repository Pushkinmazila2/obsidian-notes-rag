FROM python:3.11-slim as builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY src ./src

RUN uv pip install --system --no-cache .

# ---- runtime ----
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 obsidian

COPY --from=builder /usr/local /usr/local

WORKDIR /app
COPY --chown=obsidian:obsidian src ./src

USER obsidian

ENV MCP_SERVER_HOST=0.0.0.0 \
    MCP_SERVER_PORT=6000 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "obsidian_rag.http_server"]