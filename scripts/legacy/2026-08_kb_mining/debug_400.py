import urllib.request, json, sys
sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import extract_text, SYSTEM_PROMPT
from pathlib import Path

pdf_path = Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/PMID39807439.pdf')
text = extract_text(pdf_path)
print(f"Extracted text length: {len(text)} chars")

user_prompt = (
    f"Paper file: {pdf_path.name}\n"
    f"PMID: 39807439\n\n"
    "=== PAPER TEXT (truncated) ===\n" + text[:90000]
)
print(f"Prompt length: {len(user_prompt)} chars")

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
    with urllib.request.urlopen(req, timeout=180) as r:
        print("SUCCESS")
        print(r.read().decode()[:500])
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
    body = e.read().decode()
    print(f"Response body: {body}")
