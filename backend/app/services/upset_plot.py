"""
UpSet-style intersection analysis
=================================
Computes set intersections of per-group feature sets (e.g. prevalent taxa per
group) and renders an UpSet-style intersection-size bar chart with Plotly.

Session feature tables are features x samples; group labels come from metadata.
"""
import logging
from itertools import combinations
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _membership_patterns(sets: Dict[str, set]) -> pd.DataFrame:
    """Aggregate features by their set-membership pattern (UpSet matrix).

    Returns a DataFrame with one row per observed non-empty membership
    pattern: the boolean membership per set, the intersection size, and the
    feature names (truncated for display).
    """
    names = list(sets)
    patterns: Dict[tuple, List[str]] = {}
    all_features = set().union(*sets.values()) if sets else set()
    for feat in all_features:
        pattern = tuple(feat in sets[n] for n in names)
        if any(pattern):
            patterns.setdefault(pattern, []).append(str(feat))

    rows = []
    for pattern, feats in patterns.items():
        rows.append({
            **{n: bool(m) for n, m in zip(names, pattern)},
            "degree": int(sum(pattern)),
            "size": len(feats),
            "features": feats[:50],
            "label": " & ".join(n for n, m in zip(names, pattern) if m),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("size", ascending=False).reset_index(drop=True)
    return out


def _plotly_upset(matrix: pd.DataFrame, set_sizes: Dict[str, int], top_n: int) -> Dict[str, Any]:
    """Render the top-N intersection sizes as an UpSet-style bar chart."""
    show = matrix.head(top_n)
    return {
        "data": [
            {
                "type": "bar",
                "x": show["label"].tolist(),
                "y": show["size"].tolist(),
                "marker": {"color": "#636EFA"},
                "hovertext": [
                    f"{row['label']}<br>{row['size']} features<br>"
                    + ", ".join(row["features"][:10])
                    + (" ..." if len(row["features"]) > 10 else "")
                    for _, row in show.iterrows()
                ],
                "hoverinfo": "text",
                "name": "Intersection size",
            }
        ],
        "layout": {
            "title": "UpSet plot - feature set intersections",
            "xaxis": {"title": "Intersection", "tickangle": -45},
            "yaxis": {"title": "Intersection size"},
            "annotations": [
                {
                    "text": " | ".join(f"{k}: {v}" for k, v in set_sizes.items()),
                    "xref": "paper", "yref": "paper", "x": 0, "y": 1.12,
                    "showarrow": False, "font": {"size": 11},
                }
            ],
            "margin": {"b": 140, "t": 80},
        },
    }


def run_upset_analysis(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    prevalence_threshold: float = 0.25,
    max_sets: int = 6,
    top_n: int = 20,
) -> Dict[str, Any]:
    """UpSet analysis of per-group prevalent features.

    Args:
        df: Feature table (features x samples).
        metadata_df: Sample metadata indexed by sample ID.
        group_column: Metadata column whose values define the sets.
        prevalence_threshold: A feature belongs to a group's set when detected
            (value > 0) in at least this fraction of the group's samples.
        max_sets: Keep the largest groups; more sets make intersections unreadable.
        top_n: Number of largest intersections to plot.

    Returns:
        Dict with plot_data, intersection matrix (as records), and per-set sizes.
    """
    if metadata_df is None or not group_column or group_column not in metadata_df.columns:
        return {
            "error": "UpSet analysis requires metadata with a group column to define the sets.",
            "plot_data": None,
        }

    common = df.columns.intersection(metadata_df.index)
    if len(common) < 2:
        return {
            "error": "Fewer than 2 samples overlap between the feature table and metadata.",
            "plot_data": None,
        }
    df = df[common]
    groups = metadata_df.loc[common, group_column].astype(str)

    counts = groups.value_counts()
    keep = counts.head(max_sets).index.tolist()
    if len(counts) > max_sets:
        logger.info("UpSet: keeping the %d largest groups out of %d", max_sets, len(counts))

    presence = df > 0
    sets: Dict[str, set] = {}
    for g in keep:
        mask = groups == g
        frac = presence.loc[:, mask].mean(axis=1)
        sets[str(g)] = set(frac[frac >= prevalence_threshold].index)

    if sum(len(s) for s in sets.values()) == 0:
        return {
            "error": "No feature passed the prevalence threshold in any group; "
                     "lower prevalence_threshold.",
            "plot_data": None,
        }

    matrix = _membership_patterns(sets)
    set_sizes = {k: len(v) for k, v in sets.items()}
    plot_data = _plotly_upset(matrix, set_sizes, top_n)

    return {
        "plot_data": plot_data,
        "intersections": matrix.drop(columns=["features"]).to_dict(orient="records"),
        "set_sizes": set_sizes,
        "prevalence_threshold": prevalence_threshold,
        "n_sets": len(sets),
        "statistics": {
            "n_sets": len(sets),
            "n_intersections": int(len(matrix)),
            "largest_intersection": int(matrix["size"].max()) if not matrix.empty else 0,
        },
    }
