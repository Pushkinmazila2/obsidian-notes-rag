# Docker Setup Guide

This guide explains how to run Obsidian RAG as a Docker container with CouchDB support.

## Quick Start

### 1. Create environment configuration

Create a `.env` file in the project root with your configuration:

```bash
# CouchDB Configuration
COUCHDB_USER=admin
COUCHDB_PASSWORD=your-secure-password-here

# Obsidian RAG Configuration
OBSIDIAN_RAG_SOURCE=couchdb
OBSIDIAN_RAG_COUCH_DB=obsidian

# Embedding Provider
OBSIDIAN_RAG_PROVIDER=ollama
OBSIDIAN_RAG_OLLAMA_MODEL=nomic-embed-text

# Optional: OpenAI (if not using Ollama)
# OPENAI_API_KEY=sk-...
# OBSIDIAN_RAG_PROVIDER=openai
# OBSIDIAN_RAG_MODEL=text-embedding-3-small
```

### 2. Start the services

```bash
# Start all services (CouchDB, Ollama, RAG server, Watcher)
docker-compose up -d

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f obsidian-rag
docker-compose logs -f obsidian-watcher
```

### 3. Pull Ollama model (first time only)

```bash
# Enter Ollama container
docker exec -it obsidian-ollama ollama pull nomic-embed-text

# Verify model is available
docker exec -it obsidian-ollama ollama list
```

### 4. Initial indexing

```bash
# Run initial index
docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli index

# Check index stats
docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli stats
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                          │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │   CouchDB    │    │    Ollama    │    │  RAG Server  │ │
│  │   :5984      │◄───┤   :11434     │◄───┤   (MCP)      │ │
│  │              │    │              │    │              │ │
│  └──────────────┘    └──────────────┘    └──────────────┘ │
│         ▲                                        ▲          │
│         │                                        │          │
│         │            ┌──────────────┐            │          │
│         └────────────┤   Watcher    │────────────┘          │
│                      │ (Auto-index) │                       │
│                      └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
         │                                        │
         │                                        │
    Obsidian App                            MCP Clients
  (Self-hosted LiveSync)                  (Claude, etc.)
```

## Services

### CouchDB
- **Port**: 5984
- **Purpose**: Stores Obsidian notes via Self-hosted LiveSync plugin
- **Data**: Persisted in `couchdb-data` volume
- **Web UI**: http://localhost:5984/_utils

### Ollama
- **Port**: 11434
- **Purpose**: Generates embeddings locally (no API key needed)
- **Data**: Models stored in `ollama-data` volume
- **Alternative**: Can use OpenAI or LM Studio instead

### RAG Server (MCP)
- **Purpose**: Provides semantic search via MCP protocol
- **Data**: Vector index stored in `rag-data` volume
- **Protocol**: stdio (for MCP clients)

### Watcher
- **Purpose**: Monitors CouchDB changes and auto-indexes new/modified notes
- **Mode**: Runs continuously in background
- **Data**: Shares `rag-data` volume with RAG server

## Environment Variables

### Required

| Variable | Description | Default |
|----------|-------------|----------|
| `COUCHDB_USER` | CouchDB admin username | `admin` |
| `COUCHDB_PASSWORD` | CouchDB admin password | `password` |
| `OBSIDIAN_RAG_SOURCE` | Data source (`vault` or `couchdb`) | `couchdb` |
| `OBSIDIAN_RAG_PROVIDER` | Embedding provider (`openai`, `ollama`, `lmstudio`) | `ollama` |

### CouchDB Settings

| Variable | Description | Default |
|----------|-------------|----------|
| `OBSIDIAN_RAG_COUCH_DB` | Database name | `obsidian` |
| `OBSIDIAN_RAG_COUCH_USER` | CouchDB username | (from `COUCHDB_USER`) |
| `OBSIDIAN_RAG_COUCH_PASSWORD` | CouchDB password | (from `COUCHDB_PASSWORD`) |

### OpenAI Settings (if using OpenAI)

