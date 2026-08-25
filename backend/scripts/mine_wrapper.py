#!/usr/bin/env python3
"""Wrapper for literature_mine.py: process one PDF at a time, never retry failures."""
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PDF_DIR = Path("/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs")
OUT_DIR = BACKEND / "knowledge_staging"
PAPERS_DIR = OUT_DIR / "papers"
FAILED_PATH = OUT_DIR / "failed.json"

# Ensure dirs exist
PAPERS_DIR.mkdir(parents=True, exist_ok=True)

# Load existing failures (cumulative)
if FAILED_PATH.exists():
    try:
        failed_list = json.loads(FAILED_PATH.read_text())
    except Exception:
        failed_list = []
else:
    failed_list = []
failed_map = {f["file"]: f["reason"] for f in failed_list}

# Find all unprocessed PDFs
pdfs = sorted(PDF_DIR.glob("*.pdf"))
unprocessed = [p for p in pdfs if not (PAPERS_DIR / f"{p.stem}.json").exists()]

print(f"Total PDFs: {len(pdfs)}")
print(f"Already processed: {len(pdfs) - len(unprocessed)}")
print(f"Remaining: {len(unprocessed)}")

if not unprocessed:
    print("All done!")
    sys.exit(0)

for i, pdf in enumerate(unprocessed, 1):
    out_json = PAPERS_DIR / f"{pdf.stem}.json"
    if out_json.exists():
        print(f"[{i}/{len(unprocessed)}] SKIP (already done): {pdf.name}")
        continue

    print(f"[{i}/{len(unprocessed)}] Processing: {pdf.name} ...", flush=True)

    # Run literature_mine.py with limit=1 and a process timeout
    cmd = [
        sys.executable,
        str(BACKEND / "scripts" / "literature_mine.py"),
        "--pdf-dir", str(PDF_DIR),
        "--out-dir", str(OUT_DIR),
        "--limit", "1",
        "--max-chars", "45000",
        "--sleep", "2.0",
    ]
    env = os.environ.copy()
    env["KIMI_BASE_URL"] = "https://api.kimi.com/coding/v1"

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=150)
        # Check if the specific PDF was processed
        if out_json.exists():
            print(f"  -> OK: {pdf.name}")
            continue
    except subprocess.TimeoutExpired:
        print(f"  -> TIMEOUT after 150s: {pdf.name}")
        result = None
    except Exception as e:
        print(f"  -> ERROR: {pdf.name} - {e}")
        result = None

    # If we get here, processing failed or timed out -> create placeholder so we skip next time
    placeholder = {"pmid": None, "source_file": pdf.name, "error": "timeout or processing failed", "associations": []}
    out_json.write_text(json.dumps(placeholder, ensure_ascii=False, indent=1) + "\n")
    failed_map[pdf.name] = "timeout or processing failed"
    print(f"  -> MARKED as failed (placeholder created): {pdf.name}")

# Write cumulative failed.json
new_failed = [{"file": k, "reason": v} for k, v in failed_map.items()]
FAILED_PATH.write_text(json.dumps(new_failed, ensure_ascii=False, indent=1) + "\n")
print(f"\nDone. Cumulative failures: {len(new_failed)}")
print(f"Processed papers: {len(list(PAPERS_DIR.glob('*.json')))}")
