#!/usr/bin/env python3
"""Test LLM-enhanced interpretation."""
import json, urllib.request

API = "http://localhost:8000"

def test_llm_enhanced():
    payload = {
        "results": {
            "alpha-diversity": {
                "job_type": "alpha",
                "status": "completed",
                "result_data": {
                    "group_statistics": {
                        "shannon": {
                            "T4": {"mean": 2.44, "std": 0.12, "n": 10},
                            "T5": {"mean": 2.37, "std": 0.12, "n": 10},
                            "statistical_test": {"test": "Mann-Whitney U", "pvalue": 0.273, "significant": False}
                        }
                    }
                }
            },
            "beta-diversity": {
                "job_type": "beta",
                "status": "completed",
                "result_data": {
                    "metric": "braycurtis",
                    "group_comparison": {"test": "PERMANOVA", "pvalue": 0.001, "r2": 0.15, "significant": True}
                }
            },
            "lefse": {
                "job_type": "lefse",
                "status": "completed",
                "result_data": {
                    "significant_features": [
                        {"feature": "Bacteroides", "lda_score": 4.2, "group": "T4"},
                        {"feature": "Faecalibacterium", "lda_score": 3.8, "group": "T5"}
                    ]
                }
            }
        },
        "question": "为什么Alpha diversity不显著但LEfSe找到了差异？",
        "metadata_summary": {"n_samples": 20, "data_type": "metagenomics"}
    }
    req = urllib.request.Request(
        f"{API}/api/v1/agent/interpret-full",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
            print(f"Status: {r.status}")
            print(f"LLM enhanced: {data.get('llm_enhanced', False)}")
            print(f"LLM model: {data.get('llm_model', 'N/A')}")
            print(f"\nIntegrated narrative (first 500 chars):")
            print(data.get('integrated_narrative', 'N/A')[:500])
            print(f"\nDisease relevance count: {len(data.get('disease_relevance', []))}")
            return data
    except Exception as e:
        print(f"Test failed: {e}")
        return None

def test_kb_expanded():
    """Test that expanded KB is loaded."""
    req = urllib.request.Request(
        f"{API}/api/v1/agent/interpret-full",
        data=json.dumps({
            "results": {
                "lefse": {
                    "job_type": "lefse",
                    "status": "completed",
                    "result_data": {
                        "significant_features": [
                            {"feature": "Alistipes_putredinis", "lda_score": 4.0, "group": "T4"},
                            {"feature": "Fusobacterium_nucleatum", "lda_score": 3.5, "group": "T5"}
                        ]
                    }
                }
            },
            "metadata_summary": {"n_samples": 20}
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
            print(f"\nExpanded KB test:")
            print(f"  Disease relevance: {len(data.get('disease_relevance', []))} matches")
            for dr in data.get('disease_relevance', [])[:3]:
                print(f"    - {dr['disease']}: {', '.join(dr['matched_taxa'])}")
            print(f"  Biological context: {len(data.get('biological_context', []))} annotations")
    except Exception as e:
        print(f"KB test failed: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing LLM-enhanced interpretation")
    print("=" * 60)
    test_llm_enhanced()
    test_kb_expanded()
