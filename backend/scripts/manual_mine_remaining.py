#!/usr/bin/env python3
"""手动处理剩余4篇PDF，使用较小max-chars并捕获HTTPError."""
import json, sys, time
from pathlib import Path

sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import mine_paper
from app.config import settings

PDF_DIR = Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs')
PAPERS_DIR = Path('/Users/macstudio/Downloads/meta2banalyst/backend/knowledge_staging/papers')
ASSOC_PATH = Path('/Users/macstudio/Downloads/meta2banalyst/backend/knowledge_staging/associations.jsonl')
FAILED_PATH = Path('/Users/macstudio/Downloads/meta2banalyst/backend/knowledge_staging/failed.json')

pdfs = [
    'PMID39807439.pdf',
    'PMID40496020.pdf',
    'PMID40601605.pdf',
    'PMID40654456.pdf',
]

client_cfg = {
    "api_key": settings.KIMI_API_KEY,
    "base_url": settings.KIMI_BASE_URL.rstrip("/"),
    "model": settings.KIMI_MODEL,
}

failed = []
n_ok = 0

with ASSOC_PATH.open("a") as assoc_f:
    for i, name in enumerate(pdfs, 1):
        pdf = PDF_DIR / name
        if not pdf.exists():
            print(f"[{i}/{len(pdfs)}] SKIP (not found): {name}")
            continue
        out_path = PAPERS_DIR / f"{pdf.stem}.json"
        if out_path.exists():
            print(f"[{i}/{len(pdfs)}] SKIP (already mined): {name}")
            n_ok += 1
            continue
        try:
            result = mine_paper(pdf, client_cfg, max_chars=30000)
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
            for a in result["associations"]:
                assoc_f.write(json.dumps({
                    "pmid": result["pmid"], "paper": result["title"], **a,
                }, ensure_ascii=False) + "\n")
            n_ok += 1
            print(f"[{i}/{len(pdfs)}] OK {name}: {result['n_associations']} associations ({result['n_quote_verified']} verified)")
        except Exception as e:
            failed.append({"file": name, "reason": str(e)[:300]})
            print(f"[{i}/{len(pdfs)}] FAIL {name}: {e}")
        time.sleep(2.0)

FAILED_PATH.write_text(json.dumps(failed, ensure_ascii=False, indent=1) + "\n")
print(f"done: {n_ok} ok, {len(failed)} failed")
