"""
Meta2bAnalyst - Export Service
Handles export of data, results, and plots in various formats.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

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
        # Requires reportlab or similar; placeholder
        raise NotImplementedError("PDF export requires additional libraries (reportlab, weasyprint)")
    
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
    
    if format in ("png", "svg", "jpg"):
        # Plotly static export requires kaleido
        try:
            import plotly.io as pio
            # Load plot JSON from results directory
            results_dir = Path("./uploads") / session_id / "results"
            plot_files = list(results_dir.glob("*.json")) if results_dir.exists() else []
            if plot_files:
                with open(plot_files[0]) as f:
                    fig_data = json.load(f)
                # This is a simplified placeholder; actual export would require
                # converting plotly figure to image
                logger.warning("Static image export requires kaleido: pip install kaleido")
        except ImportError:
            logger.warning("plotly or kaleido not installed for image export")
    
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
