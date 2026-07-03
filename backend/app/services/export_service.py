"""
Meta2bAnalyst - Export Service
Handles export of data, results, and plots in various formats.
"""
import json
import logging
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


def generate_comprehensive_report(
    session_id: str,
    export_path: str,
    analysis_results: list[dict],
    metadata: Optional[dict] = None,
) -> None:
    """Generate a comprehensive PDF report with all analysis results."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    
    doc = SimpleDocTemplate(export_path, pagesize=A4,
                           rightMargin=2*cm, leftMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30,
        alignment=TA_CENTER,
    )
    
    story = []
    
    # Cover page
    story.append(Paragraph("Meta2bAnalyst", title_style))
    story.append(Paragraph("Comprehensive Analysis Report", styles['Heading2']))
    story.append(Spacer(1, 1*cm))
    if metadata:
        story.append(Paragraph(f"Session: {session_id}", styles['Normal']))
        story.append(Paragraph(f"Date: {metadata.get('date', 'N/A')}", styles['Normal']))
    story.append(PageBreak())
    
    # For each analysis result
    for i, result in enumerate(analysis_results):
        story.append(Paragraph(f"{i+1}. {result.get('test_method', 'Analysis')} Results", styles['Heading2']))
        
        # Parameters
        if 'parameters' in result:
            story.append(Paragraph("Parameters:", styles['Heading3']))
            params = result['parameters']
            param_text = "<br/>".join([f"<b>{k}:</b> {v}" for k, v in params.items()])
            story.append(Paragraph(param_text, styles['Normal']))
        
        # Significant results table
        if 'significant_features' in result and result['significant_features']:
            story.append(Paragraph("Significant Features:", styles['Heading3']))
            sig = result['significant_features'][:30]
            if sig:
                headers = list(sig[0].keys())
                data = [headers] + [[str(row.get(h, '')[:50]) for h in headers] for row in sig]
                table = Table(data, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(KeepTogether(table))
        
        story.append(Spacer(1, 0.5*cm))
        
        # Summary statistics
        if 'summary' in result:
            story.append(Paragraph("Summary Statistics:", styles['Heading3']))
            summary = result['summary']
            summary_text = "<br/>".join([f"<b>{k}:</b> {v}" for k, v in summary.items()])
            story.append(Paragraph(summary_text, styles['Normal']))
        
        story.append(PageBreak())
    
    doc.build(story)
    logger.info(f"Generated comprehensive report: {export_path}")
