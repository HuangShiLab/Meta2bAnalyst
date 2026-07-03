"""
Meta2bAnalyst - Plotly Generator Utility
Generate Plotly figures for various analysis types.
"""
import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def create_bar_chart(
    data: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: Optional[str] = None,
    title: str = "Bar Chart",
    x_label: str = "",
    y_label: str = "",
) -> Dict[str, Any]:
    """Create a Plotly bar chart figure."""
    traces = []
    if color_column and color_column in data.columns:
        groups = data[color_column].unique()
        for group in groups:
            group_data = data[data[color_column] == group]
            traces.append({
                "type": "bar",
                "name": str(group),
                "x": group_data[x_column].tolist(),
                "y": group_data[y_column].tolist(),
            })
    else:
        traces.append({
            "type": "bar",
            "x": data[x_column].tolist(),
            "y": data[y_column].tolist(),
        })
    
    return {
        "data": traces,
        "layout": {
            "title": title,
            "xaxis": {"title": x_label or x_column},
            "yaxis": {"title": y_label or y_column},
            "barmode": "group" if color_column else "relative",
        },
    }


def create_scatter_plot(
    data: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: Optional[str] = None,
    size_column: Optional[str] = None,
    title: str = "Scatter Plot",
    x_label: str = "",
    y_label: str = "",
) -> Dict[str, Any]:
    """Create a Plotly scatter plot figure."""
    traces = []
    if color_column and color_column in data.columns:
        groups = data[color_column].unique()
        for group in groups:
            group_data = data[data[color_column] == group]
            trace = {
                "type": "scatter",
                "mode": "markers",
                "name": str(group),
                "x": group_data[x_column].tolist(),
                "y": group_data[y_column].tolist(),
            }
            if size_column and size_column in group_data.columns:
                trace["marker"] = {"size": group_data[size_column].tolist()}
            traces.append(trace)
    else:
        trace = {
            "type": "scatter",
            "mode": "markers",
            "x": data[x_column].tolist(),
            "y": data[y_column].tolist(),
        }
        if size_column and size_column in data.columns:
            trace["marker"] = {"size": data[size_column].tolist()}
        traces.append(trace)
    
    return {
        "data": traces,
        "layout": {
            "title": title,
            "xaxis": {"title": x_label or x_column},
            "yaxis": {"title": y_label or y_column},
            "hovermode": "closest",
        },
    }


def create_pcoa_plot(
    coordinates: Dict[str, List[float]],
    variance_explained: List[float],
    group_metadata: Optional[Dict[str, str]] = None,
    title: str = "PCoA Plot",
) -> Dict[str, Any]:
    """Create a Plotly PCoA scatter plot."""
    traces = []
    
    if group_metadata:
        groups = {}
        for sample, coords in coordinates.items():
            group = group_metadata.get(sample, "Unknown")
            if group not in groups:
                groups[group] = {"x": [], "y": [], "z": [], "text": []}
            groups[group]["x"].append(coords[0] if len(coords) > 0 else 0)
            groups[group]["y"].append(coords[1] if len(coords) > 1 else 0)
            groups[group]["z"].append(coords[2] if len(coords) > 2 else 0)
            groups[group]["text"].append(sample)
        
        for group, data in groups.items():
            if len(data["z"]) > 0 and any(z != 0 for z in data["z"]):
                traces.append({
                    "type": "scatter3d",
                    "mode": "markers",
                    "name": str(group),
                    "x": data["x"],
                    "y": data["y"],
                    "z": data["z"],
                    "text": data["text"],
                })
            else:
                traces.append({
                    "type": "scatter",
                    "mode": "markers",
                    "name": str(group),
                    "x": data["x"],
                    "y": data["y"],
                    "text": data["text"],
                })
    else:
        x_vals = [coords[0] for coords in coordinates.values()]
        y_vals = [coords[1] for coords in coordinates.values()]
        z_vals = [coords[2] if len(coords) > 2 else 0 for coords in coordinates.values()]
        text = list(coordinates.keys())
        
        if any(z != 0 for z in z_vals):
            traces.append({
                "type": "scatter3d",
                "mode": "markers",
                "x": x_vals,
                "y": y_vals,
                "z": z_vals,
                "text": text,
            })
        else:
            traces.append({
                "type": "scatter",
                "mode": "markers",
                "x": x_vals,
                "y": y_vals,
                "text": text,
            })
    
    pc1_var = f"PC1 ({variance_explained[0]:.1f}%)" if variance_explained else "PC1"
    pc2_var = f"PC2 ({variance_explained[1]:.1f}%)" if len(variance_explained) > 1 else "PC2"
    
    return {
        "data": traces,
        "layout": {
            "title": title,
            "xaxis": {"title": pc1_var},
            "yaxis": {"title": pc2_var},
            "hovermode": "closest",
        },
    }


