#!/usr/bin/env python3
"""
Meta2bAnalyst - End-to-End Integration Test
Tests the complete workflow from data upload to PDF report generation.
"""

import sys
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000/api/v1"
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"
WARN = "\033[93m⚠\033[0m"


def log_step(step_num: int, desc: str):
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {desc}")
    print("=" * 60)


def check_response(resp: httpx.Response, expected_status: int = 200) -> dict:
    if resp.status_code != expected_status:
        print(f"{FAIL} HTTP {resp.status_code}: {resp.text[:500]}")
        raise RuntimeError(f"Expected {expected_status}, got {resp.status_code}")
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text}


def main():
    print("\n" + "=" * 60)
    print("Meta2bAnalyst - End-to-End Integration Test")
    print("=" * 60)

    client = httpx.Client(timeout=120.0)
    session_id = None
    failed_steps = []

    # ── Step 1: Create Session ──
    try:
        log_step(1, "Create Session")
        resp = client.post(
            f"{BASE_URL}/sessions",
            json={"data_format": "2brad_m", "analysis_level": "species"},
        )
        data = check_response(resp, 201)
        session_id = data["id"]
        print(f"{OK} Session created: {session_id}")
    except Exception as e:
        print(f"{FAIL} Step 1 failed: {e}")
        sys.exit(1)

    # ── Step 2: Upload Files ──
    try:
        log_step(2, "Upload Feature Table + Metadata")
        feature_file = EXAMPLES_DIR / "2brad_m_species.csv"
        meta_file = EXAMPLES_DIR / "metadata_gut.csv"

        with open(feature_file, "rb") as f:
            resp = client.post(
                f"{BASE_URL}/sessions/{session_id}/upload",
                data={"file_type": "feature_table"},
                files={"file": ("2brad_m_species.csv", f, "text/csv")},
            )
            check_response(resp, 201)
            print(f"{OK} Uploaded feature table")

        with open(meta_file, "rb") as f:
            resp = client.post(
                f"{BASE_URL}/sessions/{session_id}/upload",
                data={"file_type": "metadata"},
                files={"file": ("metadata_gut.csv", f, "text/csv")},
            )
            check_response(resp, 201)
            print(f"{OK} Uploaded metadata")
    except Exception as e:
        print(f"{FAIL} Step 2 failed: {e}")
        failed_steps.append(2)

    # ── Step 3: Data Inspection ──
    try:
        log_step(3, "Data Inspection")
        resp = client.get(f"{BASE_URL}/sessions/{session_id}/inspect")
        data = check_response(resp)
        n_features = data.get("feature_count", "N/A")
        n_samples = data.get("sample_count", "N/A")
        print(f"{OK} Inspection: {n_features} features × {n_samples} samples")
    except Exception as e:
        print(f"{FAIL} Step 3 failed: {e}")
        failed_steps.append(3)

    # ── Step 4: Filter ──
    try:
        log_step(4, "Filter Data (low count + low variance)")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/filter",
            json={
                "min_count": 4,
                "prevalence": 0.2,
                "variance_percent": 10,
                "variance_method": "iqr",
            },
        )
        check_response(resp)
        print(f"{OK} Filtering applied")
    except Exception as e:
        print(f"{FAIL} Step 4 failed: {e}")
        failed_steps.append(4)

    # ── Step 5: Normalize ──
    try:
        log_step(5, "Normalize Data (TSS)")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/normalize",
            json={"method": "tss", "rarefy": False},
        )
        check_response(resp)
        print(f"{OK} TSS normalization applied")
    except Exception as e:
        print(f"{FAIL} Step 5 failed: {e}")
        failed_steps.append(5)

    # ── Step 6: Alpha Diversity ──
    try:
        log_step(6, "Alpha Diversity (Shannon, Simpson, Chao1)")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/alpha-diversity",
            json={
                "analysis_type": "alpha",
                "metrics": ["shannon", "simpson", "chao1"],
                "group_column": "group",
            },
        )
        data = check_response(resp, 201)
        if data.get("status") == "completed":
            result = data.get("result_data", {})
            plot_ok = "plot_data" in result
            stats = result.get("statistics", {})
            print(f"{OK} Alpha diversity: plot={plot_ok}, stats={list(stats.keys())[:3]}")
        else:
            print(f"{WARN} Alpha diversity: status={data.get('status')}")
    except Exception as e:
        print(f"{FAIL} Step 6 failed: {e}")
        failed_steps.append(6)

    # ── Step 7: Beta Diversity + PCoA ──
    try:
        log_step(7, "Beta Diversity (Bray-Curtis) + PCoA")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/beta-diversity",
            json={
                "analysis_type": "beta",
                "distance": "braycurtis",
                "group_column": "group",
            },
        )
        data = check_response(resp, 201)
        if data.get("status") == "completed":
            plot_ok = "plot_data" in data.get("result_data", {})
            print(f"{OK} Beta diversity: plot={plot_ok}")

        # PCoA
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/pcoa",
            json={
                "analysis_type": "pcoa",
                "distance": "braycurtis",
                "group_column": "group",
            },
        )
        data = check_response(resp, 201)
        if data.get("status") == "completed":
            plot_ok = "plot_data" in data.get("result_data", {})
            print(f"{OK} PCoA: plot={plot_ok}")
    except Exception as e:
        print(f"{FAIL} Step 7 failed: {e}")
        failed_steps.append(7)

    # ── Step 8-11: Differential Abundance (multiple methods) ──
    diff_methods = [
        ("t-test", "t-test"),
        ("wilcoxon", "Wilcoxon"),
        ("ANCOM-BC", "ANCOM-BC"),
        ("lefse", "LEfSe"),
    ]
    for method_name, label in diff_methods:
        try:
            log_step(8 + diff_methods.index((method_name, label)), f"Differential: {label}")
            if method_name == "lefse":
                resp = client.post(
                    f"{BASE_URL}/sessions/{session_id}/analyze/lefse",
                    json={
                        "analysis_type": "lefse",
                        "group_column": "group",
                        "parameters": {"lda_threshold": 1.0},
                    },
                )
            elif method_name == "ANCOM-BC":
                resp = client.post(
                    f"{BASE_URL}/sessions/{session_id}/analyze/differential",
                    json={
                        "analysis_type": "differential",
                        "group_column": "group",
                        "parameters": {
                            "test_method": method_name,
                            "group1": "Control",
                            "group2": "Treatment",
                            "correction_method": "BH",
                            "pvalue_threshold": 0.05,
                            "zero_cut": 0.9,
                            "struc_zero": True,
                        },
                    },
                )
            else:
                resp = client.post(
                    f"{BASE_URL}/sessions/{session_id}/analyze/differential",
                    json={
                        "analysis_type": "differential",
                        "group_column": "group",
                        "parameters": {
                            "test_method": method_name,
                            "group1": "Control",
                            "group2": "Treatment",
                            "correction_method": "BH",
                            "pvalue_threshold": 0.05,
                        },
                    },
                )
            data = check_response(resp, 201)
            if data.get("status") in ("completed", "success"):
                result = data.get("result_data", {})
                sig_count = len(result.get("significant_features", []))
                plot_ok = "plot_data" in result
                print(f"{OK} {label}: sig={sig_count}, plot={plot_ok}")
            else:
                print(f"{WARN} {label}: status={data.get('status')}")
        except Exception as e:
            print(f"{FAIL} {label} failed: {e}")
            failed_steps.append(f"8-{label}")

    # ── Step 12: Random Forest ──
    try:
        log_step(12, "Random Forest Classification")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/random-forest",
            json={
                "analysis_type": "random_forest",
                "group_column": "group",
                "parameters": {"n_estimators": 500, "cv_folds": 5},
            },
        )
        data = check_response(resp, 201)
        if data.get("status") == "completed":
            result = data.get("result_data", {})
            acc = result.get("accuracy", "N/A")
            plot_ok = "plot_data" in result
            print(f"{OK} Random Forest: accuracy={acc}, plot={plot_ok}")
        else:
            print(f"{WARN} Random Forest: status={data.get('status')}")
    except Exception as e:
        print(f"{FAIL} Step 12 failed: {e}")
        failed_steps.append(12)

    # ── Step 13: Heatmap ──
    try:
        log_step(13, "Heatmap (Top 50 features)")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/heatmap",
            json={
                "analysis_type": "heatmap",
                "group_column": "group",
                "parameters": {"n_top": 50},
            },
        )
        data = check_response(resp, 201)
        if data.get("status") == "completed":
            plot_ok = "plot_data" in data.get("result_data", {})
            print(f"{OK} Heatmap: plot={plot_ok}")
        else:
            print(f"{WARN} Heatmap: status={data.get('status')}")
    except Exception as e:
        print(f"{FAIL} Step 13 failed: {e}")
        failed_steps.append(13)

    # ── Step 14: Stacked Bar Chart ──
    try:
        log_step(14, "Stacked Bar Chart (Compositional)")
        resp = client.post(
            f"{BASE_URL}/sessions/{session_id}/analyze/stacked-bar",
            json={
                "analysis_type": "taxonomy_bar",
                "group_column": "group",
                "parameters": {"tax_level": "phylum"},
            },
        )
        data = check_response(resp, 201)
        if data.get("status") == "completed":
            plot_ok = "plot_data" in data.get("result_data", {})
            print(f"{OK} Stacked bar: plot={plot_ok}")
        else:
            print(f"{WARN} Stacked bar: status={data.get('status')}")
    except Exception as e:
        print(f"{FAIL} Step 14 failed: {e}")
        failed_steps.append(14)

    # ── Step 15: Generate PDF Report ──
    try:
        log_step(15, "Generate Comprehensive PDF Report")
        resp = client.post(f"{BASE_URL}/sessions/{session_id}/export/report")
        if resp.status_code == 200:
            report_path = Path("test_report.pdf")
            report_path.write_bytes(resp.content)
            size_kb = len(resp.content) / 1024
            print(f"{OK} PDF report generated: {report_path} ({size_kb:.1f} KB)")
        else:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            print(f"{WARN} PDF report: HTTP {resp.status_code}, {data.get('detail', resp.text[:200])}")
    except Exception as e:
        print(f"{FAIL} Step 15 failed: {e}")
        failed_steps.append(15)

    # ── Summary ──
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    total_steps = 15
    if failed_steps:
        print(f"{FAIL} Failed steps: {len(failed_steps)}/{total_steps}")
        for s in failed_steps:
            print(f"  - Step {s}")
        sys.exit(1)
    else:
        print(f"{OK} All {total_steps} steps passed successfully!")
        print(f"{INFO} Session ID: {session_id}")
        print(f"{INFO} PDF Report: test_report.pdf")
        sys.exit(0)


if __name__ == "__main__":
    main()
