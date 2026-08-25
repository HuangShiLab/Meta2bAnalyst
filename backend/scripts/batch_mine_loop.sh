#!/bin/bash
# Meta2bAnalyst - 后台批量文献挖掘循环
# 不受交互式超时限制，自动处理所有剩余PDF

# 不设置 set -e，因为 literature_mine.py 在有失败论文时返回非零码，这属于正常情况

cd /Users/macstudio/Downloads/meta2banalyst/backend

export COLLECTOR_HOME=/Users/macstudio/Downloads/oral-microbiome-data-collector
export M2B=/Users/macstudio/Downloads/meta2banalyst

LOG="logs/batch_mine_loop.log"
ROUND=0

while true; do
    ROUND=$((ROUND + 1))
    echo "=== Round $ROUND $(date '+%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
    
    env -u KIMI_BASE_URL \
      venv/bin/python3 scripts/literature_mine.py \
      --pdf-dir "$COLLECTOR_HOME/papers/pdfs" \
      --out-dir knowledge_staging \
      --limit 1 \
      --max-chars 30000 \
      --sleep 2.0 \
      2>&1 | tee -a "$LOG"
    
    EXIT_CODE=${PIPESTATUS[0]}
    echo "Round $ROUND exit code: $EXIT_CODE" | tee -a "$LOG"
    
    # 检查是否还有剩余PDF
    REMAINING=$(comm -23 \
        <(ls "$COLLECTOR_HOME/papers/pdfs"/*.pdf | xargs -n1 basename | sed 's/\.pdf$//' | sort) \
        <(ls knowledge_staging/papers/*.json 2>/dev/null | xargs -n1 basename | sed 's/\.json$//' | sort) \
        | wc -l)
    
    echo "Remaining PDFs: $REMAINING" | tee -a "$LOG"
    
    if [ "$REMAINING" -eq 0 ]; then
        echo "All PDFs processed. Exiting." | tee -a "$LOG"
        break
    fi
    
    # 每轮之间短暂休息
    sleep 3
done
