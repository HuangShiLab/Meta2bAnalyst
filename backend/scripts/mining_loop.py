#!/usr/bin/env python3
"""后台文献挖掘循环管理器 —— 带超时保护"""
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path("/Users/macstudio/Downloads/meta2banalyst/backend")
LOG = BACKEND / "logs" / "cron_mine.log"

def run_batch():
    """运行一批挖掘，最长等待10分钟。"""
    cmd = ["bash", str(BACKEND / "scripts" / "cron_mine.sh")]
    try:
        with open(LOG, "a") as fh:
            proc = subprocess.Popen(
                cmd,
                cwd=BACKEND,
                stdout=fh,
                stderr=subprocess.STDOUT,
            )
            try:
                proc.wait(timeout=600)  # 10分钟超时
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                fh.write("\n[BATCH_TIMEOUT] 批次处理超过10分钟，已强制终止\n")
                fh.flush()
    except Exception as e:
        with open(LOG, "a") as fh:
            fh.write(f"\n[BATCH_ERROR] {e}\n")
            fh.flush()

def main():
    print("[mining_loop] 启动后台挖掘循环", file=sys.stderr)
    while True:
        run_batch()
        time.sleep(15)  # 批次间休息15秒

if __name__ == "__main__":
    raise SystemExit(main())
