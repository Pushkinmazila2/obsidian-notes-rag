#!/bin/bash
# Interactive Docker setup script for Obsidian RAG MCP Server

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "═══════════════════════════════════════════════════════════"
echo "  Obsidian RAG MCP Server - Docker Setup"
echo "═══════════════════════════════════════════════════════════"
echo -e "${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ docker-compose is not installed${NC}"
    echo "Please install docker-compose: https://docs.docker.com/compose/install/"
    exit 1
fi
echo -e "${GREEN}✓ docker-compose installed${NC}"

echo ""

# Configuration
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 1: Data Source Configuration${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Select data source:"
echo "  1. CouchDB (Self-hosted LiveSync) - Recommended for cloud"
echo "  2. Local Vault (filesystem) - For local development only"
echo ""
read -p "Choice [1]: " SOURCE_CHOICE
SOURCE_CHOICE=${SOURCE_CHOICE:-1}

if [ "$SOURCE_CHOICE" = "1" ]; then
    SOURCE="couchdb"
    
    echo ""
    echo -e "${YELLOW}CouchDB Configuration:${NC}"
    echo ""
    
    read -p "CouchDB URL [http://localhost:5984]: " COUCH_URL
    COUCH_URL=${COUCH_URL:-http://localhost:5984}
    
    read -p "Database name [obsidian]: " COUCH_DB
    COUCH_DB=${COUCH_DB:-obsidian}
    
    read -p "Username [admin]: " COUCH_USER
    COUCH_USER=${COUCH_USER:-admin}
    
    read -sp "Password: " COUCH_PASSWORD
    echo ""
    
    if [ -z "$COUCH_PASSWORD" ]; then
        echo -e "${RED}❌ Password is required${NC}"
        exit 1
    fi
    
    # Test connection
    echo ""
    echo -e "${YELLOW}Testing CouchDB connection...${NC}"
    if curl -sf -u "$COUCH_USER:$COUCH_PASSWORD" "$COUCH_URL/_up" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ CouchDB connection successful${NC}"
    else
        echo -e "${YELLOW}⚠ Could not connect to CouchDB (server may be down)${NC}"
        read -p "Continue anyway? [y/N]: " CONTINUE
        if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
            exit 1
        fi
    fi
else
    SOURCE="vault"
    echo ""
    echo -e "${YELLOW}⚠ Local vault mode is not recommended for Docker deployment${NC}"
    echo "You'll need to mount your vault directory into the container."
    echo ""
    read -p "Path to Obsidian vault: " VAULT_PATH
    
    if [ ! -d "$VAULT_PATH" ]; then
        echo -e "${RED}❌ Directory not found: $VAULT_PATH${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 2: Embedding Provider Configuration${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Select embedding provider:"
echo "  1. OpenAI (recommended for cloud, requires API key)"
echo "  2. Remote Ollama (self-hosted, requires Bearer token)"
echo "  3. Remote LM Studio (self-hosted, requires Bearer token)"
echo ""
read -p "Choice [1]: " PROVIDER_CHOICE
PROVIDER_CHOICE=${PROVIDER_CHOICE:-1}

if [ "$PROVIDER_CHOICE" = "1" ]; then
    PROVIDER="openai"
    echo ""
    echo -e "${YELLOW}OpenAI Configuration:${NC}"
    echo ""
    
    # Check for existing API key in environment
    if [ -n "$OPENAI_API_KEY" ]; then
        echo -e "${GREEN}✓ Found OPENAI_API_KEY in environment${NC}"
        read -p "Use this key? [Y/n]: " USE_ENV_KEY
        if [ "$USE_ENV_KEY" = "n" ] || [ "$USE_ENV_KEY" = "N" ]; then
            read -sp "Enter OpenAI API key: " OPENAI_KEY
            echo ""
        else
            OPENAI_KEY="$OPENAI_API_KEY"
        fi
    else
        read -sp "Enter OpenAI API key: " OPENAI_KEY
        echo ""
    fi
    
    if [ -z "$OPENAI_KEY" ]; then
        echo -e "${RED}❌ API key is required${NC}"
        exit 1
    fi
    
    read -p "Model [text-embedding-3-small]: " MODEL
    MODEL=${MODEL:-text-embedding-3-small}
    
elif [ "$PROVIDER_CHOICE" = "2" ]; then
    PROVIDER="ollama"
    echo ""
    echo -e "${YELLOW}Remote Ollama Configuration:${NC}"
    echo ""
    
    read -p "Ollama URL [http://localhost:11434]: " OLLAMA_URL
    OLLAMA_URL=${OLLAMA_URL:-http://localhost:11434}
    
    read -p "Model [nomic-embed-text]: " MODEL
    MODEL=${MODEL:-nomic-embed-text}
    
    read -p "Bearer token (leave empty if none): " OLLAMA_TOKEN
    
    # Test connection
    echo ""
    echo -e "${YELLOW}Testing Ollama connection...${NC}"
    if [ -n "$OLLAMA_TOKEN" ]; then
        TEST_RESULT=$(curl -sf -H "Authorization: Bearer $OLLAMA_TOKEN" "$OLLAMA_URL/api/tags" 2>&1)
    else
        TEST_RESULT=$(curl -sf "$OLLAMA_URL/api/tags" 2>&1)
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Ollama connection successful${NC}"
        # Check if model exists
        if echo "$TEST_RESULT" | grep -q "$MODEL"; then
            echo -e "${GREEN}✓ Model $MODEL is available${NC}"
        else
            echo -e "${YELLOW}⚠ Model $MODEL not found on server${NC}"
            echo "Available models:"
            echo "$TEST_RESULT" | grep -o '"name":"[^"]*"' | cut -d'"' -f4
        fi
    else
        echo -e "${YELLOW}⚠ Could not connect to Ollama${NC}"
    fi
    
else
    PROVIDER="lmstudio"
    echo ""
    echo -e "${YELLOW}Remote LM Studio Configuration:${NC}"
    echo ""
    
    read -p "LM Studio URL [http://localhost:1234]: " LMSTUDIO_URL
    LMSTUDIO_URL=${LMSTUDIO_URL:-http://localhost:1234}
    
    read -p "Model [text-embedding-nomic-embed-text-v1.5]: " MODEL
    MODEL=${MODEL:-text-embedding-nomic-embed-text-v1.5}
    
    read -p "Bearer token (leave empty if none): " LMSTUDIO_TOKEN
    
    # Test connection
    echo ""
    echo -e "${YELLOW}Testing LM Studio connection...${NC}"
    if [ -n "$LMSTUDIO_TOKEN" ]; then
        TEST_RESULT=$(curl -sf -H "Authorization: Bearer $LMSTUDIO_TOKEN" "$LMSTUDIO_URL/v1/models" 2>&1)
    else
        TEST_RESULT=$(curl -sf "$LMSTUDIO_URL/v1/models" 2>&1)
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ LM Studio connection successful${NC}"
    else
        echo -e "${YELLOW}⚠ Could not connect to LM Studio${NC}"
    fi
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 3: MCP Server Configuration${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "The MCP server will be accessible via HTTP/SSE with Bearer token authentication."
echo ""

# Generate random token
DEFAULT_TOKEN=$(openssl rand -hex 32 2>/dev/null || cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 64 | head -n 1)

read -p "Bearer token (press Enter to generate random): " MCP_TOKEN
if [ -z "$MCP_TOKEN" ]; then
    MCP_TOKEN="$DEFAULT_TOKEN"
    echo -e "${GREEN}Generated token: $MCP_TOKEN${NC}"
fi

read -p "Server port [3000]: " MCP_PORT
MCP_PORT=${MCP_PORT:-3000}

read -p "Log level (debug/info/warning/error) [info]: " LOG_LEVEL
LOG_LEVEL=${LOG_LEVEL:-info}

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 4: Review Configuration${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Data Source: $SOURCE"
if [ "$SOURCE" = "couchdb" ]; then
    echo "  CouchDB URL: $COUCH_URL"
    echo "  Database: $COUCH_DB"
    echo "  Username: $COUCH_USER"
else
    echo "  Vault Path: $VAULT_PATH"
fi
echo ""
echo "Embedding Provider: $PROVIDER"
if [ "$PROVIDER" = "openai" ]; then
    echo "  Model: $MODEL"
    echo "  API Key: ${OPENAI_KEY:0:10}..."
elif [ "$PROVIDER" = "ollama" ]; then
    echo "  URL: $OLLAMA_URL"
    echo "  Model: $MODEL"
    [ -n "$OLLAMA_TOKEN" ] && echo "  Token: ${OLLAMA_TOKEN:0:10}..."
else
    echo "  URL: $LMSTUDIO_URL"
    echo "  Model: $MODEL"
    [ -n "$LMSTUDIO_TOKEN" ] && echo "  Token: ${LMSTUDIO_TOKEN:0:10}..."
fi
echo ""
echo "MCP Server:"
echo "  Port: $MCP_PORT"
echo "  Token: ${MCP_TOKEN:0:10}..."
echo "  Log Level: $LOG_LEVEL"
echo ""

read -p "Proceed with installation? [Y/n]: " PROCEED
if [ "$PROCEED" = "n" ] || [ "$PROCEED" = "N" ]; then
    echo "Installation cancelled."
    exit 0
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 5: Creating Configuration${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Create .env file
cat > .env << EOF
# Obsidian RAG MCP Server Configuration
# Generated by docker-setup.sh on $(date)

# Data Source
OBSIDIAN_RAG_SOURCE=$SOURCE

EOF

if [ "$SOURCE" = "couchdb" ]; then
    cat >> .env << EOF
# CouchDB Configuration
OBSIDIAN_RAG_COUCH_URL=$COUCH_URL
OBSIDIAN_RAG_COUCH_DB=$COUCH_DB
OBSIDIAN_RAG_COUCH_USER=$COUCH_USER
OBSIDIAN_RAG_COUCH_PASSWORD=$COUCH_PASSWORD

EOF
fi

cat >> .env << EOF
# Embedding Provider
OBSIDIAN_RAG_PROVIDER=$PROVIDER

EOF

if [ "$PROVIDER" = "openai" ]; then
    cat >> .env << EOF
# OpenAI Configuration
OPENAI_API_KEY=$OPENAI_KEY
OBSIDIAN_RAG_MODEL=$MODEL

EOF
elif [ "$PROVIDER" = "ollama" ]; then
    cat >> .env << EOF
# Ollama Configuration
OBSIDIAN_RAG_OLLAMA_URL=$OLLAMA_URL
OBSIDIAN_RAG_OLLAMA_MODEL=$MODEL
EOF
    [ -n "$OLLAMA_TOKEN" ] && echo "OBSIDIAN_RAG_OLLAMA_API_KEY=$OLLAMA_TOKEN" >> .env
    echo "" >> .env
else
    cat >> .env << EOF
# LM Studio Configuration
OBSIDIAN_RAG_LMSTUDIO_URL=$LMSTUDIO_URL
OBSIDIAN_RAG_LMSTUDIO_MODEL=$MODEL
EOF
    [ -n "$LMSTUDIO_TOKEN" ] && echo "OBSIDIAN_RAG_LMSTUDIO_API_KEY=$LMSTUDIO_TOKEN" >> .env
    echo "" >> .env
fi

cat >> .env << EOF
# MCP Server Configuration
MCP_SERVER_PORT=$MCP_PORT
MCP_SERVER_TOKEN=$MCP_TOKEN

# Logging
LOG_LEVEL=$LOG_LEVEL
EOF

echo -e "${GREEN}✓ Configuration saved to .env${NC}"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Step 6: Building and Starting Container${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

echo "Building Docker image..."
docker-compose -f docker-compose.yml build

echo ""
echo "Starting services..."
docker-compose -f docker-compose.yml up -d

echo ""
echo "Waiting for services to be ready..."
sleep 5

# Check health
echo ""
echo -e "${YELLOW}Checking service health...${NC}"
for i in {1..10}; do
    if curl -sf http://localhost:$MCP_PORT/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ MCP Server is healthy${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${YELLOW}⚠ Server is starting (may take a minute)${NC}"
    else
        sleep 2
    fi
done

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "MCP Server is running at: http://localhost:$MCP_PORT"
echo ""
echo "Next steps:"
echo ""
if [ "$SOURCE" = "couchdb" ]; then
    echo "1. Configure Obsidian Self-hosted LiveSync plugin:"
    echo "   - URL: $COUCH_URL"
    echo "   - Database: $COUCH_DB"
    echo "   - Username: $COUCH_USER"
    echo "   - Password: (your password)"
    echo ""
    echo "2. After syncing notes, run initial indexing:"
    echo "   docker exec obsidian-rag-mcp python -m obsidian_rag.cli index"
else
    echo "1. Run initial indexing:"
    echo "   docker exec obsidian-rag-mcp python -m obsidian_rag.cli index"
fi
echo ""
echo "3. Test the server:"
echo "   curl -H \"Authorization: Bearer $MCP_TOKEN\" http://localhost:$MCP_PORT/tools"
echo ""
echo "4. Check logs:"
echo "   docker-compose -f docker-compose.yml logs -f"
echo ""
echo "5. Connect MCP clients:"
echo "   - URL: http://localhost:$MCP_PORT"
echo "   - Token: $MCP_TOKEN"
echo ""
echo "Useful commands:"
echo "  docker-compose -f docker-compose.yml ps       # Show status"
echo "  docker-compose -f docker-compose.yml logs -f  # View logs"
echo "  docker-compose -f docker-compose.yml down     # Stop services"
echo "  docker-compose -f docker-compose.yml restart  # Restart services"
echo ""
echo "Configuration saved in: .env"
echo "Documentation: docs/HTTP_MCP_SETUP.md"
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""