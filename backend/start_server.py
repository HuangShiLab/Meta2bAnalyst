#!/usr/bin/env python3
import subprocess, os, sys

os.chdir('/Users/shihuang/Documents/kimi/workspace/meta2bAnalyst/backend')

# Kill existing
subprocess.run("ps aux | grep uvicorn | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null", shell=True)
import time
time.sleep(1)

log = open('backend.log', 'w')
p = subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    cwd=os.getcwd(),
    stdout=log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
print(p.pid)
