#!/bin/bash
# Meta2bAnalyst - Celery Worker Startup Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${RED}Virtual environment not found. Please run: python3 -m venv venv${NC}"
    exit 1
fi

# Check Redis connection
echo -e "${YELLOW}Checking Redis connection...${NC}"
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}Warning: Redis is not running. Please start Redis first.${NC}"
    echo -e "${YELLOW}You can start Redis with: redis-server${NC}"
fi

echo -e "${GREEN}Starting Celery worker for Meta2bAnalyst...${NC}"

# Run Celery worker
exec celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    -Q analysis,export,default
