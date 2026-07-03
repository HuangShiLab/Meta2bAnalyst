# Meta2bAnalyst - Makefile

.PHONY: dev build up down stop logs test clean help

# Default target
help:
	@echo "Meta2bAnalyst - Available Commands"
	@echo "=================================="
	@echo "  make dev       - Start development environment (frontend + backend + redis)"
	@echo "  make build     - Build all Docker images"
	@echo "  make up        - Start production services with Docker (detached)"
	@echo "  make down      - Stop production Docker services"
	@echo "  make stop      - Stop all dev services (backend, frontend, redis)"
	@echo "  make logs      - Tail Docker Compose logs"
	@echo "  make test      - Run backend tests with pytest"
	@echo "  make clean     - Remove Docker containers, volumes, and prune images"
	@echo "  make help      - Show this help message"

# Development: start frontend, backend, and redis locally
dev:
	@echo "Starting development environment..."
	@bash docker/dev.sh

# Docker: build all images
build:
	docker-compose -f docker/docker-compose.yml build

# Docker: start production services (detached)
up:
	docker-compose -f docker/docker-compose.yml up -d

# Docker: stop production services
down:
	docker-compose -f docker/docker-compose.yml down

# Stop all dev services (uses saved PID files)
stop:
	@echo "Stopping development services..."
	@if [ -f .dev_backend.pid ]; then kill $$(cat .dev_backend.pid) 2>/dev/null || true; rm -f .dev_backend.pid; fi
	@if [ -f .dev_frontend.pid ]; then kill $$(cat .dev_frontend.pid) 2>/dev/null || true; rm -f .dev_frontend.pid; fi
	@docker stop meta2b-redis 2>/dev/null || true

# Docker: tail logs
logs:
	docker-compose -f docker/docker-compose.yml logs -f

# Run backend tests
test:
	cd backend && source venv/bin/activate && pytest -v

# Docker: clean everything
clean:
	docker-compose -f docker/docker-compose.yml down -v
	docker system prune -f
	@echo "Docker containers, volumes, and unused images removed."
