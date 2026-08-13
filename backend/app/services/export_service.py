"""
Meta2bAnalyst - Export Service
Handles export of data, results, and plots in various formats.
"""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def export_data(
    source_path: str,
    export_path: str,
    format: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export data file to the specified format.

    Args:
        source_path: Path to source data file
        export_path: Path for exported file
        format: Export format (csv, tsv, xlsx, biom, json)
        parameters: Optional export parameters
    """
    params = parameters or {}
    
    # Read source data
    if source_path.endswith(".csv"):
        df = pd.read_csv(source_path, index_col=0)
    elif source_path.endswith(".biom"):
        # Try to parse as BIOM
        try:
            import biom
            table = biom.load_table(source_path)
            df = pd.DataFrame(
                table.matrix_data.toarray().T,
                index=table.ids(axis="sample"),
                columns=table.ids(axis="observation"),
            ).T
        except ImportError:
            raise RuntimeError("biom-format not installed, cannot export BIOM file")
    else:
        df = pd.read_csv(source_path, sep="\t", index_col=0)
    
    # Export based on format
    if format == "csv":
        df.to_csv(export_path)
    elif format in ("tsv", "txt"):
        df.to_csv(export_path, sep="\t")
    elif format == "xlsx":
        df.to_excel(export_path)
    elif format == "json":
        df.to_json(export_path, orient="records", indent=2)
    elif format == "biom":
        try:
            import biom
            from biom.table import Table
            table = Table(df.values, list(df.index), list(df.columns))
            with open(export_path, "w") as f:
                f.write(table.to_json("Meta2bAnalyst"))
        except ImportError:
            raise RuntimeError("biom-format not installed, cannot export to BIOM")
    else:
        raise ValueError(f"Unsupported export format for data: {format}")
    
    logger.info(f"Exported data to {export_path} (format: {format})")


def export_result(
    result_data: Optional[Dict[str, Any]],
    export_path: str,
    format: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export analysis result to the specified format.

    Args:
        result_data: Analysis result dictionary
        export_path: Path for exported file
        format: Export format (json, csv, html, pdf)
        parameters: Optional export parameters
    """
    if result_data is None:
        raise ValueError("No result data to export")
    
    params = parameters or {}
    
    if format == "json":
        with open(export_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)
    
    elif format in ("csv", "tsv"):
        # Extract tabular data from result if available
        sep = "\t" if format == "tsv" else ","
        if "all_features" in result_data:
            df = pd.DataFrame(result_data["all_features"])
            df.to_csv(export_path, sep=sep, index=False)
        elif "sample_diversity" in result_data:
            records = []
            for sample, values in result_data["sample_diversity"].items():
                row = {"sample": sample, **values}
                records.append(row)
            df = pd.DataFrame(records)
            df.to_csv(export_path, sep=sep, index=False)
        else:
            with open(export_path, "w") as f:
                json.dump(result_data, f, indent=2, default=str)
    
    elif format == "html":
        # Simple HTML export
        html = f"""<!DOCTYPE html>
<html>
<head><title>Meta2bAnalyst Result</title></head>
<body>
<h1>Analysis Result</h1>
<pre>{json.dumps(result_data, indent=2, default=str)}</pre>
</body>
</html>"""
        with open(export_path, "w") as f:
            f.write(html)
    
    elif format == "pdf":
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        
        doc = SimpleDocTemplate(export_path, pagesize=A4,
                               rightMargin=2*cm, leftMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph("Meta2bAnalyst Analysis Report", styles['Title']))
        story.append(Spacer(1, 0.5*cm))
        
        # Analysis info
        story.append(Paragraph(f"Analysis Type: {result_data.get('test_method', 'Unknown')}", styles['Heading2']))
        story.append(Paragraph(f"Group Column: {result_data.get('group_column', 'N/A')}", styles['Normal']))
        story.append(Spacer(1, 0.5*cm))
        
        # Significant features table
        if 'significant_features' in result_data and result_data['significant_features']:
            story.append(Paragraph("Significant Features", styles['Heading2']))
            sig_features = result_data['significant_features'][:50]  # Limit to 50
            if sig_features:
                headers = list(sig_features[0].keys())
                data = [headers] + [[str(row.get(h, '')) for h in headers] for row in sig_features]
                table = Table(data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ]))
                story.append(table)
        
        doc.build(story)
    
    else:
        with open(export_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)
    
    logger.info(f"Exported result to {export_path} (format: {format})")


