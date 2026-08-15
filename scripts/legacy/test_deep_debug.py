#!/usr/bin/env python3
"""Deep debug KB loader and LLM API."""
import sys, os, json, urllib.request

sys.path.insert(0, "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend")

def test_kb_loader():
    print("=== KB Loader Test ===")
    try:
        from app.knowledge.loader import get_knowledge_base, fuzzy_lookup_taxon, lookup_disease, get_all_diseases, get_all_taxa
        kb = get_knowledge_base()
        print(f"KB initialized")
        
        # Test taxon lookup
        taxa = get_all_taxa()
        print(f"Total taxa: {len(taxa)}")
        print(f"First 5: {taxa[:5]}")
        
        # Test fuzzy lookup
        result = fuzzy_lookup_taxon("Faecalibacterium", limit=2)
        print(f"Fuzzy lookup 'Faecalibacterium': {len(result)} results")
        
        # Test disease lookup
        diseases = get_all_diseases()
        print(f"Total diseases: {len(diseases)}")
        print(f"First 5: {diseases[:5]}")
        
        d = lookup_disease("inflammatory_bowel_disease")
        print(f"IBD lookup: {d is not None}")
        if d:
            print(f"  Key genera: {d.get('key_genera', [])[:3]}")
    except Exception as e:
        print(f"KB loader test failed: {e}")
        import traceback
        traceback.print_exc()

def test_llm_api():
    print("\n=== LLM API Test ===")
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        print("No KIMI_API_KEY found")
        return
    
    # Try different endpoints
    endpoints = [
        ("https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-8k"),
        ("https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-32k"),
    ]
    
    for url, model in endpoints:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 10,
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
                print(f"  {model}: SUCCESS")
                print(f"    Response: {data['choices'][0]['message']['content'][:50]}...")
                return
        except urllib.error.HTTPError as e:
            print(f"  {model}: HTTP {e.code} - {e.read().decode()[:100]}")
        except Exception as e:
            print(f"  {model}: {e}")

if __name__ == "__main__":
    test_kb_loader()
    test_llm_api()
