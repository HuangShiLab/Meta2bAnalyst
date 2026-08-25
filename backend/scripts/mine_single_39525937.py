#!/usr/bin/env python3
"""单独处理 PMID39525937，捕获所有异常."""
import sys, json, time
sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import mine_paper
from app.config import settings
from pathlib import Path

pdf = Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/PMID39525937.pdf')
out_path = Path('/Users/macstudio/Downloads/meta2banalyst/backend/knowledge_staging/papers/PMID39525937.json')

client_cfg = {
    "api_key": settings.KIMI_API_KEY,
    "base_url": settings.KIMI_BASE_URL.rstrip("/"),
    "model": settings.KIMI_MODEL,
}

try:
    result = mine_paper(pdf, client_cfg, max_chars=30000)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(f"OK: {result['n_associations']} associations")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
