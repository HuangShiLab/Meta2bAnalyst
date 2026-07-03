#!/bin/bash
# Meta2bAnalyst - Development environment startup script
# Usage: ./dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔧 Meta2bAnalyst Development Environment"
echo "========================================="
echo ""

# Check if Redis container is already running
if ! docker ps --format "{{.Names}}" | grep -q "^meta2b-redis$"; then
    # Check if a stopped container exists
    if docker ps -a --format "{{.Names}}" | grep -q "^meta2b-redis$"; then
        echo "🟢 Starting existing Redis container..."
        docker start meta2b-redis
    else
        echo "🟢 Starting Redis container..."
        docker run -d --name meta2b-redis -p 6379:6379 redis:7-alpine
    fi
else
    echo "🟢 Redis container already running."
fi

echo ""

# Start backend (background)
echo "🟢 Starting backend (FastAPI + Uvicorn)..."
cd "$PROJECT_DIR/backend"
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠️  Virtual environment not found. Please create one:"
    echo "   cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Ensure uploads directory exists
mkdir -p uploads logs

# Kill any existing uvicorn process on port 8000
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > logs/dev_backend.log 2>&1 &
BACKEND_PID=$!

echo "  Backend PID: $BACKEND_PID"
echo "  Backend Log: backend/logs/dev_backend.log"
echo ""

# Start frontend (background)
echo "🟢 Starting frontend (Vite + React)..."
cd "$PROJECT_DIR/frontend"

# Kill any existing vite process
pkill -f "vite" 2>/dev/null || true
sleep 1

npm run dev > /dev/null 2>&1 &
FRONTEND_PID=$!

echo "  Frontend PID: $FRONTEND_PID"
echo ""

# Save PIDs for cleanup
echo "$BACKEND_PID" > "$PROJECT_DIR/.dev_backend.pid"
echo "$FRONTEND_PID" > "$PROJECT_DIR/.dev_frontend.pid"

echo "✅ All services started!"
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Redis:     redis://localhost:6379"
echo ""
echo "Stop all services:"
echo "  kill $BACKEND_PID $FRONTEND_PID && docker stop meta2b-redis"
echo ""
echo "Tail backend logs: tail -f backend/logs/dev_backend.log"