def create_heatmap_plot(
    matrix: pd.DataFrame,
    row_labels: List[str],
    col_labels: List[str],
    group_metadata: Optional[Dict[str, str]] = None,
    title: str = "Heatmap",
) -> Dict[str, Any]:
    """Create a Plotly heatmap figure."""
    trace = {
        "type": "heatmap",
        "z": matrix.values.tolist(),
        "x": col_labels,
        "y": row_labels,
        "colorscale": "Viridis",
    }
    
    layout = {
        "title": title,
        "xaxis": {"title": "Samples", "tickangle": -45},
        "yaxis": {"title": "Features"},
    }
    
    if group_metadata:
        # Add group annotations above columns
        # This is a simplified implementation
        pass
    
    return {
        "data": [trace],
        "layout": layout,
    }


def create_box_plot(
    data: pd.DataFrame,
    value_column: str,
    group_column: str,
    title: str = "Box Plot",
) -> Dict[str, Any]:
    """Create a Plotly box plot figure."""
    traces = []
    groups = data[group_column].unique()
    for group in groups:
        group_data = data[data[group_column] == group]
        traces.append({
            "type": "box",
            "name": str(group),
            "y": group_data[value_column].tolist(),
        })
    
    return {
        "data": traces,
        "layout": {
            "title": title,
            "yaxis": {"title": value_column},
            "boxmode": "group",
        },
    }


def create_volcano_plot(
    results_df: pd.DataFrame,
    log2fc_column: str = "log2_fold_change",
    pvalue_column: str = "pvalue",
    title: str = "Volcano Plot",
) -> Dict[str, Any]:
    """Create a Plotly volcano plot for differential abundance."""
    # Calculate -log10(pvalue)
    results_df = results_df.copy()
    results_df["neg_log10_pvalue"] = -np.log10(results_df[pvalue_column].replace(0, 1e-300))
    
    # Color points based on significance
    def get_color(row):
        if row[pvalue_column] < 0.05 and abs(row[log2fc_column]) > 1:
            return "red" if row[log2fc_column] > 0 else "blue"
        elif row[pvalue_column] < 0.05:
            return "orange"
        else:
            return "gray"
    
    results_df["color"] = results_df.apply(get_color, axis=1)
    
    trace = {
        "type": "scatter",
        "mode": "markers",
        "x": results_df[log2fc_column].tolist(),
        "y": results_df["neg_log10_pvalue"].tolist(),
        "text": results_df.get("feature", results_df.index).tolist(),
        "marker": {
            "color": results_df["color"].tolist(),
            "size": 8,
        },
    }
    
    return {
        "data": [trace],
        "layout": {
            "title": title,
            "xaxis": {"title": "Log2 Fold Change"},
            "yaxis": {"title": "-Log10 P-value"},
            "shapes": [
                {
                    "type": "line",
                    "x0": -1, "x1": -1, "y0": 0, "y1": results_df["neg_log10_pvalue"].max(),
                    "line": {"color": "gray", "width": 1, "dash": "dash"},
                },
                {
                    "type": "line",
                    "x0": 1, "x1": 1, "y0": 0, "y1": results_df["neg_log10_pvalue"].max(),
                    "line": {"color": "gray", "width": 1, "dash": "dash"},
                },
                {
                    "type": "line",
                    "x0": results_df[log2fc_column].min(), "x1": results_df[log2fc_column].max(),
                    "y0": -np.log10(0.05), "y1": -np.log10(0.05),
                    "line": {"color": "gray", "width": 1, "dash": "dash"},
                },
            ],
        },
    }


def plot_to_json(fig: Dict[str, Any]) -> str:
    """Convert Plotly figure to JSON string."""
    return json.dumps(fig, indent=2)
