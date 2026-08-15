import httpx

BASE = "http://localhost:8000/api/v1"
client = httpx.Client(timeout=120.0)

# Get latest session
resp = client.get(f"{BASE}/sessions")
data = resp.json()
sessions = data.get('sessions', [])
if not sessions:
    print("No sessions found")
    exit(1)
sid = sessions[-1]['id']
print(f"Using session: {sid}")

# Test functional prediction
print("\n--- Functional Prediction (PICRUSt2) ---")
r = client.post(
    f"{BASE}/sessions/{sid}/analyze/functional-prediction",
    json={"group_column": "group"}
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        print(f"Method: {rd.get('method')}")
        qm = rd.get('quality_metrics', {})
        print(f"Coverage: {qm.get('coverage')}, NSTI: {qm.get('mean_nsti')}")
        print(f"KOs predicted: {qm.get('n_ko_predicted')}")
        print(f"Has KO heatmap: {bool(rd.get('plots', {}).get('ko_heatmap'))}")
        print(f"Has pathway bar: {bool(rd.get('plots', {}).get('pathway_bar'))}")
        print(f"Has pathway PCA: {bool(rd.get('plots', {}).get('pathway_pca'))}")
        diff = rd.get('differential', {})
        print(f"Significant pathways: {diff.get('n_significant', 0)}")
    else:
        print("No result_data")
else:
    print(r.text[:500])
