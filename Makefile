.PHONY: help build up down logs restart clean init-ollama index stats shell test

# Default target
help:
	@echo "Obsidian RAG Docker Management"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  build         - Build Docker images"
	@echo "  up            - Start all services"
	@echo "  down          - Stop all services"
	@echo "  logs          - View logs (all services)"
	@echo "  logs-rag      - View RAG server logs"
	@echo "  logs-watcher  - View watcher logs"
	@echo "  restart       - Restart all services"
	@echo "  clean         - Stop and remove all containers, volumes"
	@echo "  init-ollama   - Pull Ollama embedding model"
	@echo "  index         - Run initial indexing"
	@echo "  index-clear   - Clear and rebuild index"
	@echo "  stats         - Show index statistics"
	@echo "  shell         - Open shell in RAG container"
	@echo "  shell-couch   - Open shell in CouchDB container"
	@echo "  test          - Run tests"
	@echo "  backup        - Backup data volumes"
	@echo "  ps            - Show running containers"
	@echo ""

# Build images
build:
	@echo "Building Docker images..."
	docker-compose build

# Start services
up:
	@echo "Starting services..."
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "Services started!"
	@make ps

# Stop services
down:
	@echo "Stopping services..."
	docker-compose down

# View logs
logs:
	docker-compose logs -f

logs-rag:
	docker-compose logs -f obsidian-rag

logs-watcher:
	docker-compose logs -f obsidian-watcher

logs-couch:
	docker-compose logs -f couchdb

logs-ollama:
	docker-compose logs -f ollama

# Restart services
restart:
	@echo "Restarting services..."
	docker-compose restart

# Clean everything
clean:
	@echo "WARNING: This will remove all containers and volumes!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		echo "Cleaned!"; \
	fi

# Initialize Ollama model
init-ollama:
	@echo "Initializing Ollama model..."
	@bash scripts/init-ollama-model.sh

# Run indexing
index:
	@echo "Running indexing..."
	docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli index

index-clear:
	@echo "Clearing and rebuilding index..."
	docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli index --clear

# Show stats
stats:
	@echo "Index statistics:"
	docker exec -it obsidian-rag-mcp python -m obsidian_rag.cli stats

# Open shell
shell:
	docker exec -it obsidian-rag-mcp bash

shell-couch:
	docker exec -it obsidian-couchdb bash

shell-ollama:
	docker exec -it obsidian-ollama bash

# Run tests
test:
	@echo "Running tests..."
	docker exec -it obsidian-rag-mcp python -m pytest tests/

# Backup data
backup:
	@echo "Creating backups..."
	@mkdir -p backups
	@echo "Backing up CouchDB..."
	docker exec obsidian-couchdb curl -X GET http://admin:password@localhost:5984/obsidian/_all_docs?include_docs=true > backups/couchdb-backup-$$(date +%Y%m%d-%H%M%S).json
	@echo "Backing up vector index..."
	docker run --rm -v obsidian-notes-rag_rag-data:/data -v $$(pwd)/backups:/backup alpine tar czf /backup/rag-data-$$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@echo "Backups created in ./backups/"

# Show running containers
ps:
	@docker-compose ps

# Full setup (first time)
setup: build up init-ollama
	@echo ""
	@echo "Setup complete!"
	@echo "Next steps:"
	@echo "  1. Configure Obsidian Self-hosted LiveSync plugin"
	@echo "  2. Run: make index"
	@echo "  3. Check: make stats"
	@echo ""

# Health check
health:
	@echo "Checking service health..."
	@echo ""
	@echo "CouchDB:"
	@curl -s http://localhost:5984/_up | jq . || echo "Not responding"
	@echo ""
	@echo "Ollama:"
	@curl -s http://localhost:11434/api/tags | jq '.models | length' || echo "Not responding"
	@echo ""
	@echo "RAG Server:"
	@docker exec obsidian-rag-mcp python -c "from src.obsidian_rag.store import VectorStore; print('OK - ' + str(VectorStore('/data').get_stats()['count']) + ' documents')" || echo "Not responding"
	@echo ""