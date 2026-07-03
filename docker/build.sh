#!/bin/bash
# Meta2bAnalyst - One-command build and start script
# Usage: ./build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🐳 Meta2bAnalyst Docker Build & Start"
echo "======================================"
echo ""

cd "$PROJECT_DIR"

# Ensure uploads directory exists
mkdir -p backend/uploads backend/logs

# Build and start all services
echo "📦 Building and starting services..."
docker-compose -f docker/docker-compose.yml up --build -d

echo ""
echo "✅ Services started!"
echo ""
echo "  Frontend: http://localhost"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  Logs:     docker-compose -f docker/docker-compose.yml logs -f"
echo "  Stop:     docker-compose -f docker/docker-compose.yml down"
echo "  Restart:  docker-compose -f docker/docker-compose.yml restart"