def export_plot(
    session_id: str,
    export_path: str,
    format: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export plot to the specified format.

    Args:
        session_id: Session ID for locating plot data
        export_path: Path for exported file
        format: Export format (png, svg, html, json)
        parameters: Optional export parameters
    """
    params = parameters or {}
    
    if format in ("png", "svg", "jpg", "jpeg"):
        import plotly.io as pio
        # From result_data 中提取 plot_data JSON
        fig_data = params.get('plot_data')
        if fig_data:
            fig = pio.from_json(json.dumps(fig_data))
            if format == 'svg':
                fig.write_image(export_path, format='svg', engine='kaleido')
            elif format in ('jpg', 'jpeg'):
                fig.write_image(export_path, format='jpeg', engine='kaleido', width=1200, height=800, scale=2)
            else:  # png
                fig.write_image(export_path, format='png', engine='kaleido', width=1200, height=800, scale=2)
            logger.info(f"Exported plot to {export_path} (format: {format})")
        else:
            raise ValueError("No plot data provided for image export")
    
    elif format == "html":
        # Create a simple HTML with embedded plotly
        html = f"""<!DOCTYPE html>
<html>
<head><title>Meta2bAnalyst Plot</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
<div id="plot"></div>
<script>
// Plot data would be loaded here
Plotly.newPlot('plot', [], {{}});
</script>
</body>
</html>"""
        with open(export_path, "w") as f:
            f.write(html)
    
    elif format == "json":
        results_dir = Path("./uploads") / session_id / "results"
        plot_files = list(results_dir.glob("*.json")) if results_dir.exists() else []
        if plot_files:
            import shutil
            shutil.copy(plot_files[0], export_path)
    
    logger.info(f"Exported plot to {export_path} (format: {format})")



def _plotly_to_image(plot_data: dict, tmp_dir: str, width: int = 800, height: int = 600, scale: int = 2) -> Optional[str]:
    """Convert Plotly JSON dict to temporary PNG file. Returns path or None."""
    if not plot_data or not plot_data.get('data'):
        return None
    try:
        import plotly.io as pio
        fig = pio.from_json(json.dumps(plot_data))
        img_path = os.path.join(tmp_dir, f"plot_{os.urandom(4).hex()}.png")
        pio.write_image(fig, img_path, format="png", width=width, height=height, scale=scale)
        return img_path
    except Exception as e:
        logger.warning(f"Failed to convert plot to image: {e}")
        return None


def _methodology_text(job_type: str) -> str:
    """Return methodology description for each analysis type."""
    methods = {
        'alpha': (
            "<b>Methodology:</b> Alpha diversity measures the richness and evenness of microbial "
            "communities within a single sample. This analysis computes Shannon index (richness + evenness), "
            "Simpson index (dominance concentration), Chao1 (estimated total species richness), "
            "Observed OTUs/ASVs (actual observed species count), and Pielou evenness index. "
            "Group differences are assessed by Kruskal-Wallis or ANOVA."
        ),
        'beta': (
            "<b>Methodology:</b> Beta diversity quantifies the compositional dissimilarity between "
            "different samples. This analysis uses the Bray-Curtis distance (abundance-based, accounting for "
            "shared species and abundance differences) to compute a pairwise distance matrix. "
            "Bray-Curtis ranges from 0 (identical communities) to 1 (completely different)."
        ),
        'pcoa': (
            "<b>Methodology:</b> Principal Coordinate Analysis (PCoA) is an unsupervised dimensionality "
            "reduction method that projects high-dimensional Beta distance matrices into a low-dimensional space "
            "(typically 2-3 axes) for visualization. Each axis is annotated with the percentage of variance explained, "
            "reflecting the contribution of that dimension to the overall compositional differences."
        ),
        'differential': (
            "<b>Methodology:</b> Differential abundance analysis identifies microbial features that are "
            "significantly altered between experimental groups. Methods include t-test/Wilcoxon (parametric/non-parametric), "
            "ANCOM-BC (compositionality-aware microbiome-specific method), and LEfSe (combining statistical significance "
            "with effect size via LDA scores). Multiple testing correction is performed using Benjamini-Hochberg (FDR) "
            "to control the false discovery rate."
        ),
        't-test': (
            "<b>Methodology:</b> The two-sample t-test (Student's t-test or Welch's t-test) is a parametric "
            "statistical test used to compare the mean abundance of microbial features between two groups. "
            "It assumes approximately normal distribution of the data. P-values are adjusted for multiple testing "
            "using the Benjamini-Hochberg (FDR) method to control the false discovery rate."
        ),
        'wilcoxon': (
            "<b>Methodology:</b> The Wilcoxon rank-sum test (Mann-Whitney U test) is a non-parametric "
            "statistical test used to compare the median abundance of microbial features between two groups. "
            "It does not assume normal distribution and is more robust to outliers than the t-test. "
            "P-values are adjusted for multiple testing using the Benjamini-Hochberg (FDR) method."
        ),
        'ANCOM-BC': (
            "<b>Methodology:</b> ANCOM-BC (Analysis of Compositions of Microbiomes with Bias Correction) "
            "is a microbiome-specific differential abundance method that accounts for compositional bias and "
            "sample-specific biases. It uses a linear regression framework with bias correction to identify "
            "features that are differentially abundant between groups. It is particularly robust for sparse data."
        ),
        'ancombc': (
            "<b>Methodology:</b> ANCOM-BC (Analysis of Compositions of Microbiomes with Bias Correction) "
            "is a microbiome-specific differential abundance method that accounts for compositional bias and "
            "sample-specific biases. It uses a linear regression framework with bias correction to identify "
            "features that are differentially abundant between groups. It is particularly robust for sparse data."
        ),
        'lefse': (
            "<b>Methodology:</b> LEfSe (Linear Discriminant Analysis Effect Size) is a microbiome-specific "
            "biomarker discovery tool. It proceeds in three steps: (1) Kruskal-Wallis test to screen features with "
            "significant inter-group differences; (2) Wilcoxon rank-sum test to validate within-subgroup consistency; "
            "(3) LDA to compute effect sizes. LDA scores > 2.0 are generally considered biologically meaningful biomarkers."
        ),
        'LEfSe': (
            "<b>Methodology:</b> LEfSe (Linear Discriminant Analysis Effect Size) is a microbiome-specific "
            "biomarker discovery tool. It proceeds in three steps: (1) Kruskal-Wallis test to screen features with "
            "significant inter-group differences; (2) Wilcoxon rank-sum test to validate within-subgroup consistency; "
            "(3) LDA to compute effect sizes. LDA scores > 2.0 are generally considered biologically meaningful biomarkers."
        ),
        'random_forest': (
            "<b>Methodology:</b> Random Forest is an ensemble machine learning algorithm used to classify "
            "samples based on microbial community features. By constructing multiple decision trees and averaging predictions, "
            "it evaluates the contribution of each feature (feature importance). 5-fold cross-validation is used to assess "
            "generalization, and Out-of-Bag (OOB) error estimates model performance."
        ),
        'heatmap': (
            "<b>Methodology:</b> The heatmap displays the abundance patterns of the top 50 high-variance "
            "features across all samples. Data are z-score standardized (row-wise) to make features of different magnitudes "
            "comparable. Hierarchical clustering (Ward's method) groups samples and features based on similarity in abundance "
            "patterns, revealing co-occurrence and mutual-exclusion relationships."
        ),
        'stacked_bar': (
            "<b>Methodology:</b> The stacked bar chart shows the relative compositional proportions of major "
            "microbial taxa in each sample. Each bar represents a sample, colors represent different taxonomic units "
            "(species/genus/phylum level), and bar height is 100% (relative abundance), enabling intuitive comparison "
            "of community structure between groups."
        ),
    }
    return methods.get(job_type, "<b>Methodology:</b> Microbiome statistical analysis.")


def _interpretation_text(result: dict) -> str:
    """Generate interpretation text based on analysis results."""
    interpretations = []
    
    # Alpha diversity
    if 'group_statistics' in result:
        gs = result['group_statistics']
        stats_texts = []
        for metric, stats in gs.items():
            if metric == 'statistical_test':
                continue
            st = stats.get('statistical_test')
            if st:
                test_name = st.get('test', '')
                pval = st.get('pvalue', 1.0)
                sig = 'significant' if st.get('significant', False) else 'not significant'
                stats_texts.append(
                    f"<b>{metric.title()}:</b> {test_name} p={pval}, {sig}"
                )
        if stats_texts:
            interpretations.append(
                f"<b>Interpretation:</b> Alpha diversity group comparison results: " + "; ".join(stats_texts) + "."
            )
    elif 'sample_diversity' in result:
        sd = result['sample_diversity']
        if sd:
            first = list(sd.values())[0]
            metrics = list(first.keys())
            interpretations.append(
                f"<b>Interpretation:</b> Alpha diversity analysis completed, covering {len(metrics)} metrics: "
                f"{', '.join(metrics)}. A total of {len(sd)} samples were analyzed. "
                f"If a metric shows significant differences between groups (p &lt; 0.05), it suggests that "
                f"the microbial community richness or evenness differs statistically between groups."
            )
    
    # Beta diversity
    if 'permanova' in result:
        perm = result['permanova']
        # Calculate pseudo-R2 from SSB / SST if R2 not present
        ssb = perm.get('ssb', 0)
        sst = ssb + perm.get('ssw', 0)
        r2 = perm.get('R2', ssb / sst if sst > 0 else 0)
        pval = perm.get('pvalue', perm.get('p_value', 1.0))
        sig = 'significant' if perm.get('significant', pval < 0.05) else 'not significant'
        interpretations.append(
            f"<b>Interpretation:</b> PERMANOVA test indicates that group differences explain {r2:.1%} of the "
            f"community variation (p={pval}, {sig}). "
            f"If the p-value is significant, the grouping variable is a strong driver of community structure differences."
        )
    elif 'distance_matrix' in result:
        n = result.get('sample_count', 0)
        interpretations.append(
            f"<b>Interpretation:</b> Beta distance matrix was computed based on {n} samples. "
            f"PCoA/NMDS visualization can be used to inspect clustering patterns; "
            f"if samples from the same group cluster tightly, it indicates high within-group community similarity."
        )
    
    # PCoA
    if 'variance_explained' in result:
        ve = result['variance_explained']
        if ve and len(ve) >= 2:
            interpretations.append(
                f"<b>Interpretation:</b> The first two PCoA axes explain {ve[0]:.1f}% and {ve[1]:.1f}% of variance, respectively. "
                f"Cumulatively, they explain {sum(ve[:2]):.1f}% of community differences. "
                f"If samples from different groups are clearly separated in the PCoA plot, it indicates that the "
                f"grouping variable is a major driver of community structure variation."
            )
    
    # Differential
    if 'significant_features' in result:
        sig = result['significant_features']
        n_sig = len(sig) if isinstance(sig, list) else 0
        test = result.get('test_method', 'differential')
        g1 = result.get('group1', 'Group 1')
        g2 = result.get('group2', 'Group 2')
        if n_sig > 0:
            top = sig[0] if n_sig > 0 else {}
            feat_name = top.get('feature', 'N/A') if isinstance(top, dict) else 'N/A'
            interpretations.append(
                f"<b>Interpretation:</b> Using {test}, {n_sig} significantly differential features were identified (q &lt; 0.05). "
                f"The most significant feature is <i>{feat_name}</i>. "
                f"log2FC &gt; 0 indicates enrichment in {g2}; log2FC &lt; 0 indicates enrichment in {g1}. "
                f"Consider both effect size (log2FC) and statistical significance (q-value) for biological relevance."
            )
        else:
            interpretations.append(
                f"<b>Interpretation:</b> Using {test}, no statistically significant differential features were found (q &lt; 0.05). "
                f"Possible reasons: insufficient sample size, small between-group differences, or high data dispersion. "
                f"Consider increasing sample size or relaxing the significance threshold (e.g., q &lt; 0.1) for exploratory analysis."
            )
    
    # Random Forest
    if 'accuracy' in result:
        acc = result['accuracy']
        cv_mean = result.get('cv_mean_accuracy', 0)
        cv_std = result.get('cv_std_accuracy', 0)
        n_est = result.get('n_estimators', 0)
        interpretations.append(
            f"<b>Interpretation:</b> The Random Forest classifier ({n_est} trees) achieved a test-set accuracy of {acc:.1%}. "
            f"5-fold cross-validation mean accuracy is {cv_mean:.1%} ± {cv_std:.1%}. "
            f"If CV accuracy is close to the test accuracy, the model generalizes well and is not overfitted. "
            f"The most important features may serve as potential biomarkers for distinguishing groups."
        )
    
    # Heatmap
    if 'matrix' in result:
        interpretations.append(
            f"<b>Interpretation:</b> The heatmap displays the abundance patterns of the top 50 high-variance features. "
            f"Color intensity represents standardized relative abundance (z-score). "
            f"Samples in the same clustering branch share similar community structures; "
            f"features in the same branch share similar abundance distribution patterns."
        )
    
    # Stacked bar
    if 'plot_data' in result and result.get('test_method', '') == 'stacked_bar':
        interpretations.append(
            f"<b>Interpretation:</b> The stacked bar chart shows the community composition proportions of each sample. "
            f"Different colored blocks represent different microbial taxa. "
            f"If samples from a group show similar color composition patterns, the group has a characteristic community structure."
        )
    
    # LEfSe
    if 'test_method' in result and 'LEfSe' in str(result.get('test_method', '')):
        lda = result.get('lda_threshold', 2.0)
        sig = result.get('significant_features', [])
        n_sig = len(sig) if isinstance(sig, list) else 0
        if n_sig > 0:
            interpretations.append(
                f"<b>Interpretation:</b> LEfSe analysis identified {n_sig} biomarkers (LDA &gt; {lda}). "
                f"These features have both statistical significance and large effect sizes between groups, "
                f"and may serve as potential microbial biomarkers for distinguishing the experimental groups."
            )
        else:
            interpretations.append(
                f"<b>Interpretation:</b> LEfSe analysis found no significant biomarkers with LDA &gt; {lda}. "
                f"Possible reasons: small between-group differences, insufficient sample size, or data sparsity. "
                f"Consider lowering the LDA threshold (e.g., 1.0) or trying other differential analysis methods."
            )
    
    return "<br/><br/>".join(interpretations) if interpretations else ""


def generate_comprehensive_report(
    session_id: str,
    export_path: str,
    analysis_results: list[dict],
    metadata: Optional[dict] = None,
    preprocessing_info: Optional[dict] = None,
) -> None:
    """Generate a comprehensive PDF report with embedded plots, methodology, and interpretations."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, KeepTogether, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    
    # Register Unicode fonts for CJK support
    _registered_fonts = {}
    for font_name, font_path in [
        ('ArialUnicode', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),
        ('STHeiti', '/System/Library/Fonts/STHeiti Light.ttc'),
    ]:
        try:
            if font_path.endswith('.ttc'):
                pdfmetrics.registerFont(TTFont(font_name, font_path, subfontIndex=0))
            else:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
            _registered_fonts[font_name] = True
            logger.info(f"Registered font: {font_name}")
            break  # Use the first successfully registered font
        except Exception as e:
            logger.warning(f"Failed to register font {font_name}: {e}")
            _registered_fonts[font_name] = False
    
    # Select font: prefer ArialUnicode, fallback to Helvetica
    unicode_font = 'ArialUnicode' if _registered_fonts.get('ArialUnicode') else 'Helvetica'
    unicode_font_bold = 'ArialUnicode' if _registered_fonts.get('ArialUnicode') else 'Helvetica-Bold'
    
    doc = SimpleDocTemplate(
        export_path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=colors.HexColor('#1e3a5f'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#4a6fa5'),
        spaceAfter=30,
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1e3a5f'),
        spaceAfter=12,
        spaceBefore=16,
        fontName='Helvetica-Bold',
        borderColor=colors.HexColor('#1e3a5f'),
        borderWidth=1,
        borderPadding=5,
        leftIndent=0,
    )
    method_style = ParagraphStyle(
        'Methodology',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#555555'),
        backColor=colors.HexColor('#f5f7fa'),
        leftIndent=10,
        rightIndent=10,
        spaceBefore=8,
        spaceAfter=8,
        leading=14,
        fontName=unicode_font,
    )
    interp_style = ParagraphStyle(
        'Interpretation',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#2c3e50'),
        leftIndent=10,
        rightIndent=10,
        spaceBefore=8,
        spaceAfter=8,
        leading=16,
        fontName=unicode_font,
    )
    caption_style = ParagraphStyle(
        'Caption',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER,
        spaceBefore=6,
        spaceAfter=12,
        italic=True,
    )
    
    story = []
    tmp_dir = tempfile.mkdtemp(prefix="meta2b_report_")
    
    try:
        # -- COVER PAGE --
        story.append(Spacer(1, 3*cm))
        story.append(Paragraph("Meta2bAnalyst", title_style))
        story.append(Paragraph("Comprehensive Microbiome Analysis Report", subtitle_style))
        story.append(HRFlowable(width="80%", thickness=1, color=colors.HexColor('#1e3a5f'), spaceBefore=20, spaceAfter=20, hAlign='CENTER'))
        
        # Session info
        story.append(Paragraph(f"<b>Session ID:</b> {session_id}", styles['Normal']))
        story.append(Paragraph(f"<b>Generated:</b> {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        if metadata:
            story.append(Paragraph(f"<b>Metadata:</b> {metadata.get('date', 'N/A')}", styles['Normal']))
        
        # Count analyses
        n_analyses = len(analysis_results)
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"<b>Total Analyses:</b> {n_analyses} modules", styles['Normal']))
        
        # Summary of analyses
        analysis_names = []
        for r in analysis_results:
            jt = r.get('test_method', r.get('job_type', 'Analysis'))
            analysis_names.append(jt)
        story.append(Paragraph(f"<b>Modules:</b> {', '.join(analysis_names)}", styles['Normal']))
        
        story.append(PageBreak())
        
        # -- TABLE OF CONTENTS --
        story.append(Paragraph("Table of Contents", section_style))
        for i, result in enumerate(analysis_results):
            jt = result.get('test_method', result.get('job_type', 'Analysis'))
            story.append(Paragraph(f"{i+1}. {jt.replace('_', ' ').title()}", styles['Normal']))
        story.append(PageBreak())
        
        # -- DATA PREPROCESSING SUMMARY --
        story.append(Paragraph("Data Preprocessing Summary", section_style))
        pre_items = []
        if preprocessing_info:
            if 'filtering' in preprocessing_info:
                pre_items.append(f"<b>Filtering:</b> {preprocessing_info['filtering']}")
            if 'normalization' in preprocessing_info:
                pre_items.append(f"<b>Normalization:</b> {preprocessing_info['normalization']}")
        if not pre_items:
            pre_items.append("<b>Preprocessing:</b> Default settings applied (no explicit filtering or normalization parameters recorded).")
        for item in pre_items:
            story.append(Paragraph(item, styles['Normal']))
            story.append(Spacer(1, 0.2*cm))
        
        # Show sample/feature counts if available
        for result in analysis_results:
            if 'n_samples' in result and 'n_features' in result:
                story.append(Paragraph(f"<b>Dataset Dimensions:</b> {result['n_samples']} samples × {result['n_features']} features", styles['Normal']))
                break
        story.append(PageBreak())
        
        # -- EACH ANALYSIS MODULE --
        for i, result in enumerate(analysis_results):
            job_type = result.get('test_method', result.get('job_type', 'Analysis'))
            display_name = job_type.replace('_', ' ').title()
            
            story.append(Paragraph(f"{i+1}. {display_name}", section_style))
            
            # Methodology
            method_text = _methodology_text(job_type)
            if method_text:
                story.append(Paragraph(method_text, method_style))
            
            # Parameters
            if 'parameters' in result:
                params = result['parameters']
                if params:
                    param_items = []
                    for k, v in params.items():
                        if isinstance(v, list):
                            v_str = ', '.join(str(x) for x in v)
                        else:
                            v_str = str(v)
                        param_items.append(f"<b>{k}:</b> {v_str}")
                    story.append(Paragraph(" | ".join(param_items), styles['Normal']))
                    story.append(Spacer(1, 0.3*cm))
            
            # Plot image
            plot_data = result.get('plot_data')
            if plot_data and plot_data.get('data'):
                img_path = _plotly_to_image(plot_data, tmp_dir, width=700, height=500, scale=2)
                if img_path and os.path.exists(img_path):
                    story.append(Image(img_path, width=16*cm, height=11.4*cm))
                    story.append(Paragraph(f"Figure {i+1}. {display_name} Visualization", caption_style))
            
            # Additional plots for random_forest (confusion matrix + ROC)
            if job_type == 'random_forest':
                cm_data = result.get('confusion_matrix')
                if cm_data and cm_data.get('labels') and cm_data.get('matrix'):
                    from app.services.analysis_engine import AnalysisEngine
                    engine = AnalysisEngine()
                    cm_plot = engine.plotly_confusion_matrix(cm_data)
                    cm_img = _plotly_to_image(cm_plot, tmp_dir, width=500, height=450, scale=2)
                    if cm_img and os.path.exists(cm_img):
                        story.append(Image(cm_img, width=11*cm, height=10*cm))
                        story.append(Paragraph(f"Figure {i+1}-a. Confusion Matrix", caption_style))
                
                roc_data = result.get('roc_curve')
                if roc_data and roc_data.get('type') != 'error':
                    from app.services.analysis_engine import AnalysisEngine
                    engine = AnalysisEngine()
                    roc_plot = engine.plotly_roc_curve(roc_data)
                    roc_img = _plotly_to_image(roc_plot, tmp_dir, width=500, height=450, scale=2)
                    if roc_img and os.path.exists(roc_img):
                        story.append(Image(roc_img, width=11*cm, height=10*cm))
                        story.append(Paragraph(f"Figure {i+1}-b. ROC Curve", caption_style))
            
            # Key statistics table
            if 'significant_features' in result:
                sig = result['significant_features']
                if isinstance(sig, list) and len(sig) > 0 and isinstance(sig[0], dict):
                    story.append(Paragraph("<b>Significant Features (Top 10):</b>", styles['Heading3']))
                    sig_top = sig[:10]
                    headers = list(sig_top[0].keys())[:8]  # Show up to 8 columns (feature, log2FC, pvalue, padj, mean_group1, mean_group2, std_group1, std_group2)
                    def _fmt_cell(row, h):
                        # Prefer display-formatted fields for p-values
                        if h == 'pvalue' and 'pvalue_display' in row:
                            return str(row.get('pvalue_display', ''))[:40]
                        if h == 'padj' and 'padj_display' in row:
                            return str(row.get('padj_display', ''))[:40]
                        if h in ('log2FC', 'mean_group1', 'mean_group2', 'std_group1', 'std_group2',
                                 'median_group1', 'median_group2'):
                            v = row.get(h, '')
                            try:
                                return f"{float(v):.3f}"[:40]
                            except (ValueError, TypeError):
                                return str(v)[:40]
                        return str(row.get(h, ''))[:40]
                    data = [headers] + [[_fmt_cell(row, h) for h in headers] for row in sig_top]
                    table = Table(data, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTSIZE', (0, 1), (-1, -1), 7),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ]))
                    story.append(KeepTogether(table))
                    story.append(Spacer(1, 0.3*cm))
            
            # Summary stats inline
            summary_items = []
            if 'accuracy' in result:
                summary_items.append(f"Accuracy: {result['accuracy']:.1%}")
            if 'cv_mean_accuracy' in result:
                summary_items.append(f"CV Accuracy: {result['cv_mean_accuracy']:.1%} ± {result.get('cv_std_accuracy', 0):.1%}")
            if 'n_samples' in result:
                summary_items.append(f"Samples: {result['n_samples']}")
            if 'n_features' in result:
                summary_items.append(f"Features: {result['n_features']}")
            if summary_items:
                story.append(Paragraph(" | ".join(summary_items), styles['Normal']))
                story.append(Spacer(1, 0.3*cm))
            
            # Alpha diversity summary table (only for alpha analysis)
            if job_type == 'alpha' and 'group_statistics' in result:
                gs = result['group_statistics']
                if gs and isinstance(gs, dict):
                    story.append(Paragraph("<b>Alpha Diversity Summary by Group:</b>", styles['Heading3']))
                    first_metric = list(gs.values())[0]
                    if not isinstance(first_metric, dict):
                        first_metric = {}
                    groups = [k for k in first_metric.keys() if k != 'statistical_test' and isinstance(k, str)]
                    headers = ['Metric'] + [f'{g} (mean±sd)' for g in groups] + ['Statistical Test', 'P-value', 'Significant']
                    data = [headers]
                    for metric, stats in gs.items():
                        if not isinstance(stats, dict):
                            continue
                        row = [metric]
                        for g in groups:
                            gstats = stats.get(g)
                            if not isinstance(gstats, dict):
                                row.append('N/A')
                                continue
                            mean = gstats.get('mean', 'N/A')
                            std = gstats.get('std', 'N/A')
                            row.append(f"{mean:.3f}±{std:.3f}" if isinstance(mean, (int, float)) and isinstance(std, (int, float)) else 'N/A')
                        stest = stats.get('statistical_test', {})
                        if isinstance(stest, dict):
                            row.append(stest.get('test', 'N/A'))
                            pval = stest.get('pvalue', 'N/A')
                            row.append(f"{pval:.4f}" if isinstance(pval, (int, float)) else str(pval))
                            sig = stest.get('significant', False)
                            row.append('Yes' if sig else 'No')
                        else:
                            row.extend(['N/A', 'N/A', 'No'])
                        data.append(row)
                    table = Table(data, repeatRows=1)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTSIZE', (0, 1), (-1, -1), 7),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ]))
                    story.append(KeepTogether(table))
                    story.append(Spacer(1, 0.3*cm))
            
            # Interpretation
            interp_text = _interpretation_text(result)
            if interp_text:
                story.append(Paragraph(interp_text, interp_style))
            
            story.append(PageBreak())
        
        # -- FOOTER / END --
        story.append(Paragraph("Report Generated by Meta2bAnalyst", styles['Normal']))
        story.append(Paragraph("For questions or issues, please refer to the documentation.", styles['Normal']))
        
        doc.build(story)
        logger.info(f"Generated comprehensive report: {export_path}")
        
    finally:
        # Clean up temp images
        for f in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(tmp_dir)
        except Exception:
            pass
