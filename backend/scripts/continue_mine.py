#!/usr/bin/env python3
"""带超时保护的文献挖掘 —— 处理剩余论文"""
import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path("/Users/macstudio/Downloads/meta2banalyst/backend")
PDF_DIR = Path("/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs")
OUT_DIR = BACKEND / "knowledge_staging"
PAPERS_DIR = OUT_DIR / "papers"
LOG = BACKEND / "logs" / "continue_mine.log"

# 获取剩余论文
pdfs = sorted(PDF_DIR.glob("*.pdf"))
done = set(p.stem for p in PAPERS_DIR.glob("*.json"))
todo = [p for p in pdfs if p.stem not in done]

total = len(pdfs)
remaining = len(todo)
processed = len(done)

print(f"总 PDF: {total}, 已处理: {processed}, 剩余: {remaining}")

with open(LOG, "a") as log_fh:
    log_fh.write(f"\n=== 继续处理 {remaining} 篇论文 ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
    log_fh.flush()
    
    for i, pdf in enumerate(todo, 1):
        out_path = PAPERS_DIR / f"{pdf.stem}.json"
        if out_path.exists():
            print(f"[{i}/{remaining}] 跳过（已处理）: {pdf.name}")
            continue
        
        print(f"[{i}/{remaining}] 处理: {pdf.name}")
        cmd = [
            str(BACKEND / "venv" / "bin" / "python3"),
            str(BACKEND / "scripts" / "literature_mine.py"),
            "--pdf-dir", str(PDF_DIR),
            "--out-dir", str(OUT_DIR),
            "--limit", "1",
            "--max-chars", "30000",
            "--sleep", "1.0",
        ]
        env = os.environ.copy()
        env.pop("KIMI_BASE_URL", None)  # 取消覆盖，让 .env 生效
        
        try:
            result = subprocess.run(
                cmd,
                cwd=BACKEND,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                env=env,
            )
            msg = f"[{i}/{remaining}] 完成: {pdf.name} (exit={result.returncode})"
            if result.stdout:
                msg += f"\nstdout: {result.stdout[-500:]}"
            if result.stderr:
                msg += f"\nstderr: {result.stderr[-500:]}"
            print(msg)
            log_fh.write(msg + "\n")
            log_fh.flush()
        except subprocess.TimeoutExpired:
            msg = f"[{i}/{remaining}] 超时: {pdf.name} (超过5分钟，跳过)"
            print(msg)
            log_fh.write(msg + "\n")
            log_fh.flush()
        except Exception as e:
            msg = f"[{i}/{remaining}] 错误: {pdf.name} ({e})"
            print(msg)
            log_fh.write(msg + "\n")
            log_fh.flush()
        
        time.sleep(2)

# 最终统计
done_final = set(p.stem for p in PAPERS_DIR.glob("*.json"))
remaining_final = total - len(done_final)
print(f"\n完成! 总: {total}, 已处理: {len(done_final)}, 剩余: {remaining_final}")
