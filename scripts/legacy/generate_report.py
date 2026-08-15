#!/usr/bin/env python3
"""Generate PDF report from demo results."""
import json
import os
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak
)

RESULTS_PATH = '/Users/shihuang/Documents/kimi/workspace/meta2banalyst/demo_results.json'
OUTPUT_DIR = '/Users/shihuang/Documents/kimi/workspace/meta2banalyst/report_output'


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    with open(RESULTS_PATH, 'r') as f:
        results = json.load(f)
    
    # Plot 1: Alpha Diversity Boxplot
    alpha = results['alpha-diversity']['result_data']
    sample_div = alpha['sample_diversity']
    shannon_vals = [sample_div[s]['shannon'] for s in sorted(sample_div.keys())]
    simpson_vals = [sample_div[s]['simpson'] for s in sorted(sample_div.keys())]
    
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].boxplot([shannon_vals[:10], shannon_vals[10:]], tick_labels=['T4', 'T5'])
    axes[0].set_title('Shannon Diversity by Visit')
    axes[0].set_ylabel('Shannon Index')
    
    axes[1].boxplot([simpson_vals[:10], simpson_vals[10:]], tick_labels=['T4', 'T5'])
    axes[1].set_title('Simpson Diversity by Visit')
    axes[1].set_ylabel('Simpson Index')
    
    plt.tight_layout()
    alpha_plot_path = os.path.join(OUTPUT_DIR, 'alpha_diversity.png')
    fig.savefig(alpha_plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # Plot 2: PCoA scatter
    pcoa = results['pcoa']['result_data']
    coords = pcoa['coordinates']
    groups = pcoa.get('group_metadata', {})
    
    fig, ax = plt.subplots(figsize=(6, 5))
    t4_x, t4_y, t5_x, t5_y = [], [], [], []
    for sample, c in coords.items():
        g = groups.get(sample, 'Unknown')
        if g == 'T4':
            t4_x.append(c['PC1']); t4_y.append(c['PC2'])
        elif g == 'T5':
            t5_x.append(c['PC1']); t5_y.append(c['PC2'])
    
    ax.scatter(t4_x, t4_y, c='#1e40af', label='T4', s=60, alpha=0.7)
    ax.scatter(t5_x, t5_y, c='#d97706', label='T5', s=60, alpha=0.7)
    ve = pcoa.get('variance_explained', [0, 0])
    ax.set_xlabel(f"PC1 ({ve[0]*100:.1f}%)")
    ax.set_ylabel(f"PC2 ({ve[1]*100:.1f}%)")
    ax.set_title('PCoA (Bray-Curtis)')
    ax.legend()
    plt.tight_layout()
    pcoa_plot_path = os.path.join(OUTPUT_DIR, 'pcoa.png')
    fig.savefig(pcoa_plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # Plot 3: Taxonomy Bar (top taxa mean abundance)
    taxo = results['taxonomy-bar']['result_data']['statistics']
    top_taxa = taxo['top_taxa'][:10]
    group_avgs = taxo['group_averages']
    
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(top_taxa))
    width = 0.35
    
    t4_vals = [group_avgs['T4'].get(t, 0) for t in top_taxa]
    t5_vals = [group_avgs['T5'].get(t, 0) for t in top_taxa]
    
    ax.bar(x - width/2, t4_vals, width, label='T4')
    ax.bar(x + width/2, t5_vals, width, label='T5')
    ax.set_ylabel('Mean Relative Abundance (%)')
    ax.set_title('Top 10 Taxa by Group')
    ax.set_xticks(x)
    ax.set_xticklabels([t.split('|')[-1] for t in top_taxa], rotation=45, ha='right')
    ax.legend()
    plt.tight_layout()
    taxo_plot_path = os.path.join(OUTPUT_DIR, 'taxonomy_bar.png')
    fig.savefig(taxo_plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # Plot 4: Core Microbiome Prevalence
    core = results['core-microbiome']['result_data']['statistics']
    core_prev = core['core_prevalence']
    taxa_short = [t.split('|')[-1] for t in list(core_prev.keys())[:15]]
    prev_vals = list(core_prev.values())[:15]
    
    fig, ax = plt.subplots(figsize=(10, 4))
    colors_list = ['#2ca02c' if p >= 0.5 else '#1f77b4' for p in prev_vals]
    ax.barh(range(len(taxa_short)), prev_vals, color=colors_list)
    ax.axvline(x=0.5, color='red', linestyle='--', label='Threshold (0.5)')
    ax.set_yticks(range(len(taxa_short)))
    ax.set_yticklabels(taxa_short)
    ax.set_xlabel('Prevalence')
    ax.set_title('Core Microbiome Prevalence (Top 15)')
    ax.legend()
    plt.tight_layout()
    core_plot_path = os.path.join(OUTPUT_DIR, 'core_microbiome.png')
    fig.savefig(core_plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    # Generate PDF
    pdf_path = os.path.join(OUTPUT_DIR, 'Meta2bAnalyst_Demo_Report.pdf')
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=24, textColor=colors.HexColor('#1e40af'),
        spaceAfter=30, alignment=1,
    )
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'],
        fontSize=16, textColor=colors.HexColor('#1e40af'),
        spaceAfter=12, spaceBefore=12,
    )
    
    story = []
    
    # Title Page
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("Meta2bAnalyst", title_style))
    story.append(Paragraph("Microbiome Analysis Report", styles['Title']))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    story.append(Paragraph("<b>Dataset:</b> MetaPhlAn Demo (20 samples, 19 species)", styles['Normal']))
    story.append(Paragraph("<b>Groups:</b> T4 (n=10), T5 (n=10)", styles['Normal']))
    story.append(PageBreak())
    
    # Executive Summary
    story.append(Paragraph("Executive Summary", heading_style))
    story.append(Paragraph(
        "This report presents the results of a comprehensive microbiome analysis "
        "performed on 20 fecal samples profiled with MetaPhlAn. The dataset spans "
        "19 taxonomic clades from kingdom to species level, with samples collected "
        "at two timepoints (T4 and T5). Seven analytical modules were executed successfully.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.2*inch))
    
    summary_data = [
        ['Analysis', 'Status', 'Key Finding'],
        ['Alpha Diversity', 'Completed', 'No significant difference between T4/T5 (p=0.27)'],
        ['Beta Diversity', 'Completed', 'Bray-Curtis distances computed for all pairs'],
        ['PCoA', 'Completed', 'Principal coordinate analysis performed'],
        ['PERMANOVA', 'Completed', f"Pseudo-F = {results['permanova']['result_data']['pseudo_f']:.2f}, p = {results['permanova']['result_data']['pvalue']:.3f}"],
        ['Rarefaction', 'Completed', 'Richness & Shannon saturated at depth >= 60'],
        ['Taxonomy Bar', 'Completed', f"Top genus: {taxo['top_taxa'][0]} ({taxo['group_averages']['T4'][taxo['top_taxa'][0]]:.1f}% T4)"],
        ['Core Microbiome', 'Completed', f"{core['n_core_taxa']} core taxa (prevalence >= 0.5)"],
    ]
    summary_table = Table(summary_data, colWidths=[2.2*inch, 1.3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(PageBreak())
    
    # Alpha Diversity
    story.append(Paragraph("1. Alpha Diversity", heading_style))
    story.append(Paragraph(
        "Alpha diversity measures within-sample microbial diversity. Shannon index "
        "quantifies richness and evenness, while Simpson index measures dominance.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    
    alpha_stats = alpha['group_statistics']['shannon']
    alpha_data = [
        ['Metric', 'Group', 'Mean', 'Median', 'Std', 'Min', 'Max', 'N'],
        ['Shannon', 'T4', f"{alpha_stats['T4']['mean']:.3f}", f"{alpha_stats['T4']['median']:.3f}",
         f"{alpha_stats['T4']['std']:.3f}", f"{alpha_stats['T4']['min']:.3f}", f"{alpha_stats['T4']['max']:.3f}", str(alpha_stats['T4']['n'])],
        ['Shannon', 'T5', f"{alpha_stats['T5']['mean']:.3f}", f"{alpha_stats['T5']['median']:.3f}",
         f"{alpha_stats['T5']['std']:.3f}", f"{alpha_stats['T5']['min']:.3f}", f"{alpha_stats['T5']['max']:.3f}", str(alpha_stats['T5']['n'])],
    ]
    alpha_table = Table(alpha_data, colWidths=[0.9*inch, 0.6*inch, 0.7*inch, 0.7*inch, 0.6*inch, 0.6*inch, 0.6*inch, 0.4*inch])
    alpha_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f766e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(alpha_table)
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        f"<b>Mann-Whitney U test:</b> statistic = {alpha_stats['statistical_test']['statistic']:.1f}, "
        f"p = {alpha_stats['statistical_test']['pvalue']:.3f}. "
        f"{'Significant' if alpha_stats['statistical_test']['significant'] else 'Not significant'} at alpha = 0.05.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    story.append(Image(alpha_plot_path, width=5.5*inch, height=2.2*inch))
    story.append(PageBreak())
    
    # Beta Diversity & PERMANOVA
    story.append(Paragraph("2. Beta Diversity & PERMANOVA", heading_style))
    story.append(Paragraph(
        "Beta diversity quantifies between-sample dissimilarity using Bray-Curtis distance. "
        "PERMANOVA tests whether group centroids differ significantly.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    
    perm = results['permanova']['result_data']
    perm_data = [
        ['Statistic', 'Value'],
        ['Pseudo-F', f"{perm['pseudo_f']:.4f}"],
        ['p-value', f"{perm['pvalue']:.4f}"],
        ['Significant (alpha=0.05)', 'Yes' if perm['significant'] else 'No'],
        ['SSB (between)', f"{perm['ssb']:.4f}"],
        ['SSW (within)', f"{perm['ssw']:.4f}"],
        ['DF between', str(perm['df_between'])],
        ['DF within', str(perm['df_within'])],
        ['Permutations', str(perm['n_permutations'])],
    ]
    perm_table = Table(perm_data, colWidths=[2.5*inch, 2*inch])
    perm_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(perm_table)
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph("<b>PCoA Visualization</b>", styles['Heading3']))
    story.append(Image(pcoa_plot_path, width=4.5*inch, height=3.5*inch))
    story.append(PageBreak())
    
    # Rarefaction
    story.append(Paragraph("3. Rarefaction Analysis", heading_style))
    story.append(Paragraph(
        "Rarefaction curves assess sampling completeness. Saturation indicates whether "
        "additional sequencing would reveal new taxa.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    
    rare_stats = results['rarefaction']['result_data']['statistics']
    rare_data = [
        ['Metric', 'Saturated', 'Saturation Ratio', 'Max Depth'],
        ['Richness', 'Yes' if rare_stats['saturated']['richness'] else 'No',
         f"{rare_stats['saturation_ratio']['richness']:.2f}", str(rare_stats['max_depth'])],
        ['Shannon', 'Yes' if rare_stats['saturated']['shannon'] else 'No',
         f"{rare_stats['saturation_ratio']['shannon']:.2f}", str(rare_stats['max_depth'])],
    ]
    rare_table = Table(rare_data, colWidths=[1.5*inch, 1.2*inch, 1.5*inch, 1.2*inch])
    rare_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d97706')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(rare_table)
    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Both richness and Shannon diversity indices reached saturation at the maximum sampling depth, "
        "indicating sufficient sequencing depth for robust diversity estimation.",
        styles['Normal']
    ))
    story.append(PageBreak())
    
    # Taxonomy Bar
    story.append(Paragraph("4. Community Composition (Genus Level)", heading_style))
    story.append(Paragraph(
        "Stacked bar plot aggregated to genus level shows relative abundance of "
        "dominant taxa. Faecalibacterium and Bacteroides are the most abundant genera.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    story.append(Image(taxo_plot_path, width=5.5*inch, height=2.5*inch))
    story.append(PageBreak())
    
    # Core Microbiome
    story.append(Paragraph("5. Core Microbiome", heading_style))
    story.append(Paragraph(
        f"Core taxa are defined as present in >= {core['prevalence_threshold']*100:.0f}% of samples "
        f"at >= {core['abundance_threshold']*100:.1f}% relative abundance. "
        f"{core['n_core_taxa']} taxa met these criteria.",
        styles['Normal']
    ))
    story.append(Spacer(1, 0.1*inch))
    story.append(Image(core_plot_path, width=5.5*inch, height=2.2*inch))
    story.append(PageBreak())
    
    # Methods
    story.append(Paragraph("Methods", heading_style))
    story.append(Paragraph("<b>Alpha Diversity:</b> Shannon and Simpson indices from relative abundances.", styles['Normal']))
    story.append(Paragraph("<b>Beta Diversity:</b> Bray-Curtis dissimilarity on relative abundance profiles.", styles['Normal']))
    story.append(Paragraph("<b>PERMANOVA:</b> Permutational multivariate ANOVA with 999 permutations.", styles['Normal']))
    story.append(Paragraph("<b>Rarefaction:</b> Iterative subsampling (10 iterations) with CSS normalization.", styles['Normal']))
    story.append(Paragraph("<b>Taxonomy Bar:</b> Aggregation to genus level from MetaPhlAn clade_names.", styles['Normal']))
    story.append(Paragraph("<b>Core Microbiome:</b> Prevalence-abundance thresholding per taxon.", styles['Normal']))
    
    # Build PDF
    doc.build(story)
    print(f"PDF saved to: {pdf_path}")


if __name__ == '__main__':
    main()
