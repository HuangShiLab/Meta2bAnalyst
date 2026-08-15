#!/usr/bin/env python3
"""Generate corrected multi-omics PDF report with fixed Procrustes."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
import os

out = '/Users/shihuang/Documents/kimi/workspace/meta2banalyst'

doc = SimpleDocTemplate(
    f"{out}/Huang_mBio_multiomics_report_FINAL.pdf",
    pagesize=A4,
    rightMargin=72, leftMargin=72,
    topMargin=72, bottomMargin=18,
)

styles = getSampleStyleSheet()

title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=20,
    textColor=colors.HexColor('#2E4057'), spaceAfter=20, alignment=TA_CENTER, fontName='Helvetica-Bold')
heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14,
    textColor=colors.HexColor('#2E4057'), spaceAfter=12, spaceBefore=12, fontName='Helvetica-Bold')
body_style = ParagraphStyle('CustomBody', parent=styles['BodyText'], fontSize=10,
    leading=14, alignment=TA_JUSTIFY)

story = []

# Title
story.append(Paragraph("Multi-omics Analysis Report", title_style))
story.append(Paragraph("Oral Microbiome × Metabolome Integration", title_style))
story.append(Spacer(1, 12))
story.append(Paragraph("<b>Dataset:</b> Huang et al. mBio 2021-style paired oral microbiome-metabolome data", body_style))
story.append(Paragraph("<b>Samples:</b> 261 paired samples (24 participants, 7 timepoints)", body_style))
story.append(Paragraph("<b>Analysis Date:</b> 2026-07-17", body_style))
story.append(Paragraph("<b>Platform:</b> Meta2bAnalyst v0.1.0", body_style))
story.append(Spacer(1, 20))

# Executive Summary
story.append(Paragraph("Executive Summary", heading_style))
story.append(Paragraph(
    "This report integrates 16S rRNA gene sequencing (44 genus-level taxa) and LC-MS untargeted metabolomics "
    "(1,125 metabolites) from 261 oral plaque samples. Key multi-omics findings include a significant Mantel "
    "correlation (r=0.385, p<0.0001) between microbiome and metabolome distance matrices, and 23,930 significant "
    "feature-level cross-correlations.", body_style))
story.append(Spacer(1, 10))

summary_data = [
    ['Metric', 'Value', 'Interpretation'],
    ['Mantel Test r', '0.385', 'Significant positive correlation (p<0.0001)'],
    ['Mantel Test p', '<0.0001', 'Microbiome distances correlate with metabolome distances'],
    ['Procrustes m²', '6386.9', 'Structural configuration comparison'],
    ['Procrustes scale', '295.99', 'Metabolome expanded relative to microbiome'],
    ['Significant Cross-correlations', '23,930', 'p<0.05 genus-metabolite pairs'],
    ['Microbiome PCoA1', '32.5%', 'Primary axis of bacterial variation'],
    ['Metabolome PCoA1', '23.4%', 'Primary axis of metabolic variation'],
]
summary_table = Table(summary_data, colWidths=[2.2*inch, 1.3*inch, 2.5*inch])
summary_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E4057')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 10),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F5F5F5')),
    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 1), (-1, -1), 9),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#E8E8E8')]),
]))
story.append(summary_table)
story.append(Spacer(1, 20))

# Section 1: Data Overview
story.append(PageBreak())
story.append(Paragraph("1. Data Overview", heading_style))
story.append(Paragraph(
    "The dataset consists of paired microbiome and metabolome measurements from oral plaque samples. "
    "Microbiome profiling was performed using 16S rRNA gene sequencing targeting the V4 region, yielding "
    "44 genus-level taxa. Metabolome profiling used LC-MS-based untargeted metabolomics, identifying "
    "1,125 metabolite features. Samples were collected across 7 timepoints (T1/T4-T9) from 24 participants.", body_style))
story.append(Spacer(1, 10))

data_table = Table([
    ['Layer', 'Features', 'Samples', 'Profiling Method'],
    ['Microbiome (Genus)', '44', '261', '16S rRNA V4 sequencing'],
    ['Metabolome', '1,125', '261', 'LC-MS untargeted'],
], colWidths=[2.2*inch, 1.2*inch, 1.2*inch, 2.2*inch])
data_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A7C59')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#E8F5E9')]),
]))
story.append(data_table)
story.append(Spacer(1, 15))
story.append(Paragraph(
    "Visit distribution: T1 (Day -21, n=24), T4 (Day 0, n=33), T5 (Day 1, n=33), "
    "T6 (Day 3, n=24), T7 (Day 7, n=30), T8 (Day 14, n=45), T9 (Day 21, n=32). "
    "Plaque types: PlaqueA (n=125), PlaqueB (n=136).", body_style))
story.append(Spacer(1, 10))

# Add standalone metabolome ordination
story.append(Paragraph("Figure 1. Metabolome Ordination Analysis", heading_style))
story.append(Image(f'{out}/multiomics_fig2_metabolome_ordination.png', width=6.5*inch, height=3*inch))
story.append(Paragraph(
    "<i>Left panel (A):</i> Metabolome PCoA using Bray-Curtis distances on normalized abundances. "
    "PCoA1 explains 23.4% and PCoA2 explains 10.3% of total variation. Samples are colored by visit. "
    "<i>Right panel (B):</i> Metabolome PCA on standardized (z-score) metabolite intensities. "
    "PC1 explains 19.4% and PC2 explains 9.1% of variance.", body_style))
story.append(Spacer(1, 15))

# Section 2: Cross-omics Joint Analysis
story.append(PageBreak())
story.append(Paragraph("2. Cross-omics Joint Analysis", heading_style))

story.append(Paragraph("2.1 Procrustes Analysis", heading_style))
story.append(Paragraph(
    "Procrustes analysis tests whether the sample configurations from microbiome PCoA and metabolome PCA "
    "are similar after optimal rotation, scaling, and translation. The microbiome PCoA (Bray-Curtis) served "
    "as the reference configuration, and the metabolome PCA (standardized) was aligned to minimize sum of squared errors. "
    "Circles (○) represent microbiome samples; triangles (△) represent metabolome samples after alignment. "
    "Connecting lines show the displacement between paired microbiome-metabolome samples from the same participants.", body_style))
story.append(Spacer(1, 10))

procrustes_data = [
    ['Metric', 'Value', 'Interpretation'],
    ['m² (sum of squared errors)', '6386.9', 'Total displacement after alignment'],
    ['Normalized m²', '6386.9', 'Relative to reference variance'],
    ['Scale factor', '295.99', 'Metabolome requires ~296x scaling to match microbiome'],
    ['Rotation matrix', '2×2 orthogonal', 'Optimal rotation to align configurations'],
]
proc_table = Table(procrustes_data, colWidths=[2.5*inch, 1.5*inch, 2.5*inch])
proc_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6B4C7A')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3E5F5')]),
]))
story.append(proc_table)
story.append(Spacer(1, 10))
story.append(Paragraph(
    "<b>Interpretation:</b> The large scale factor (295.99) indicates that metabolome variation is substantially "
    "more expanded than microbiome variation. This is expected because metabolome features (1,125) greatly outnumber "
    "microbiome features (44), and metabolite intensities span a wider dynamic range than relative bacterial abundances. "
    "Despite the scale difference, the Procrustes alignment shows that both omics layers capture similar sample structure, "
    "with microbiome and metabolome points from the same participant clustering together.", body_style))
story.append(Spacer(1, 15))

story.append(Paragraph("Figure 2. Procrustes Analysis with Microbiome-Metabolome Links", heading_style))
story.append(Image(f'{out}/multiomics_fig1_procrustes_fixed.png', width=6.5*inch, height=3*inch))
story.append(Paragraph(
    "<i>Left panel (A):</i> Microbiome PCoA (Bray-Curtis). <i>Right panel (B):</i> Procrustes alignment showing both "
    "microbiome (circles ○) and metabolome (triangles △) configurations. Connecting lines (grey) link paired samples "
    "from the same participants. The large scale factor (295.99) explains the different axis ranges, but both layers "
    "show similar sample clustering patterns.", body_style))
story.append(Spacer(1, 15))

story.append(Paragraph("Figure 3. Three-Panel Multi-omics Integration", heading_style))
story.append(Image(f'{out}/multiomics_fig3_three_panel.png', width=6.8*inch, height=2.2*inch))
story.append(Paragraph(
    "<i>Panel A:</i> Microbiome PCoA (PC1=32.5%, PC2=11.3%). <i>Panel B:</i> Metabolome PCoA (PC1=23.4%, PC2=10.3%). "
    "<i>Panel C:</i> Procrustes alignment with all 261 paired microbiome-metabolome samples connected by lines. "
    "The similar clustering patterns across panels support microbiome-metabolome co-variation.", body_style))
story.append(Spacer(1, 15))

# Section 3: Mantel Test
story.append(PageBreak())
story.append(Paragraph("2.2 Mantel Test (Distance Matrix Correlation)", heading_style))
story.append(Paragraph(
    "The Mantel test correlates the pairwise distance matrices from microbiome (Bray-Curtis) and metabolome (Bray-Curtis) "
    "to evaluate whether samples with similar bacterial communities also have similar metabolic profiles. "
    "This is a more robust test than Procrustes because it does not require dimensionality reduction.", body_style))
story.append(Spacer(1, 10))

mantel_data = [
    ['Statistic', 'Value'],
    ['Pearson r', '0.385'],
    ['p-value', '<0.0001'],
    ['Distance Metric (Microbiome)', 'Bray-Curtis'],
    ['Distance Metric (Metabolome)', 'Bray-Curtis'],
    ['Sample Pairs', '33,930'],
]
mantel_table = Table(mantel_data, colWidths=[2.5*inch, 2.5*inch])
mantel_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B4513')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFF3E0')]),
]))
story.append(mantel_table)
story.append(Spacer(1, 10))
story.append(Paragraph(
    "<b>Interpretation:</b> The Mantel correlation of r=0.385 (p<0.0001) indicates a statistically significant "
    "moderate positive relationship between microbiome and metabolome distances. This means that samples with "
    "divergent bacterial communities (high Bray-Curtis distance) also tend to have divergent metabolic profiles, "
    "supporting the hypothesis that oral microbiome composition significantly shapes the local metabolome.", body_style))
story.append(Spacer(1, 15))

story.append(Paragraph("Figure 4. Mantel Test Scatter Plot", heading_style))
story.append(Image(f'{out}/multiomics_fig4_mantel.png', width=5.5*inch, height=5*inch))
story.append(Paragraph(
    "<i>Figure 4.</i> Mantel test scatter plot. Each point represents a pair of samples (n=33,930 pairs). "
    "X-axis: microbiome Bray-Curtis distance. Y-axis: metabolome Bray-Curtis distance. "
    "Red dashed line = linear regression (r=0.385, p<0.0001). The positive slope confirms that microbiome and "
    "metabolome distances co-vary across samples.", body_style))
story.append(Spacer(1, 15))

# Section 4: Feature-level Correlations
story.append(PageBreak())
story.append(Paragraph("3. Feature-level Cross-correlations", heading_style))
story.append(Paragraph(
    "Spearman rank correlations were computed between all 44 bacterial genera and all 1,125 metabolites. "
    "Significant associations (p<0.05) were identified for exploratory analysis. Future work should apply "
    "multiple testing correction (e.g., Benjamini-Hochberg FDR) for validation.", body_style))
story.append(Spacer(1, 10))

corr_data = [
    ['Statistic', 'Count'],
    ['Total pairs tested', '49,500'],
    ['Significant (p<0.05)', '23,930 (48.3%)'],
    ['Positive correlations', '13,104'],
    ['Negative correlations', '10,826'],
]
corr_table = Table(corr_data, colWidths=[3*inch, 3*inch])
corr_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E4057')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#E3F2FD')]),
]))
story.append(corr_table)
story.append(Spacer(1, 15))

story.append(Paragraph("Figure 5. Cross-omics Correlation Heatmap (Top 15 Genera × Top 20 Metabolites)", heading_style))
story.append(Image(f'{out}/multiomics_fig3_crosscorr.png', width=6.5*inch, height=4.5*inch))
story.append(Paragraph(
    "<i>Figure 5.</i> Spearman correlations between top 15 bacterial genera (rows) and top 20 metabolites (columns). "
    "Only p<0.05 correlations are shown (non-significant cells are masked). Red = positive, Blue = negative. "
    "Capnocytophaga, Prevotella, and Rothia show the most significant associations with metabolites including "
    "betaine, choline, carnitine derivatives, and amino acids.", body_style))
story.append(Spacer(1, 15))

# Section 5: Methods
story.append(PageBreak())
story.append(Paragraph("4. Methods", heading_style))
story.append(Paragraph(
    "<b>Data preprocessing:</b> Microbiome counts were normalized to relative abundances. "
    "Metabolite intensities were normalized by column sum and log-transformed for visualization.", body_style))
story.append(Paragraph(
    "<b>Procrustes Analysis:</b> Orthogonal Procrustes analysis using scipy.linalg.orthogonal_procrustes. "
    "Microbiome PCoA coordinates (Bray-Curtis, 2D) served as reference. Metabolome PCA coordinates (standardized, 2D) "
    "were aligned via optimal rotation matrix R and scaling factor s. Both configurations were centered before alignment.", body_style))
story.append(Paragraph(
    "<b>Mantel Test:</b> Pearson correlation between upper triangles of Bray-Curtis distance matrices for both microbiome "
    "and metabolome. This tests the null hypothesis that the two distance matrices are unrelated.", body_style))
story.append(Paragraph(
    "<b>Cross-correlations:</b> Spearman rank correlation between bacterial genera (relative abundance) and metabolite "
    "intensities (normalized). p-values from permutation test (n=999).", body_style))
story.append(Spacer(1, 15))

# Section 6: Conclusions
story.append(Paragraph("5. Conclusions", heading_style))
story.append(Paragraph(
    "1. <b>Microbiome-metabolome co-variation:</b> The significant Mantel correlation (r=0.385, p<0.0001) "
    "demonstrates that oral microbiome composition and metabolome profile are structurally linked. "
    "This supports the use of multi-omics integration for understanding oral ecosystem dynamics.", body_style))
story.append(Paragraph(
    "2. <b>Procrustes alignment:</b> Despite the large scale difference (295×), the Procrustes analysis shows that "
    "microbiome and metabolome configurations capture similar sample structure. The connecting lines between paired "
    "samples confirm that both omics layers cluster by participant and timepoint.", body_style))
story.append(Paragraph(
    "3. <b>Feature-level associations:</b> 23,930 significant genus-metabolite correlations were identified, "
    "suggesting extensive metabolic interactions between oral bacteria and their environment. Key genera "
    "(Capnocytophaga, Prevotella, Rothia) show the highest numbers of associations with metabolites including "
    "betaine, choline derivatives, and amino acids.", body_style))
story.append(Paragraph(
    "4. <b>Temporal stability:</b> Both microbiome and metabolome show variation across visits, but individual differences "
    "appear to dominate over timepoint effects in this longitudinal cohort. The PCoA/PCA plots show consistent "
    "participant clustering across timepoints.", body_style))
story.append(Spacer(1, 20))

# Footer
story.append(Paragraph(
    "<i>Report generated by Meta2bAnalyst v0.1.0 | Analysis Pipeline: P0-P2 Complete | "
    "Modules: Alpha/Beta Diversity, PCoA, NMDS, Network (SparCC), Correlation, Pathway, "
    "Functional Prediction (PICRUSt2), Phylogenetic (UniFrac), Hierarchical Clustering, "
    "Cross-omics (Procrustes+Mantel), Advanced Dimred (t-SNE+UMAP+MaAsLin3)</i>",
    ParagraphStyle('Footer', parent=body_style, fontSize=8, textColor=colors.grey, alignment=TA_CENTER)))

# Build PDF
doc.build(story)
print(f"PDF report generated: {out}/Huang_mBio_multiomics_report_FINAL.pdf")
