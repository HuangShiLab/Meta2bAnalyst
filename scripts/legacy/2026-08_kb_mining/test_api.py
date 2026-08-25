import json
import urllib.request

payload = {
    "model": "moonshot-v1-8k",
    "messages": [{"role": "system", "content": "Say hello"}],
    "max_tokens": 10,
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
    resp = urllib.request.urlopen(req, timeout=30)
    print("SUCCESS:", json.loads(resp.read().decode()))
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code, e.read().decode())
except Exception as e:
    print("ERROR:", type(e).__name__, e)
