#!/usr/bin/env python3
"""Quick test for new P0 endpoints (network, correlation, pathway)."""
import httpx

BASE = "http://localhost:8000/api/v1"
client = httpx.Client(timeout=120.0)

resp = client.get(f"{BASE}/sessions")
data = resp.json()
sessions = data.get('sessions', [])
if not sessions:
    print("No sessions found. Run end_to_end_test.py first.")
    exit(1)

sid = sessions[-1]['id']
print(f"Using session: {sid}")

# Test Network Analysis
print("\n--- Network Analysis ---")
r = client.post(f"{BASE}/sessions/{sid}/analyze/network", json={})
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        print(f"Network stats: {list(rd.get('network_stats', {}).keys())}")
        print(f"Nodes: {len(rd.get('nodes', []))}, Edges: {len(rd.get('edges', []))}")
        print(f"Communities: {len(rd.get('communities', []))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])

# Test Correlation Analysis
print("\n--- Correlation Analysis ---")
r = client.post(f"{BASE}/sessions/{sid}/analyze/correlation", json={"target": "feature"})
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        fc = rd.get("feature_correlation", {})
        print(f"Significant pairs: {len(fc.get('significant_pairs', []))}")
        print(f"Has heatmap plot: {bool(fc.get('heatmap_plot'))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])

# Test Pathway Analysis
print("\n--- Pathway Analysis ---")
r = client.post(f"{BASE}/sessions/{sid}/analyze/pathway", json={})
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        ep = rd.get("enriched_pathways", [])
        print(f"Enriched pathways: {len(ep)}")
        print(f"Has bar plot: {bool(rd.get('bar_plot'))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])

print("\nAll P0 endpoint tests complete.")
