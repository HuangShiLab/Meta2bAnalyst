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

# Test source tracking
print("\n--- Source Tracking (FEAST-style) ---")
r = client.post(
    f"{BASE}/sessions/{sid}/analyze/source-tracking",
    json={}
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        if 'error' in rd:
            print(f"Error: {rd['error']}")
        else:
            print(f"Method: {rd.get('method')}")
            print(f"N sink samples: {rd.get('n_sink_samples')}")
            print(f"N source samples: {rd.get('n_source_samples')}")
            summary = rd.get('summary', {})
            print(f"Mean fit quality: {summary.get('mean_fit_quality')}")
            print(f"Source types: {summary.get('source_types')}")
            print(f"Has proportions plot: {bool(rd.get('plots', {}).get('source_proportions'))}")
            print(f"Has heatmap: {bool(rd.get('plots', {}).get('source_heatmap'))}")
            print(f"Has pie chart: {bool(rd.get('plots', {}).get('source_pie'))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])
