#!/bin/bash
# Quick start script for Obsidian RAG Docker setup

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  Obsidian RAG - Quick Start Setup"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install it first:"
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✓ Docker and docker-compose are installed"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
# CouchDB Configuration
COUCHDB_USER=admin
COUCHDB_PASSWORD=changeme123

# Obsidian RAG Configuration
OBSIDIAN_RAG_SOURCE=couchdb
OBSIDIAN_RAG_COUCH_DB=obsidian

# Embedding Provider
OBSIDIAN_RAG_PROVIDER=ollama
OBSIDIAN_RAG_OLLAMA_MODEL=nomic-embed-text

# Optional: OpenAI (uncomment to use instead of Ollama)
# OPENAI_API_KEY=sk-...
# OBSIDIAN_RAG_PROVIDER=openai
# OBSIDIAN_RAG_MODEL=text-embedding-3-small
EOF
    echo "✓ Created .env file with default settings"
    echo "⚠️  Please edit .env and change COUCHDB_PASSWORD!"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to exit and edit .env..."
else
    echo "✓ .env file already exists"
fi

echo ""
echo "Starting services..."
echo "This may take a few minutes on first run."
echo ""

# Build and start services
docker-compose up -d --build

echo ""
echo "Waiting for services to be ready..."
sleep 10

# Check service health
echo ""
echo "Checking service health..."
echo ""

# Check CouchDB
echo -n "CouchDB: "
if curl -sf http://localhost:5984/_up > /dev/null 2>&1; then
    echo "✓ Running"
else
    echo "⚠️  Not responding (may still be starting)"
fi

# Check Ollama
echo -n "Ollama: "
if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Running"
else
    echo "⚠️  Not responding (may still be starting)"
fi

# Check RAG server
echo -n "RAG Server: "
if docker exec obsidian-rag-mcp python -c "from src.obsidian_rag.store import VectorStore; VectorStore('/data').get_stats()" > /dev/null 2>&1; then
    echo "✓ Running"
else
    echo "⚠️  Not responding (may still be starting)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "1. Pull Ollama embedding model:"
echo "   make init-ollama"
echo "   (or manually: docker exec obsidian-ollama ollama pull nomic-embed-text)"
echo ""
echo "2. Configure Obsidian Self-hosted LiveSync plugin:"
echo "   - URL: http://localhost:5984"
echo "   - Database: obsidian"
echo "   - Username: admin"
echo "   - Password: (from your .env file)"
echo ""
echo "3. After syncing some notes, run initial indexing:"
echo "   make index"
echo ""
echo "4. Check index statistics:"
echo "   make stats"
echo ""
echo "5. View logs:"
echo "   make logs"
echo ""
echo "Useful commands:"
echo "  make help     - Show all available commands"
echo "  make ps       - Show running containers"
echo "  make health   - Check service health"
echo "  make backup   - Backup data"
echo ""
echo "Web interfaces:"
echo "  CouchDB: http://localhost:5984/_utils"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo ""