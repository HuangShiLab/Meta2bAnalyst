#!/usr/bin/env python3
"""Start server, run demo analysis, generate PDF report."""
import json
import os
import signal
import subprocess
import sys
import time

import requests

BASE_URL = "http://localhost:8000/api/v1"
EXAMPLES_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend/examples"
RESULTS_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst"
SERVER_LOG = "/tmp/meta2b_server_demo.log"


def start_server():
    """Start uvicorn server in a new process group."""
    env = os.environ.copy()
    env["PYTHONPATH"] = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend"
    
    # Use subprocess with new session to avoid SIGHUP
    proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        cwd="/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend",
        stdout=open(SERVER_LOG, "w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )
    print(f"Server PID: {proc.pid}")
    
    # Wait for server to be ready
    for i in range(30):
        try:
            resp = requests.get("http://localhost:8000/docs", timeout=2)
            if resp.status_code == 200:
                print("✅ Server is ready")
                return proc
        except Exception:
            pass
        time.sleep(1)
    
    print("❌ Server failed to start")
    print(open(SERVER_LOG).read()[-500:])
    proc.terminate()
    return None


def stop_server(proc):
    """Stop the server."""
    if proc:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
        print("✅ Server stopped")


def run_analyses(session_id):
    """Run all demo analyses."""
    print("\n" + "=" * 60)
    print("Running analyses...")
    print("=" * 60)
    
    analyses = [
        ("alpha-diversity", {"analysis_type": "alpha_diversity", "parameters": {"indices": ["shannon", "simpson"]}, "group_column": "Visit"}),
        ("beta-diversity", {"analysis_type": "beta_diversity", "parameters": {"metric": "braycurtis"}, "group_column": "Visit"}),
        ("pcoa", {"analysis_type": "pcoa", "parameters": {"metric": "braycurtis"}, "group_column": "Visit"}),
        ("permanova", {"analysis_type": "permanova", "parameters": {"metric": "braycurtis"}, "group_column": "Visit"}),
        ("rarefaction", {"metrics": ["richness", "shannon"], "group_column": "Visit", "steps": 20, "iterations": 10}),
        ("taxonomy-bar", {"tax_level": "genus", "top_n": 15, "group_column": "Visit"}),
        ("core-microbiome", {"group_column": "Visit", "prevalence_threshold": 0.5, "abundance_threshold": 0.01}),
    ]
    
    results = {}
    for analysis_type, params in analyses:
        print(f"\n▶ Running {analysis_type}...")
        try:
            resp = requests.post(
                f"{BASE_URL}/sessions/{session_id}/analyze/{analysis_type}",
                json=params,
                timeout=60,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                results[analysis_type] = data
                print(f"  ✅ Success: job_id={data.get('job_id')}")
            else:
                print(f"  ❌ Failed: {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            print(f"  ❌ Exception: {e}")
    
    return results


def generate_pdf_report(results):
    """Generate a PDF report from analysis results."""
    print("\n" + "=" * 60)
    print("Generating PDF report...")
    print("=" * 60)
    
    report_lines = []
    report_lines.append("# Meta2bAnalyst Demo Analysis Report")
    report_lines.append("")
    report_lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}")
    report_lines.append("")
    report_lines.append("## Overview")
    report_lines.append("")
    report_lines.append("This report demonstrates the Meta2bAnalyst platform's analysis capabilities using MetaPhlAn example data (20 samples × 19 species).")
    report_lines.append("")
    
    for name, data in results.items():
        report_lines.append(f"## {name.replace('-', ' ').title()}")
        report_lines.append("")
        
        stats = data.get("result_data", {}).get("statistics", {})
        if stats:
            report_lines.append("### Statistics")
            report_lines.append("")
            for k, v in list(stats.items())[:10]:
                if isinstance(v, (int, float, str)):
                    report_lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
            report_lines.append("")
        
        plot_data = data.get("result_data", {}).get("plot_data")
        if plot_data and plot_data.get("data"):
            report_lines.append(f"- Plot generated with {len(plot_data['data'])} trace(s)")
            if plot_data.get("layout", {}).get("title"):
                report_lines.append(f"- Title: {plot_data['layout']['title']}")
        report_lines.append("")
    
    report_md = "\n".join(report_lines)
    
    # Save markdown
    md_path = os.path.join(RESULTS_DIR, "demo_report.md")
    with open(md_path, "w") as f:
        f.write(report_md)
    print(f"✅ Markdown report saved: {md_path}")
    
    # Try to convert to PDF using reportlab
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_CENTER
        
        pdf_path = os.path.join(RESULTS_DIR, "demo_report.pdf")
        doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                                rightMargin=72, leftMargin=72,
                                topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Meta2bAnalyst Demo Report", title_style))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        story.append(Spacer(1, 0.3 * inch))
        
        # Content
        for line in report_lines:
            if line.startswith("# "):
                story.append(Paragraph(line[2:], styles['Title']))
            elif line.startswith("## "):
                story.append(Paragraph(line[3:], styles['Heading2']))
            elif line.startswith("### "):
                story.append(Paragraph(line[4:], styles['Heading3']))
            elif line.startswith("**") and line.endswith("**"):
                story.append(Paragraph(line, styles['Normal']))
            elif line.startswith("- "):
                story.append(Paragraph(f"&bull; {line[2:]}", styles['Normal']))
            elif line.strip():
                story.append(Paragraph(line, styles['Normal']))
            story.append(Spacer(1, 0.1 * inch))
        
        doc.build(story)
        print(f"✅ PDF report saved: {pdf_path}")
        return pdf_path
    except Exception as e:
        print(f"⚠️ PDF generation failed: {e}")
        return md_path


def main():
    # Start server
    print("=" * 60)
    print("Starting server...")
    print("=" * 60)
    proc = start_server()
    if not proc:
        return
    
    try:
        # Create session
        print("\n" + "=" * 60)
        print("Creating session...")
        print("=" * 60)
        resp = requests.post(f"{BASE_URL}/sessions", json={
            "name": "MetaPhlAn Demo",
            "data_format": "tsv",
            "description": "Demo analysis",
        })
        session_id = resp.json()["id"]
        print(f"✅ Session: {session_id}")
        
        # Upload files
        print("\n" + "=" * 60)
        print("Uploading data...")
        print("=" * 60)
        for filename, file_type in [("metaphlan_abundance.tsv", "microbiome"), ("metaphlan_metadata.tsv", "metadata")]:
            with open(os.path.join(EXAMPLES_DIR, filename), "rb") as f:
                resp = requests.post(
                    f"{BASE_URL}/sessions/{session_id}/upload",
                    files={"file": (filename, f, "text/tab-separated-values")},
                    data={"file_type": file_type},
                )
            print(f"✅ {filename}: {resp.status_code}")
        
        # Run analyses
        results = run_analyses(session_id)
        
        # Save results
        results_path = os.path.join(RESULTS_DIR, "demo_results.json")
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n✅ Results JSON: {results_path}")
        
        # Generate PDF
        pdf_path = generate_pdf_report(results)
        
        print("\n" + "=" * 60)
        print("DEMO COMPLETE")
        print("=" * 60)
        print(f"Results JSON: {results_path}")
        print(f"Report: {pdf_path}")
        
    finally:
        stop_server(proc)


if __name__ == "__main__":
    main()
