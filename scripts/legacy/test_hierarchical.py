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

# Test hierarchical clustering
print("\n--- Hierarchical Clustering + Heat Tree ---")
r = client.post(
    f"{BASE}/sessions/{sid}/analyze/hierarchical-clustering",
    json={"group_column": "group"}
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        print(f"Cluster axis: {rd.get('cluster_axis')}")
        print(f"Distance metric: {rd.get('distance_metric')}")
        print(f"Linkage method: {rd.get('linkage_method')}")
        print(f"N clusters: {rd.get('n_clusters')}")
        print(f"Sample clusters: {len(rd.get('sample_clusters', []))}")
        print(f"Feature clusters: {len(rd.get('feature_clusters', []))}")
        print(f"Has heat tree: {bool(rd.get('plots', {}).get('heat_tree'))}")
        print(f"Has sample dendrogram: {bool(rd.get('plots', {}).get('sample_dendrogram'))}")
        print(f"Has feature dendrogram: {bool(rd.get('plots', {}).get('feature_dendrogram'))}")
        print(f"Has silhouette plot: {bool(rd.get('plots', {}).get('silhouette_plot'))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])
