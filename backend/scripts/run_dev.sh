#!/bin/bash
# Meta2bAnalyst - Development Server Startup Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${RED}Virtual environment not found. Please run: python3 -m venv venv${NC}"
    exit 1
fi

# Ensure directories exist
mkdir -p uploads logs

echo -e "${GREEN}Starting Meta2bAnalyst development server...${NC}"
echo -e "${YELLOW}Host: $HOST${NC}"
echo -e "${YELLOW}Port: $PORT${NC}"
echo -e "${YELLOW}API docs: http://localhost:$PORT/docs${NC}"
echo -e "${YELLOW}Health check: http://localhost:$PORT/health${NC}"
echo ""

# Run uvicorn with auto-reload for development
exec uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    --log-level info \
    --access-log
