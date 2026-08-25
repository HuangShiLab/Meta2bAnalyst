import urllib.request, json, sys
sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import extract_text, SYSTEM_PROMPT
from pathlib import Path

pdf_path = Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/PMID39807439.pdf')
text = extract_text(pdf_path)

for chars in [5000, 10000, 15000, 20000, 25000, 30000]:
    user_prompt = (
        f"Paper file: {pdf_path.name}\n"
        f"PMID: 39807439\n\n"
        "=== PAPER TEXT (truncated) ===\n" + text[:chars]
    )
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        "https://api.kimi.com/coding/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-kimi-alm8qAvprNGa2cpFSBymJWg9w8ReTu86wWoVIVyVKB5GUbj3p11UPlETWczwFizm",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print(f"Chars {chars}: SUCCESS")
            break
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode())
        msg = body.get('error', {}).get('message', 'unknown')
        print(f"Chars {chars}: FAIL - {msg}")
