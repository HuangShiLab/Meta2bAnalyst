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

# Test advanced dimred
print("\n--- Advanced Dimred (t-SNE + UMAP + MaAsLin3) ---")
r = client.post(
    f"{BASE}/sessions/{sid}/analyze/advanced-dimred",
    json={"group_column": "group", "fixed_effects": ["group"]}
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        print(f"Method: {rd.get('method')}")
        print(f"t-SNE samples: {len(rd.get('tsne', []))}")
        print(f"UMAP samples: {len(rd.get('umap', []))}")
        print(f"MaAsLin3 associations: {len(rd.get('maaslin', []))}")
        print(f"Has t-SNE plot: {bool(rd.get('plots', {}).get('tsne_plot'))}")
        print(f"Has UMAP plot: {bool(rd.get('plots', {}).get('umap_plot'))}")
        print(f"Has MaAsLin3 volcano: {bool(rd.get('plots', {}).get('maaslin_volcano'))}")
    else:
        print("No result_data")
else:
    print(r.text[:500])
