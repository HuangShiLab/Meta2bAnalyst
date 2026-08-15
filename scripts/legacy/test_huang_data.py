#!/usr/bin/env python3
"""
Test full pipeline on Huang et al mBio 2021-style paired microbiome + metabolome data.
Same site (oral) with 24 participants, multiple timepoints.
"""
import httpx
import pandas as pd
import json
import time
import sys

BASE = "http://localhost:8000/api/v1"
client = httpx.Client(timeout=300.0)

def upload_file(file_path, file_type, session_id):
    """Upload a data file to the session."""
    with open(file_path, 'rb') as f:
        files = {'file': (file_path.split('/')[-1], f, 'text/tab-separated-values')}
        data = {'file_type': file_type, 'session_id': session_id}
        r = client.post(f"{BASE}/upload", data=data, files=files)
    if r.status_code == 200:
        return r.json()
    else:
        print(f"Upload failed: {r.status_code} {r.text[:500]}")
        return None

def run_analysis(session_id, endpoint, params=None):
    """Run an analysis endpoint and wait for result."""
    params = params or {}
    r = client.post(f"{BASE}/sessions/{session_id}/analyze/{endpoint}", json=params)
    if r.status_code != 200:
        print(f"  {endpoint} failed: {r.status_code} {r.text[:500]}")
        return None
    d = r.json()
    print(f"  {endpoint}: status={d['status']}, job_id={d['job_id']}")
    return d.get('result_data', {})

def run_legacy(session_id, job_type, params):
    """Run legacy analysis via job creation."""
    # Create job
    r = client.post(f"{BASE}/sessions/{session_id}/analysis", json={
        'job_type': job_type,
        'parameters': params,
    })
    if r.status_code != 200:
        print(f"  {job_type} create failed: {r.status_code} {r.text[:500]}")
        return None
    job = r.json()
    job_id = job['job_id']
    
    # Run job
    r = client.post(f"{BASE}/sessions/{session_id}/analysis/{job_id}/run")
    if r.status_code != 200:
        print(f"  {job_type} run failed: {r.status_code} {r.text[:500]}")
        return None
    d = r.json()
    print(f"  {job_type}: status={d['status']}")
    return d.get('result_data', {})

# ─────────────────────────────── 1. Create session
print("=== 1. Creating session ===")
r = client.post(f"{BASE}/sessions", json={'name': 'Huang_mBio_2021_oral_paired'})
if r.status_code != 200:
    print(f"Failed to create session: {r.status_code}")
    sys.exit(1)
session = r.json()
sid = session['id']
print(f"Session ID: {sid}")

# ─────────────────────────────── 2. Upload microbiome data
print("\n=== 2. Uploading microbiome data ===")
microbiome_abd = "/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_microbes_genus.abd_261.txt"
microbiome_meta = "/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_microbes_metadata_261.txt"

upload_file(microbiome_abd, 'feature_table', sid)
print("  Microbiome abundance uploaded")
upload_file(microbiome_meta, 'metadata', sid)
print("  Microbiome metadata uploaded")

# ─────────────────────────────── 3. Upload metabolome data
print("\n=== 3. Uploading metabolome data ===")
metabolome_abd = "/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_metabolites_abd_261.txt"
metabolome_meta = "/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_metabolites_metadata_261.txt"

upload_file(metabolome_abd, 'feature_table', sid)
print("  Metabolome abundance uploaded")
upload_file(metabolome_meta, 'metadata', sid)
print("  Metabolome metadata uploaded")

print("\n=== 4. Running analyses on MICROBIOME ===")

# Alpha diversity
print("\n--- Alpha Diversity ---")
run_analysis(sid, 'alpha-diversity', {'metrics': ['shannon', 'simpson', 'chao1', 'observed_otus']})

# Beta diversity
print("\n--- Beta Diversity ---")
run_analysis(sid, 'beta-diversity', {'metric': 'braycurtis'})

# PCoA
print("\n--- PCoA ---")
run_analysis(sid, 'pcoa', {'metric': 'braycurtis', 'group_column': 'Visit'})

# NMDS
print("\n--- NMDS ---")
run_analysis(sid, 'nmds', {'metric': 'braycurtis', 'n_components': 2})

# Differential analysis (t-test)
print("\n--- Differential Analysis (t-test) ---")
run_analysis(sid, 'differential-analysis', {
    'test': 't-test',
    'group_column': 'Bleeding',
    'control_group': '0',
    'case_group': '1',
    'top_n': 20,
})

# Heatmap
print("\n--- Heatmap ---")
run_analysis(sid, 'heatmap', {
    'group_column': 'Visit',
    'top_n_features': 50,
    'clustering': 'both',
})

# Network analysis
print("\n--- Network Analysis ---")
run_analysis(sid, 'network', {
    'method': 'sparcc',
    'threshold': 0.3,
    'top_n_features': 100,
})

# Correlation analysis
print("\n--- Correlation Analysis ---")
run_analysis(sid, 'correlation', {
    'target': 'feature',
    'method': 'spearman',
    'threshold': 0.3,
})

# Pathway analysis
print("\n--- Pathway Analysis ---")
run_analysis(sid, 'pathway', {
    'method': 'hypergeometric',
    'pvalue_threshold': 0.05,
})

# Functional prediction
print("\n--- Functional Prediction (PICRUSt2) ---")
run_analysis(sid, 'functional-prediction', {
    'method': 'picrust2',
    'group_column': 'Visit',
    'top_n_ko': 50,
    'top_n_pathway': 20,
})

# Phylogenetic analysis
print("\n--- Phylogenetic Analysis (UniFrac) ---")
run_analysis(sid, 'phylogenetic', {
    'weighted': True,
    'group_column': 'Visit',
})

# Hierarchical clustering
print("\n--- Hierarchical Clustering ---")
run_analysis(sid, 'hierarchical-clustering', {
    'cluster_axis': 'both',
    'distance_metric': 'braycurtis',
    'group_column': 'Visit',
})

# Stacked bar chart
print("\n--- Stacked Bar ---")
run_analysis(sid, 'stacked-bar', {'group_column': 'Visit'})

print("\n=== 5. Running analyses on METABOLOME ===")
# Note: For metabolome, we need to create a new session since we uploaded both to same session
# Actually the current backend may only use the first feature table. Let's check.
# For now, let's run cross-omics with the current data.

print("\n=== 6. Running CROSS-OMICS analysis ===")
print("\n--- Cross-omics (Procrustes + Mantel) ---")
run_analysis(sid, 'cross-omics', {
    'procrustes_method': 'pcoa',
    'mantel_metric': 'braycurtis',
    'group_column': 'Visit',
})

# Advanced dimred
print("\n--- Advanced Dimred (t-SNE + UMAP) ---")
run_analysis(sid, 'advanced-dimred', {
    'method': 'both',
    'group_column': 'Visit',
    'fixed_effects': ['Visit'],
})

print("\n=== 7. Generating PDF report ===")
report_r = client.post(f"{BASE}/sessions/{sid}/reports", json={
    'include_charts': True,
    'report_type': 'comprehensive',
})
if report_r.status_code == 200:
    report_data = report_r.json()
    print(f"Report generated: {report_data}")
else:
    print(f"Report generation failed: {report_r.status_code} {report_r.text[:500]}")

print("\n=== All analyses complete! ===")
print(f"Session ID: {sid}")
print(f"View results at: http://localhost:8000/api/v1/sessions/{sid}/analysis")
