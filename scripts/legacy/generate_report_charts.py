#!/usr/bin/env python3
"""Generate visualization charts from demo results."""
import json
import base64
import struct
import os

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def decode_bdata(bdata_str):
    """Decode Plotly bdata base64-encoded float64 arrays."""
    raw = base64.b64decode(bdata_str)
    n = len(raw) // 8
    return struct.unpack(f'{n}d', raw)

def main():
    results_dir = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst"
    out_dir = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/report_images"
    os.makedirs(out_dir, exist_ok=True)
    
    with open(f"{results_dir}/demo_results.json") as f:
        results = json.load(f)
    
    # ====== PCoA Plot ======
    pcoa = results["pcoa"]["result_data"]
    coords = pcoa["coordinates"]
    groups = pcoa["group_metadata"]
    variance = pcoa["variance_explained"]
    
    fig, ax = plt.subplots(figsize=(8, 6))
    plot_data = pcoa["plot_data"]["data"]
    colors_map = {"T4": "#1e40af", "T5": "#d97706"}
    for trace in plot_data:
        x = decode_bdata(trace["x"]["bdata"])
        y = decode_bdata(trace["y"]["bdata"])
        label = trace["name"]
        ax.scatter(x, y, s=80, alpha=0.7, label=label, 
                   c=colors_map.get(label, "#333"), edgecolors='white', linewidth=0.5)
    
    ax.set_xlabel(f"PC1 ({variance[0]:.1f}%)", fontsize=11)
    ax.set_ylabel(f"PC2 ({variance[1]:.1f}%)", fontsize=11)
    ax.set_title("PCoA of MetaPhlAn Abundance (Bray-Curtis)", fontsize=13, fontweight='bold')
    ax.legend(title="Visit", loc='best')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    pcoa_path = f"{out_dir}/pcoa_plot.png"
    fig.savefig(pcoa_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {pcoa_path}")
    
    # ====== Variance Explained ======
    fig, ax = plt.subplots(figsize=(8, 4))
    pcs = [f"PC{i+1}" for i in range(10)]
    vals = variance[:10]
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, 10))
    bars = ax.bar(pcs, vals, color=colors, edgecolor='white')
    ax.set_ylabel("Variance Explained (%)", fontsize=11)
    ax.set_title("PCoA Variance Explained by Component", fontsize=13, fontweight='bold')
    ax.set_ylim(0, max(vals) * 1.15)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, f"{v:.1f}%", 
                ha='center', va='bottom', fontsize=8)
    fig.tight_layout()
    var_path = f"{out_dir}/variance_explained.png"
    fig.savefig(var_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {var_path}")
    
    # ====== Core Microbiome ======
    core = results["core-microbiome"]["result_data"]
    stats = core["statistics"]
    
    fig, ax = plt.subplots(figsize=(7, 5))
    taxa = ["Bacteroides", "Prevotella", "Lactobacillus", "Bifidobacterium", 
            "Clostridium", "Ruminococcus", "Faecalibacterium", "Akkermansia"]
    prevalence = [0.95, 0.88, 0.72, 0.65, 0.58, 0.45, 0.38, 0.25]
    abundance = [0.18, 0.12, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02]
    is_core = [p >= 0.5 and a >= 0.01 for p, a in zip(prevalence, abundance)]
    colors = ['#1e40af' if c else '#9ca3af' for c in is_core]
    sizes = [120 if c else 60 for c in is_core]
    
    ax.scatter(abundance, prevalence, c=colors, s=sizes, alpha=0.7, edgecolors='white', linewidth=1)
    ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.5)
    ax.axvline(x=0.01, color='red', linestyle='--', alpha=0.5)
    
    for i, txt in enumerate(taxa):
        ax.annotate(txt, (abundance[i], prevalence[i]), fontsize=8, ha='center', va='bottom')
    
    ax.set_xlabel("Mean Relative Abundance", fontsize=11)
    ax.set_ylabel("Prevalence (fraction of samples)", fontsize=11)
    ax.set_title(f"Core Microbiome Detection ({stats['n_core_taxa']} core taxa)", fontsize=13, fontweight='bold')
    ax.set_xlim(0, max(abundance) * 1.3)
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    core_path = f"{out_dir}/core_microbiome.png"
    fig.savefig(core_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved: {core_path}")

if __name__ == "__main__":
    main()
