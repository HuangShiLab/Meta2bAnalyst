#!/usr/bin/env python3
"""Debug KB and LLM loading."""
import json, urllib.request, sys, os

API = "http://localhost:8000"

def test_kb_direct():
    """Test knowledge base directly via API."""
    # Test if we can get module list (proves backend is running)
    try:
        with urllib.request.urlopen(f"{API}/api/v1/agent/modules", timeout=5) as r:
            modules = json.loads(r.read().decode())
            print(f"Modules: {modules.get('total', 0)} total")
    except Exception as e:
        print(f"Modules API failed: {e}")
        return

    # Test interpret-full with known taxa from original KB
    payload = {
        "results": {
            "lefse": {
                "job_type": "lefse",
                "status": "completed",
                "result_data": {
                    "significant_features": [
                        {"feature": "Faecalibacterium_prausnitzii", "lda_score": 4.2, "group": "T4"},
                        {"feature": "Bacteroides_thetaiotaomicron", "lda_score": 3.8, "group": "T5"}
                    ]
                }
            }
        },
        "metadata_summary": {"n_samples": 20}
    }
    req = urllib.request.Request(
        f"{API}/api/v1/agent/interpret-full",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
            print(f"\nOriginal KB taxa test:")
            print(f"  Biological context: {len(data.get('biological_context', []))}")
            for ctx in data.get('biological_context', [])[:2]:
                print(f"    - {ctx[:80]}...")
            print(f"  Disease relevance: {len(data.get('disease_relevance', []))}")
            for dr in data.get('disease_relevance', [])[:2]:
                print(f"    - {dr['disease']}: {', '.join(dr['matched_taxa'])}")
    except Exception as e:
        print(f"Interpret test failed: {e}")

def test_env():
    """Check if KIMI_API_KEY is available in backend process."""
    # We can't directly check backend env, but we can check our own
    key = os.getenv("KIMI_API_KEY")
    print(f"\nLocal KIMI_API_KEY: {'Present' if key else 'Missing'}")
    if key:
        print(f"  Key prefix: {key[:20]}...")

def test_llm_client_directly():
    """Test LLM client directly."""
    sys.path.insert(0, "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend")
    try:
        from app.services.llm_client import get_llm_client
        client = get_llm_client()
        print(f"\nLLM Client:")
        print(f"  Available: {client.available}")
        if client.available:
            print(f"  API Key prefix: {client.api_key[:20]}...")
            # Quick test
            result = client.enhance_narrative(
                integrated_narrative="Test narrative",
                biological_context=[],
                caveats=[],
                follow_up=[],
                contradictions=[],
                disease_relevance=[],
                question="Test question",
            )
            print(f"  LLM test result: llm_used={result.get('llm_used')}")
            if result.get('llm_used'):
                print(f"  Enhanced text preview: {result['enhanced_narrative'][:100]}...")
    except Exception as e:
        print(f"LLM client test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Debug KB and LLM Loading")
    print("=" * 60)
    test_env()
    test_kb_direct()
    test_llm_client_directly()
