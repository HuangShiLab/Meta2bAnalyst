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

# Test phylogenetic analysis
print("\n--- Phylogenetic Analysis (UniFrac + Faith's PD + NMDS) ---")
r = client.post(
    f"{BASE}/sessions/{sid}/analyze/phylogenetic",
    json={"group_column": "group"}
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"Job type: {d['job_type']}, Status: {d['status']}")
    if d.get("result_data"):
        rd = d["result_data"]
        print(f"Method: {rd.get('method')}")
        print(f"Has UniFrac PCoA: {bool(rd.get('plots', {}).get('unifrac_pcoa'))}")
        print(f"Has NMDS plot: {bool(rd.get('plots', {}).get('nmds_plot'))}")
        print(f"Has Faith's PD plot: {bool(rd.get('plots', {}).get('faith_pd_plot'))}")
        nmds = rd.get('nmds', {})
        print(f"NMDS stress: {nmds.get('stress', 'N/A')}")
        permanova = rd.get('permanova', {})
        print(f"PERMANOVA p-value: {permanova.get('p_value', 'N/A')}")
    else:
        print("No result_data")
else:
    print(r.text[:500])
