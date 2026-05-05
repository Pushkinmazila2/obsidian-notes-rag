#!/bin/bash
# Initialize Ollama with embedding model
# This script should be run from the host machine, not inside a container

set -e

OLLAMA_CONTAINER=${OLLAMA_CONTAINER:-obsidian-ollama}
MODEL=${OBSIDIAN_RAG_OLLAMA_MODEL:-nomic-embed-text}

echo "Checking if Ollama container is running..."
if ! docker ps | grep -q "$OLLAMA_CONTAINER"; then
    echo "Error: Ollama container '$OLLAMA_CONTAINER' is not running"
    echo "Start it with: docker-compose up -d ollama"
    exit 1
fi

echo "Waiting for Ollama to be ready..."
until docker exec "$OLLAMA_CONTAINER" curl -f http://localhost:11434/api/tags > /dev/null 2>&1; do
    echo "Ollama not ready yet, waiting..."
    sleep 5
done

echo "Ollama is ready!"

# Check if model exists
echo "Checking if model $MODEL exists..."
if docker exec "$OLLAMA_CONTAINER" ollama list | grep -q "$MODEL"; then
    echo "✓ Model $MODEL already exists"
else
    echo "Pulling model $MODEL (this may take a few minutes)..."
    docker exec "$OLLAMA_CONTAINER" ollama pull "$MODEL"
    echo "✓ Model $MODEL pulled successfully"
fi

echo ""
echo "Ollama initialization complete!"
echo "Available models:"
docker exec "$OLLAMA_CONTAINER" ollama list