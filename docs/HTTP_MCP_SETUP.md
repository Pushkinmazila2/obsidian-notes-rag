# HTTP/SSE MCP Server Setup

This guide explains how to run Obsidian RAG as an HTTP/SSE MCP server that connects to remote services.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Cloud/Remote Services                    │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   CouchDB    │    │  Remote LLM  │    │  OpenAI API  │ │
│  │  (External)  │    │   (Ollama/   │    │              │ │
│  │              │    │   LM Studio) │    │              │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         ▲                    ▲                    ▲         │
│         │                    │                    │         │
│         │  HTTP + Auth       │  HTTP + Bearer    │  API Key│
│         └────────────────────┴───────────────────┘         │
│                              │                              │
└──────────────────────────────┼──────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Obsidian RAG MCP  │
                    │   HTTP/SSE Server  │
                    │   (Docker/Cloud)   │
                    └──────────┬──────────┘
                               │
                    HTTP/SSE + Bearer Token
                               │
                    ┌──────────▼──────────┐
                    │   MCP Clients       │
                    │ (Claude, Cursor,    │
                    │  Windsurf, etc.)    │
                    └─────────────────────┘
```

## Key Features

- **Lightweight**: Only the MCP server runs in Docker, no bundled LLM or database
- **Remote Services**: Connects to external CouchDB and LLM endpoints
- **Bearer Token Auth**: Secure HTTP/SSE communication
- **Cloud Ready**: Deploy anywhere (AWS, GCP, Azure, Fly.io, Railway, etc.)
- **Stateless**: Vector index stored in persistent volume

## Quick Start

### 1. Create configuration file

Create `.env` file:

```bash
# CouchDB (external)
OBSIDIAN_RAG_COUCH_URL=https://your-couchdb.example.com
OBSIDIAN_RAG_COUCH_DB=obsidian
OBSIDIAN_RAG_COUCH_USER=admin
OBSIDIAN_RAG_COUCH_PASSWORD=your-password

# Embedding Provider
OBSIDIAN_RAG_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Or use remote Ollama
# OBSIDIAN_RAG_PROVIDER=ollama
# OBSIDIAN_RAG_OLLAMA_URL=https://your-ollama.example.com
# OBSIDIAN_RAG_OLLAMA_API_KEY=your-bearer-token
# OBSIDIAN_RAG_OLLAMA_MODEL=nomic-embed-text

# Or use remote LM Studio
# OBSIDIAN_RAG_PROVIDER=lmstudio
# OBSIDIAN_RAG_LMSTUDIO_URL=https://your-lmstudio.example.com
# OBSIDIAN_RAG_LMSTUDIO_API_KEY=your-bearer-token
# OBSIDIAN_RAG_LMSTUDIO_MODEL=text-embedding-nomic-embed-text-v1.5

# MCP Server Authentication
MCP_SERVER_TOKEN=your-secure-random-token

# Optional: Logging
LOG_LEVEL=info
```

### 2. Start the server

```bash
# Using docker-compose
docker-compose -f docker-compose.simple.yml up -d

# Or using docker directly
docker build -t obsidian-rag .
docker run -d \
  --name obsidian-rag \
  -p 3000:3000 \
  --env-file .env \
  -v rag-data:/data \
  obsidian-rag
```

### 3. Verify server is running

```bash
# Check health
curl http://localhost:3000/health

# List available tools (with authentication)
curl -H "Authorization: Bearer your-secure-random-token" \
  http://localhost:3000/tools
```

### 4. Initial indexing

```bash
# Index all notes from CouchDB
curl -X POST \
  -H "Authorization: Bearer your-secure-random-token" \
  -H "Content-Type: application/json" \
  -d '{"tool": "couch_reindex", "parameters": {"clear": true}}' \
  http://localhost:3000/call

# Or use CLI
docker exec obsidian-rag-mcp python -m obsidian_rag.cli index
```

## Connecting Remote LLM Services

### Option 1: OpenAI (Recommended for Cloud)

```bash
OBSIDIAN_RAG_PROVIDER=openai
OPENAI_API_KEY=sk-...
OBSIDIAN_RAG_MODEL=text-embedding-3-small
```

**Pros:**
- No infrastructure to manage
- Fast and reliable
- Good quality embeddings

**Cons:**
- Costs per API call
- Requires internet connection
- Data sent to OpenAI

### Option 2: Remote Ollama with Bearer Token

If you have Ollama running on another server:

```bash
OBSIDIAN_RAG_PROVIDER=ollama
OBSIDIAN_RAG_OLLAMA_URL=https://ollama.example.com
OBSIDIAN_RAG_OLLAMA_API_KEY=your-bearer-token
OBSIDIAN_RAG_OLLAMA_MODEL=nomic-embed-text
```

**Setting up Ollama with Bearer Token:**

1. Run Ollama behind a reverse proxy (Caddy/Nginx)
2. Add authentication middleware

Example Caddy config:

```caddyfile
ollama.example.com {
    @authorized {
        header Authorization "Bearer your-bearer-token"
    }
    
    handle @authorized {
        reverse_proxy localhost:11434
    }
    
    handle {
        respond "Unauthorized" 401
    }
}
```

**Pros:**
- Free (after infrastructure costs)
- Private - data stays on your servers
- Good quality with nomic-embed-text

**Cons:**
- Need to manage Ollama server
- Requires GPU for good performance

### Option 3: Remote LM Studio with Bearer Token

Similar to Ollama, but using LM Studio:

```bash
OBSIDIAN_RAG_PROVIDER=lmstudio
OBSIDIAN_RAG_LMSTUDIO_URL=https://lmstudio.example.com
OBSIDIAN_RAG_LMSTUDIO_API_KEY=your-bearer-token
OBSIDIAN_RAG_LMSTUDIO_MODEL=text-embedding-nomic-embed-text-v1.5
```

### Option 4: LocalAI (Self-hosted OpenAI-compatible API)

LocalAI provides an OpenAI-compatible API:

```bash
OBSIDIAN_RAG_PROVIDER=openai  # Use OpenAI provider
OPENAI_API_KEY=your-localai-token
OPENAI_BASE_URL=https://localai.example.com/v1
OBSIDIAN_RAG_MODEL=text-embedding-ada-002  # Or your model name
```

## Connecting MCP Clients

### Claude Desktop (HTTP/SSE)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obsidian-notes-rag": {
      "url": "https://your-mcp-server.example.com",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer your-secure-random-token"
      }
    }
  }
}
```

### Cursor / Windsurf (HTTP API)

These editors can call HTTP APIs directly. Create a custom tool configuration:

```json
{
  "tools": [
    {
      "name": "search_obsidian",
      "description": "Search Obsidian notes",
      "endpoint": "https://your-mcp-server.example.com/call",
      "method": "POST",
      "headers": {
        "Authorization": "Bearer your-secure-random-token",
        "Content-Type": "application/json"
      },
      "body": {
        "tool": "search_notes",
        "parameters": {
          "query": "{{query}}",
          "limit": 5
        }
      }
    }
  ]
}
```

## Cloud Deployment Examples

### Deploy to Fly.io

1. Install Fly CLI: https://fly.io/docs/hands-on/install-flyctl/

2. Create `fly.toml`:

```toml
app = "obsidian-rag-mcp"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  OBSIDIAN_RAG_SOURCE = "couchdb"
  OBSIDIAN_RAG_PROVIDER = "openai"
  MCP_SERVER_PORT = "3000"
  LOG_LEVEL = "info"

[http_service]
  internal_port = 3000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/health"

[mounts]
  source = "rag_data"
  destination = "/data"
```

3. Set secrets:

```bash
fly secrets set \
  OPENAI_API_KEY=sk-... \
  OBSIDIAN_RAG_COUCH_URL=https://... \
  OBSIDIAN_RAG_COUCH_USER=admin \
  OBSIDIAN_RAG_COUCH_PASSWORD=... \
  MCP_SERVER_TOKEN=your-secure-token
```

4. Deploy:

```bash
fly deploy
```

### Deploy to Railway

1. Connect GitHub repo to Railway
2. Add environment variables in Railway dashboard
3. Railway auto-detects Dockerfile and deploys
4. Get public URL from Railway dashboard

### Deploy to AWS ECS

1. Push image to ECR:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ECR_URL
docker build -t obsidian-rag .
docker tag obsidian-rag:latest YOUR_ECR_URL/obsidian-rag:latest
docker push YOUR_ECR_URL/obsidian-rag:latest
```

2. Create ECS task definition with environment variables
3. Create ECS service with ALB
4. Configure ALB health checks to `/health`

## Security Best Practices

### 1. Use Strong Bearer Tokens

```bash
# Generate secure random token
openssl rand -hex 32
```

### 2. Use HTTPS in Production

Always use HTTPS for:
- MCP server endpoint
- CouchDB connection
- LLM API endpoints

### 3. Restrict Network Access

- Use VPC/private networks when possible
- Whitelist IP addresses
- Use firewall rules

### 4. Rotate Credentials Regularly

- Bearer tokens
- CouchDB passwords
- API keys

### 5. Monitor and Log

```bash
# View logs
docker logs -f obsidian-rag-mcp

# Set log level
LOG_LEVEL=debug
```

## Troubleshooting

### Server won't start

```bash
# Check logs
docker logs obsidian-rag-mcp

# Verify environment variables
docker exec obsidian-rag-mcp env | grep OBSIDIAN
```

### Can't connect to CouchDB

```bash
# Test connection from container
docker exec obsidian-rag-mcp curl -v $OBSIDIAN_RAG_COUCH_URL

# Check credentials
docker exec obsidian-rag-mcp python -c "
from src.obsidian_rag.couch_source import CouchDBClient
from src.obsidian_rag.config import load_config
config = load_config()
client = CouchDBClient(
    couchdb_url=config.couchdb_url,
    db=config.couchdb_db,
    username=config.couchdb_username,
    password=config.couchdb_password
)
print(client.get_doc('_design/views'))
"
```

### Can't connect to LLM

```bash
# Test Ollama connection
curl -H "Authorization: Bearer your-token" \
  https://your-ollama.example.com/api/tags

# Test from container
docker exec obsidian-rag-mcp python -c "
from src.obsidian_rag.indexer import create_embedder
from src.obsidian_rag.config import load_config
config = load_config()
embedder = create_embedder(
    provider=config.provider,
    base_url=config.ollama_url,
    api_key=config.get_ollama_api_key()
)
print(embedder.embed('test')[:5])
"
```

### Authentication errors

```bash
# Test with correct token
curl -H "Authorization: Bearer your-token" \
  http://localhost:3000/tools

# Should return 401 without token
curl http://localhost:3000/tools
```

## Performance Tuning

### For large vaults (>1000 notes)

1. Increase container resources:

```yaml
# docker-compose.simple.yml
services:
  obsidian-rag:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

2. Use batch indexing:

```bash
# Index in batches by path
curl -X POST -H "Authorization: Bearer token" \
  -d '{"tool": "couch_reindex", "parameters": {"path_filter": "Daily Notes/"}}' \
  http://localhost:3000/call
```

3. Adjust chunk size:

```bash
OBSIDIAN_RAG_CHUNK_SIZE=1000
```

## Monitoring

### Health Check Endpoint

```bash
curl http://localhost:3000/health
```

Response:
```json
{
  "status": "healthy",
  "documents": 1234
}
```

### Metrics (Future)

Planned metrics endpoint:
- Request count
- Response times
- Error rates
- Index size
- Last sync time

## License

MIT