#!/bin/bash
# Meta2bAnalyst - 定时LLM挖掘脚本
# 每次处理3篇，避免超时

set -e

cd /Users/macstudio/Downloads/meta2banalyst/backend

export COLLECTOR_HOME=/Users/macstudio/Downloads/oral-microbiome-data-collector
export M2B=/Users/macstudio/Downloads/meta2banalyst

# 取消错误的环境变量覆盖
env -u KIMI_BASE_URL \
  venv/bin/python3 scripts/literature_mine.py \
  --pdf-dir "$COLLECTOR_HOME/papers/pdfs" \
  --out-dir knowledge_staging \
  --limit 3 \
  --sleep 2.0 \
  >> logs/cron_mine.log 2>&1 || true