| Variable | Description | Default |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OBSIDIAN_RAG_MODEL` | Model name | `text-embedding-3-small` |

### Ollama Settings (if using Ollama)

| Variable | Description | Default |
|----------|-------------|----------|
| `OBSIDIAN_RAG_OLLAMA_MODEL` | Model name | `nomic-embed-text` |

### Advanced Settings

| Variable | Description | Default |
|----------|-------------|----------|
| `OBSIDIAN_RAG_DATA` | Data directory path | `/data` |
| `OBSIDIAN_RAG_CHUNK_SIZE` | Chunk size in tokens | `1500` |
| `OBSIDIAN_RAG_SIMILARITY_THRESHOLD` | Minimum similarity (0.0-1.0) | `0.10` |

## Cloud Deployment

### Deploy to any cloud provider

The Docker setup works on any platform that supports Docker:

- **AWS**: ECS, EC2, Lightsail
- **Google Cloud**: Cloud Run, Compute Engine
- **Azure**: Container Instances, App Service
- **DigitalOcean**: App Platform, Droplets
- **Fly.io**: `fly launch`
- **Railway**: Connect GitHub repo

### Example: Deploy to Fly.io

1. Install Fly CLI: https://fly.io/docs/hands-on/install-flyctl/

2. Create `fly.toml`:

```toml
app = "obsidian-rag"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  OBSIDIAN_RAG_SOURCE = "couchdb"
  OBSIDIAN_RAG_PROVIDER = "openai"
  OBSIDIAN_RAG_COUCH_URL = "https://your-couchdb.example.com"
  OBSIDIAN_RAG_COUCH_DB = "obsidian"

[mounts]
  source = "rag_data"
  destination = "/data"
```

3. Set secrets:

```bash
fly secrets set OPENAI_API_KEY=sk-...
fly secrets set OBSIDIAN_RAG_COUCH_USER=admin
fly secrets set OBSIDIAN_RAG_COUCH_PASSWORD=...
```

4. Deploy:

```bash
fly deploy
```

### Example: Deploy to Railway

1. Connect your GitHub repo to Railway
2. Add environment variables in Railway dashboard
3. Railway auto-detects Dockerfile and deploys

## Connecting Obsidian

### Self-hosted LiveSync Plugin

1. Install plugin: https://github.com/vrtmrz/obsidian-livesync
2. Configure CouchDB connection:
   - URL: `http://your-server:5984`
   - Database: `obsidian`
   - Username: (from `COUCHDB_USER`)
   - Password: (from `COUCHDB_PASSWORD`)
3. Enable sync

## Connecting MCP Clients

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obsidian-notes-rag": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "obsidian-rag-mcp",
        "python",
        "-m",
        "obsidian_rag.server"
      ]
    }
  }
}
```

### Remote MCP Server (Future)

For cloud deployments, you'll need to expose the MCP server over HTTP/WebSocket. This is planned for a future release.

## Maintenance

### Backup data

```bash
# Backup CouchDB
docker exec obsidian-couchdb couchdb-backup backup -H http://admin:password@localhost:5984 -d obsidian -f /tmp/backup.json
docker cp obsidian-couchdb:/tmp/backup.json ./backup-$(date +%Y%m%d).json

# Backup vector index
docker run --rm -v obsidian-notes-rag_rag-data:/data -v $(pwd):/backup alpine tar czf /backup/rag-data-$(date +%Y%m%d).tar.gz -C /data .
```

### Update services

```bash
# Pull latest images
docker-compose pull

# Rebuild and restart
docker-compose up -d --build
```

### View resource usage

```bash
docker stats
```

### Troubleshooting

```bash
# Check service health
docker-compose ps

# View logs
docker-compose logs -f obsidian-rag

# Enter container shell
docker exec -it obsidian-rag-mcp bash

# Test CouchDB connection
docker exec -it obsidian-rag-mcp python -c "from src.obsidian_rag.couch_source import CouchDBClient; print(CouchDBClient().get_doc('_design/views'))"

# Rebuild index
docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli index --clear
```

## Performance Tuning

### For large vaults (>1000 notes)

1. Increase CouchDB memory:

```yaml
# docker-compose.yml
couchdb:
  environment:
    - COUCHDB_ERLANG_COOKIE=secret
  command: ["-kernel", "inet_dist_listen_min", "9100", "-kernel", "inet_dist_listen_max", "9200"]
```

2. Use batch indexing:

```bash
docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli index --path-filter "Daily Notes/"
```

3. Adjust chunk size:

```bash
# In .env
OBSIDIAN_RAG_CHUNK_SIZE=1000
```

## Security

### Production checklist

- [ ] Change default CouchDB password
- [ ] Use HTTPS for CouchDB (reverse proxy)
- [ ] Restrict CouchDB port (5984) to internal network
- [ ] Use secrets management (not .env files)
- [ ] Enable CouchDB authentication
- [ ] Regular backups
- [ ] Monitor logs for errors

### Reverse proxy example (Caddy)

```caddyfile
couchdb.example.com {
    reverse_proxy obsidian-couchdb:5984
}

rag.example.com {
    reverse_proxy obsidian-rag-mcp:8080
}
```

## License

MIT