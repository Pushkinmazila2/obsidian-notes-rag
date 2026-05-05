#!/bin/bash
# Initialize Ollama with embedding model

set -e

echo "Waiting for Ollama to be ready..."
until curl -f http://ollama:11434/api/tags > /dev/null 2>&1; do
    echo "Ollama not ready yet, waiting..."
    sleep 5
done

echo "Ollama is ready!"

# Pull embedding model
MODEL=${OBSIDIAN_RAG_OLLAMA_MODEL:-nomic-embed-text}
echo "Pulling model: $MODEL"

if ollama list | grep -q "$MODEL"; then
    echo "Model $MODEL already exists"
else
    echo "Pulling model $MODEL..."
    ollama pull "$MODEL"
    echo "Model $MODEL pulled successfully"
fi

echo "Ollama initialization complete!"