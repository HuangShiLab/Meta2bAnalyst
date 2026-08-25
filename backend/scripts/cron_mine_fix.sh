#!/bin/bash
# 临时处理剩余4篇PDF，使用较小的max-chars避免HTTP 400

cd /Users/macstudio/Downloads/meta2banalyst/backend

export COLLECTOR_HOME=/Users/macstudio/Downloads/oral-microbiome-data-collector
export M2B=/Users/macstudio/Downloads/meta2banalyst

# 先处理可能因文本过长导致HTTP 400的39807439
env -u KIMI_BASE_URL \
  venv/bin/python3 scripts/literature_mine.py \
  --pdf-dir "$COLLECTOR_HOME/papers/pdfs" \
  --out-dir knowledge_staging \
  --max-chars 30000 \
  --sleep 2.0 \
  >> logs/cron_mine.log 2>&1
