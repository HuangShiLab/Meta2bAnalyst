#!/usr/bin/env python3
"""调试 PMID39807439 的 HTTP 400 问题."""
import sys, json, urllib.request
sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import extract_text, SYSTEM_PROMPT
from app.config import settings

pdf_path = '/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/PMID39807439.pdf'
text = extract_text(__import__('pathlib').Path(pdf_path))
print('文本长度:', len(text))

# 构造 prompt
prompt = f"Paper file: PMID39807439.pdf\nPMID: 39807439\n\n=== PAPER TEXT (truncated) ===\n" + text[:30000]
print('Prompt 长度:', len(prompt))

payload = {
    "model": settings.KIMI_MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ],
    "max_tokens": 8000,
    "response_format": {"type": "json_object"},
}

base_url = settings.KIMI_BASE_URL.rstrip('/')
print('Base URL:', base_url)
print('API URL:', base_url + '/chat/completions')

req = urllib.request.Request(
    base_url + '/chat/completions',
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.KIMI_API_KEY}",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=180) as r:
        response = json.loads(r.read().decode())
    print('Response keys:', response.keys())
    content = response["choices"][0]["message"]["content"]
    print('Content length:', len(content))
    print('Content preview:', content[:500])
except Exception as e:
    print('ERROR:', type(e).__name__, e)
    # 如果是 HTTPError，打印响应体
    if hasattr(e, 'read'):
        body = e.read().decode()
        print('Response body:', body[:500])
