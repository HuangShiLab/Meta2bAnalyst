#!/usr/bin/env python3
import json
import sys
sys.path.insert(0, '/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend')

# Build proper payload from demo_results.json
with open('/Users/shihuang/Documents/kimi/workspace/meta2banalyst/demo_results.json', 'r') as f:
    results = json.load(f)

payload = {
    "results": results,
    "metadata_summary": {
        "n_samples": 20,
        "n_groups": 2,
        "data_type": "metagenomics"
    }
}

with open('/Users/shihuang/Documents/kimi/workspace/meta2banalyst/test_payload.json', 'w') as f:
    json.dump(payload, f, indent=2)

print("Payload written to test_payload.json")
