import httpx

BASE = "http://localhost:8000/api/v1"
client = httpx.Client(timeout=120.0)

resp = client.get(f"{BASE}/sessions")
data = resp.json()
sessions = data.get('sessions', [])
if not sessions:
    print("No sessions found")
    exit(1)
sid = sessions[-1]['id']
print(f"Using session: {sid}")

# Test cross-omics
print("\n--- Cross-omics Analysis (Procrustes + Mantel) ---")
r = client.post(
    f"{BASE}/sessions/{sid}/analyze/cross-omics",
    json={"group_column": "group"}
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        procrustes = rd.get('procrustes', {})
        print(f"Procrustes m2: {procrustes.get('m2')}")
        print(f"Procrustes normalized_m2: {procrustes.get('normalized_m2')}")
        mantel = rd.get('mantel', {})
        print(f"Mantel correlation: {mantel.get('correlation')}")
        print(f"Mantel p-value: {mantel.get('p_value')}")
        print(f"Has Procrustes plot: {bool(rd.get('plots', {}).get('procrustes_plot'))}")
        print(f"Has Mantel scatter: {bool(rd.get('plots', {}).get('mantel_scatter'))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])
