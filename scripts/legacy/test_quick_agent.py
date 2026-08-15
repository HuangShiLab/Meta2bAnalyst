#!/usr/bin/env python3
"""Test Agent interpret-full endpoint with sample data."""
import json, urllib.request

API = "http://localhost:8000"

def test_health():
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=5) as r:
            print(f"Health: {r.read().decode()}")
            return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def test_interpret_full():
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
        "question": "为什么Alpha diversity不显著但LEfSe找到了差异？"
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
            print(f"\ninterpret-full status: {r.status}")
            print(f"Response keys: {list(data.keys())}")
            print("\n=== FULL RESPONSE ===")
            for key, value in data.items():
                print(f"\n--- {key} ---")
                if isinstance(value, str):
                    print(value)
                elif isinstance(value, list) and value and isinstance(value[0], str):
                    for item in value:
                        print(f"  - {item}")
                else:
                    print(json.dumps(value, indent=2, ensure_ascii=False))
            return data
    except Exception as e:
        print(f"interpret-full failed: {e}")
        return None

if __name__ == "__main__":
    if test_health():
        test_interpret_full()
