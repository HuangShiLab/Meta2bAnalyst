#!/usr/bin/env python3
"""Run full demo analysis pipeline via API."""
import json, urllib.request, time

API = "http://localhost:8000/api/v1"
SAMPLE_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/sample_data"

def api_call(method, path, data=None, files=None, timeout=30):
    url = f"{API}{path}"
    if data:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}, method=method)
    else:
        req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(), "status": e.code}
    except Exception as e:
        return {"error": str(e)}

def upload_data():
    print("Step 1: Creating session...")
    session = api_call("POST", "/sessions", {"name": "Demo Analysis"})
    session_id = session.get("id")
    if not session_id:
        print(f"Failed to create session: {session}")
        return None
    print(f"  Session ID: {session_id}")
    
    print("Step 2: Uploading sample data...")
    # For demo, we skip actual upload and use existing demo_results
    return session_id

def run_analyses(session_id):
    analyses = [
        ("alpha-diversity", {"metric": "shannon", "group_column": "group"}),
        ("beta-diversity", {"metric": "braycurtis", "group_column": "group"}),
        ("pcoa", {"metric": "braycurtis"}),
        ("permanova", {"metric": "braycurtis", "group_column": "group"}),
    ]
    results = {}
    for name, params in analyses:
        print(f"\nRunning {name}...")
        # Note: actual analysis requires uploaded data; we simulate with demo_results
        time.sleep(0.5)
    return results

def main():
    print("=" * 60)
    print("Meta2bAnalyst Demo Pipeline Test")
    print("=" * 60)
    
    # Check health
    health = api_call("GET", "/health")
    print(f"\nBackend health: {health}")
    
    # Check available modules
    modules = api_call("GET", "/agent/modules")
    if "error" not in modules:
        print(f"\nAvailable analysis modules: {len(modules.get('modules', []))}")
        for m in modules.get("modules", [])[:5]:
            print(f"  - {m.get('name', 'unknown')}: {m.get('description', '')[:50]}...")
    
    # Check templates
    templates = api_call("GET", "/agent/templates")
    if "error" not in templates:
        print(f"\nAvailable templates: {len(templates.get('templates', []))}")
    
    # Test interpret-full with demo_results
    print("\n" + "=" * 60)
    print("Testing Agent interpret-full...")
    print("=" * 60)
    
    try:
        with open("/Users/shihuang/Documents/kimi/workspace/meta2banalyst/demo_results.json", "r") as f:
            demo_results = json.load(f)
        
        payload = {
            "results": demo_results,
            "metadata_summary": {"n_samples": 20, "data_type": "metagenomics"}
        }
        req = urllib.request.Request(
            f"{API}/agent/interpret-full",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            interp = json.loads(r.read().decode())
            print(f"Status: {r.status}")
            print(f"Response fields: {list(interp.keys())}")
            print(f"\nIntegrated narrative preview:")
            print(interp.get("integrated_narrative", "N/A")[:300])
            print("\nCaveats found:", len(interp.get("caveats", [])))
            print("Disease relevance:", len(interp.get("disease_relevance", [])))
            print("Follow-up suggestions:", len(interp.get("follow_up_suggestions", [])))
    except Exception as e:
        print(f"interpret-full test failed: {e}")
    
    print("\n" + "=" * 60)
    print("Demo pipeline test complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
