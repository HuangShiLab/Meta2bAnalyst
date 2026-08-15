#!/usr/bin/env python3
"""Run demo analysis on MetaPhlAn example data and generate report."""
import json
import os
import sys
import time

import requests

BASE_URL = "http://localhost:8000/api/v1"
EXAMPLES_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/examples"
RESULTS_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst"


def main():
    # 1. Create session
    print("=" * 60)
    print("Step 1: Creating session...")
    print("=" * 60)
    resp = requests.post(
        f"{BASE_URL}/sessions",
        json={
            "name": "MetaPhlAn Demo Analysis",
            "data_format": "tsv",
            "description": "Demonstration of Meta2bAnalyst with MetaPhlAn data",
        },
    )
    resp.raise_for_status()
    session = resp.json()
    session_id = session["id"]
    print(f"✅ Session created: {session_id}")

    # 2. Upload files
    print("\n" + "=" * 60)
    print("Step 2: Uploading example data...")
    print("=" * 60)
    files_to_upload = [
        ("metaphlan_abundance.tsv", "microbiome"),
        ("metaphlan_metadata.tsv", "metadata"),
    ]

    for filename, file_type in files_to_upload:
        filepath = os.path.join(EXAMPLES_DIR, filename)
        with open(filepath, "rb") as f:
            upload_resp = requests.post(
                f"{BASE_URL}/sessions/{session_id}/upload",
                files={"file": (filename, f, "text/tab-separated-values")},
                data={"file_type": file_type},
            )
        if upload_resp.status_code in (200, 201):
            print(f"✅ Uploaded {filename}")
        else:
            print(f"❌ Failed {filename}: {upload_resp.status_code}")
            print(upload_resp.text[:300])

    # 3. Run analyses
    print("\n" + "=" * 60)
    print("Step 3: Running analyses...")
    print("=" * 60)
    
    # For existing endpoints that use AnalysisRequest schema
    analyses_existing = [
        ("alpha-diversity", {"analysis_type": "alpha", "indices": ["shannon", "simpson"], "group_column": "Visit"}),
        ("beta-diversity", {"analysis_type": "beta", "parameters": {"metric": "braycurtis"}, "group_column": "Visit"}),
        ("pcoa", {"analysis_type": "pcoa", "parameters": {"metric": "braycurtis"}, "group_column": "Visit"}),
        ("permanova", {"analysis_type": "permanova", "parameters": {"metric": "braycurtis"}, "group_column": "Visit"}),
    ]
    
    # For new endpoints with dedicated request schemas
    analyses_new = [
        ("rarefaction", {"metrics": ["richness", "shannon"], "group_column": "Visit", "steps": 20, "iterations": 10}),
        ("taxonomy-bar", {"tax_level": "genus", "top_n": 15, "group_column": "Visit"}),
        ("core-microbiome", {"group_column": "Visit", "prevalence_threshold": 0.5, "abundance_threshold": 0.01}),
    ]

    results = {}
    
    for analysis_type, params in analyses_existing:
        print(f"\n▶ Running {analysis_type}...")
        resp = requests.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/{analysis_type}",
            json={"analysis_type": params["analysis_type"], "parameters": params, "group_column": params.get("group_column")},
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            results[analysis_type] = data
            print(f"  ✅ Success: job_id={data.get('job_id')}")
            stats = data.get("result_data", {}).get("statistics")
            if stats:
                print(f"  📊 Stats: {json.dumps(stats, indent=2)[:400]}")
        else:
            print(f"  ❌ Failed: {resp.status_code}")
            print(f"  {resp.text[:300]}")
    
    for analysis_type, params in analyses_new:
        print(f"\n▶ Running {analysis_type}...")
        resp = requests.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/{analysis_type}",
            json=params,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            results[analysis_type] = data
            print(f"  ✅ Success: job_id={data.get('job_id')}")
            stats = data.get("result_data", {}).get("statistics")
            if stats:
                print(f"  📊 Stats: {json.dumps(stats, indent=2)[:400]}")
        else:
            print(f"  ❌ Failed: {resp.status_code}")
            print(f"  {resp.text[:300]}")

    # 4. Save results
    print("\n" + "=" * 60)
    print("Step 4: Saving results...")
    print("=" * 60)
    results_path = os.path.join(RESULTS_DIR, "demo_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"✅ Results saved to: {results_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS SUMMARY")
    print("=" * 60)
    for name, data in results.items():
        stats = data.get("result_data", {}).get("statistics", {})
        print(f"\n📈 {name.upper()}")
        for k, v in list(stats.items())[:5]:
            print(f"   {k}: {v}")
    
    return results


if __name__ == "__main__":
    main()
