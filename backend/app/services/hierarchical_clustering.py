"""
Meta2bAnalyst - Hierarchical Clustering + Heat Tree Module
Implements hierarchical clustering of samples and features with interactive
heatmap + dendrogram visualization (Heat Tree).

References:
  - Ward 1963, J Am Stat Assoc 58:236-244
  - Eisen et al. 1998, Proc Natl Acad Sci USA 95:14863-14868
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage, to_tree
from scipy.spatial.distance import braycurtis, pdist, squareform
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=RuntimeWarning)


def _sanitize_json(obj: Any) -> Any:
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return _sanitize_json(obj.to_dict(orient='records'))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj


# ─────────────────────────────── Hierarchical Clustering Core

def compute_linkage(
    df: pd.DataFrame,
    axis: str = "sample",
    metric: str = "braycurtis",
    method: str = "ward",
) -> Tuple[np.ndarray, pd.DataFrame, List[str]]:
    """Compute hierarchical linkage for samples or features.
    
    Args:
        df: Feature table (features x samples).
        axis: 'sample' (cluster samples) or 'feature' (cluster features).
        metric: Distance metric ('braycurtis', 'euclidean', 'correlation').
        method: Linkage method ('ward', 'complete', 'average', 'single').
        
    Returns:
        linkage_matrix: (n-1) x 4 linkage matrix from scipy.
        reordered_data: DataFrame reordered by clustering.
        labels: Ordered labels.
    """
    if axis == "sample":
        # Transpose to get samples as rows
        data = df.T.values
        labels = list(df.columns)
    else:
        data = df.values
        labels = list(df.index)
    
    # Compute distance matrix
    if metric == "braycurtis":
        # Bray-Curtis requires non-negative values
        data = np.abs(data)
        dist_array = pdist(data, metric="braycurtis")
    elif metric == "correlation":
        dist_array = pdist(data, metric="correlation")
    else:
        dist_array = pdist(data, metric=metric)
    
    # Handle NaN distances
    dist_array = np.nan_to_num(dist_array, nan=0.0, posinf=1.0, neginf=0.0)
    
    # Compute linkage
    if method == "ward":
        # Ward requires Euclidean distances
        linkage_matrix = linkage(dist_array, method="ward")
    else:
        linkage_matrix = linkage(dist_array, method=method)
    
    # Get optimal leaf ordering
    from scipy.cluster.hierarchy import leaves_list, optimal_leaf_ordering
    try:
        optimal_linkage = optimal_leaf_ordering(linkage_matrix, dist_array)
        leaf_order = leaves_list(optimal_linkage)
    except Exception:
        leaf_order = leaves_list(linkage_matrix)
    
    # Reorder data
    ordered_labels = [labels[i] for i in leaf_order]
    
    if axis == "sample":
        reordered_data = df[ordered_labels]
    else:
        reordered_data = df.loc[ordered_labels]
    
    logger.info(f"Hierarchical clustering ({axis}): metric={metric}, method={method}, n={len(labels)}")
    
    return linkage_matrix, reordered_data, ordered_labels


def extract_dendrogram_data(linkage_matrix: np.ndarray, labels: List[str]) -> Dict[str, Any]:
    """Extract dendrogram coordinates for Plotly visualization.
    
    Args:
        linkage_matrix: Scipy linkage matrix.
        labels: Leaf labels.
        
    Returns:
        Dict with x, y coordinates and leaf order for dendrogram plotting.
    """
    # Get dendrogram layout
    dendro = dendrogram(linkage_matrix, labels=labels, no_plot=True)
    
    # Extract coordinates
    icoord = dendro['icoord']
    dcoord = dendro['dcoord']
    
    # Convert to plotly format
    x_coords = []
    y_coords = []
    
    for i, (xs, ys) in enumerate(zip(icoord, dcoord)):
        x_coords.extend(xs + [None])
        y_coords.extend(ys + [None])
    
    return {
        "x": x_coords,
        "y": y_coords,
        "leaves": dendro['leaves'],
        "ivl": dendro['ivl'],
    }


def assign_clusters(
    linkage_matrix: np.ndarray,
    labels: List[str],
    n_clusters: int = 3,
) -> pd.DataFrame:
    """Assign cluster labels based on hierarchical clustering.
    
    Args:
        linkage_matrix: Scipy linkage matrix.
        labels: Leaf labels.
        n_clusters: Number of clusters to extract.
        
    Returns:
        DataFrame with label and cluster assignment.
    """
    cluster_ids = fcluster(linkage_matrix, n_clusters, criterion="maxclust")
    
    return pd.DataFrame({
        "label": labels,
        "cluster": cluster_ids,
    })


# ─────────────────────────────── Heat Tree Visualization

def plotly_heat_tree(
    df: pd.DataFrame,
    sample_linkage: Optional[np.ndarray] = None,
    feature_linkage: Optional[np.ndarray] = None,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    top_n_features: int = 50,
    normalize: str = "row",
    colorscale: str = "YlOrRd",
) -> dict:
    """Generate interactive Heat Tree (heatmap + dendrograms) using Plotly.
    
    Args:
        df: Feature table (features x samples).
        sample_linkage: Optional sample linkage matrix for column dendrogram.
        feature_linkage: Optional feature linkage matrix for row dendrogram.
        metadata_df: Optional metadata for sample group colors.
        group_column: Column for group annotations.
        top_n_features: Number of top features to display.
        normalize: 'row', 'column', or 'none'.
        colorscale: Plotly colorscale name.
        
    Returns:
        Plotly figure JSON dict.
    """
    # Select top features by mean abundance
    if len(df.index) > top_n_features:
        top_feats = df.mean(axis=1).sort_values(ascending=False).head(top_n_features).index
        df_plot = df.loc[top_feats]
    else:
        df_plot = df.copy()
    
    # Normalize
    if normalize == "row":
        df_plot = df_plot.div(df_plot.sum(axis=1), axis=0)
    elif normalize == "column":
        df_plot = df_plot.div(df_plot.sum(axis=0), axis=1)
    
    # Reorder if linkage provided
    if feature_linkage is not None:
        from scipy.cluster.hierarchy import leaves_list
        try:
            feat_order = leaves_list(feature_linkage)
            df_plot = df_plot.iloc[feat_order]
        except Exception:
            pass
    
    if sample_linkage is not None:
        from scipy.cluster.hierarchy import leaves_list
        try:
            sample_order = leaves_list(sample_linkage)
            df_plot = df_plot.iloc[:, sample_order]
        except Exception:
            pass
    
    # Create heatmap
    fig = go.Figure(data=go.Heatmap(
        z=df_plot.values,
        x=list(df_plot.columns),
        y=list(df_plot.index),
        colorscale=colorscale,
        colorbar=dict(title="Abundance"),
        hovertemplate="<b>%{y}</b><br>Sample: %{x}<br>Abundance: %{z:.4f}<extra></extra>",
    ))
    
    # Add sample group annotations if metadata provided
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        groups = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                  for s in df_plot.columns]
        unique_groups = sorted(set(groups))
        
        # Create color mapping
        color_map = {
            g: ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"][i % 10]
            for i, g in enumerate(unique_groups)
        }
        
        group_colors = [color_map[g] for g in groups]
        
        # Add annotation bar above heatmap
        for i, (sample, group, color) in enumerate(zip(df_plot.columns, groups, group_colors)):
            fig.add_trace(go.Scatter(
                x=[sample],
                y=[1.02],
                mode="markers",
                marker=dict(size=15, color=color, symbol="square"),
                showlegend=False,
                hovertemplate=f"Sample: {sample}<br>Group: {group}<extra></extra>",
            ))
    
    fig.update_layout(
        title="Hierarchical Clustering Heatmap (Heat Tree)",
        xaxis_title="Sample",
        yaxis_title="Feature",
        template="plotly_white",
        height=max(500, len(df_plot.index) * 15),
        width=max(600, len(df_plot.columns) * 40),
        margin=dict(l=150, r=40, t=80, b=100),
    )
    
    return fig.to_dict()


def plotly_dendrogram(
    linkage_matrix: np.ndarray,
    labels: List[str],
    orientation: str = "top",
    title: str = "Dendrogram",
) -> dict:
    """Generate dendrogram plot using Plotly.
    
    Args:
        linkage_matrix: Scipy linkage matrix.
        labels: Leaf labels.
        orientation: 'top', 'bottom', 'left', or 'right'.
        title: Plot title.
        
    Returns:
        Plotly figure JSON dict.
    """
    dendro_data = extract_dendrogram_data(linkage_matrix, labels)
    
    fig = go.Figure(data=go.Scatter(
        x=dendro_data["x"],
        y=dendro_data["y"],
        mode="lines",
        line=dict(color="#2ca02c", width=1),
        hoverinfo="skip",
    ))
    
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=300 if orientation in ["top", "bottom"] else 500,
        width=600 if orientation in ["top", "bottom"] else 300,
        xaxis=dict(showticklabels=False, zeroline=False),
        yaxis=dict(showticklabels=False, zeroline=False),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    
    return fig.to_dict()


def plotly_cluster_heatmap(
    df: pd.DataFrame,
    cluster_result: pd.DataFrame,
    top_n: int = 30,
) -> dict:
    """Generate heatmap colored by cluster assignment.
    
    Args:
        df: Feature table.
        cluster_result: DataFrame with label and cluster columns.
        top_n: Number of top features.
        
    Returns:
        Plotly figure JSON dict.
    """
    if len(df.index) > top_n:
        top_feats = df.mean(axis=1).sort_values(ascending=False).head(top_n).index
        df_plot = df.loc[top_feats]
    else:
        df_plot = df.copy()
    
    # Normalize per row
    df_plot = df_plot.div(df_plot.sum(axis=1), axis=0)
    
    fig = px.imshow(
        df_plot.values,
        x=list(df_plot.columns),
        y=list(df_plot.index),
        color_continuous_scale="Viridis",
        aspect="auto",
        title="Clustered Feature Heatmap",
    )
    
    fig.update_layout(
        xaxis_title="Sample",
        yaxis_title="Feature",
        template="plotly_white",
        height=max(400, len(df_plot.index) * 15),
        margin=dict(l=150, r=40, t=60, b=100),
    )
    
    return fig.to_dict()


# ─────────────────────────────── Silhouette Analysis

def compute_silhouette_scores(
    df: pd.DataFrame,
    linkage_matrix: np.ndarray,
    max_clusters: int = 10,
) -> pd.DataFrame:
    """Compute silhouette scores for different numbers of clusters.
    
    Args:
        df: Feature table (features x samples).
        linkage_matrix: Sample linkage matrix.
        max_clusters: Maximum number of clusters to test.
        
    Returns:
        DataFrame with n_clusters and silhouette_score.
    """
    from sklearn.metrics import silhouette_score
    
    data = df.T.values  # samples x features
    
    results = []
    for k in range(2, min(max_clusters + 1, len(data))):
        cluster_ids = fcluster(linkage_matrix, k, criterion="maxclust")
        
        if len(np.unique(cluster_ids)) < 2:
            continue
        
        try:
            score = silhouette_score(data, cluster_ids, metric="euclidean")
            results.append({"n_clusters": k, "silhouette_score": score})
        except Exception:
            continue
    
    return pd.DataFrame(results)


def plotly_silhouette(silhouette_df: pd.DataFrame) -> dict:
    """Generate silhouette score plot.
    
    Args:
        silhouette_df: Result from compute_silhouette_scores().
        
    Returns:
        Plotly figure JSON dict.
    """
    if silhouette_df.empty:
        return go.Figure().update_layout(title="No silhouette data").to_dict()
    
    fig = go.Figure(data=go.Scatter(
        x=silhouette_df["n_clusters"],
        y=silhouette_df["silhouette_score"],
        mode="lines+markers",
        marker=dict(size=10, color="#2ca02c"),
        line=dict(color="#2ca02c"),
    ))
    
    # Highlight best score
    best_idx = silhouette_df["silhouette_score"].idxmax()
    best_k = silhouette_df.loc[best_idx, "n_clusters"]
    best_score = silhouette_df.loc[best_idx, "silhouette_score"]
    
    fig.add_trace(go.Scatter(
        x=[best_k],
        y=[best_score],
        mode="markers",
        marker=dict(size=15, color="#d62728", symbol="star"),
        name=f"Best: k={best_k}",
    ))
    
    fig.update_layout(
        title="Silhouette Analysis for Optimal Cluster Number",
        xaxis_title="Number of Clusters",
        yaxis_title="Silhouette Score",
        template="plotly_white",
        height=400,
        showlegend=True,
    )
    
    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_hierarchical_clustering(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run complete hierarchical clustering and heat tree analysis.
    
    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata DataFrame.
        parameters: Dict with keys:
            - cluster_axis: 'sample', 'feature', or 'both' (default 'both')
            - distance_metric: 'braycurtis', 'euclidean', 'correlation' (default 'braycurtis')
            - linkage_method: 'ward', 'complete', 'average', 'single' (default 'ward')
            - n_clusters: int (default 3)
            - top_n_features: int for heatmap (default 50)
            - group_column: metadata column for coloring
            - compute_silhouette: bool (default True)
            
    Returns:
        Dict with clustering results, cluster assignments, silhouette scores, and plots.
    """
    params = parameters or {}
    cluster_axis = params.get("cluster_axis", "both")
    distance_metric = params.get("distance_metric", "braycurtis")
    linkage_method = params.get("linkage_method", "ward")
    n_clusters = params.get("n_clusters", 3)
    top_n_features = params.get("top_n_features", 50)
    group_column = params.get("group_column")
    compute_sil = params.get("compute_silhouette", True)
    
    logger.info(f"Starting hierarchical clustering: axis={cluster_axis}, metric={distance_metric}, method={linkage_method}")
    
    # Sample clustering
    sample_linkage = None
    sample_clusters = None
    sample_order = None
    
    if cluster_axis in ["sample", "both"]:
        sample_linkage, sample_reordered, sample_order = compute_linkage(
            df, axis="sample", metric=distance_metric, method=linkage_method
        )
        sample_clusters = assign_clusters(sample_linkage, sample_order, n_clusters)
    
    # Feature clustering
    feature_linkage = None
    feature_clusters = None
    feature_order = None
    
    if cluster_axis in ["feature", "both"]:
        feature_linkage, feature_reordered, feature_order = compute_linkage(
            df, axis="feature", metric="correlation", method=linkage_method
        )
        feature_clusters = assign_clusters(feature_linkage, feature_order, n_clusters)
    
    # Silhouette analysis
    silhouette_df = pd.DataFrame()
    if compute_sil and sample_linkage is not None:
        silhouette_df = compute_silhouette_scores(df, sample_linkage, max_clusters=min(10, len(df.columns) - 1))
    
    # Generate plots
    plots = {
        "heat_tree": plotly_heat_tree(
            df,
            sample_linkage=sample_linkage,
            feature_linkage=feature_linkage,
            metadata_df=metadata_df,
            group_column=group_column,
            top_n_features=top_n_features,
        ),
    }
    
    if sample_linkage is not None:
        plots["sample_dendrogram"] = plotly_dendrogram(
            sample_linkage, sample_order, orientation="top", title="Sample Clustering Dendrogram"
        )
    
    if feature_linkage is not None:
        plots["feature_dendrogram"] = plotly_dendrogram(
            feature_linkage, feature_order, orientation="left", title="Feature Clustering Dendrogram"
        )
    
    if not silhouette_df.empty:
        plots["silhouette_plot"] = plotly_silhouette(silhouette_df)
    
    # Build result
    result = _sanitize_json({
        "cluster_axis": cluster_axis,
        "distance_metric": distance_metric,
        "linkage_method": linkage_method,
        "n_clusters": n_clusters,
        "sample_clusters": sample_clusters.to_dict(orient="records") if sample_clusters is not None else [],
        "feature_clusters": feature_clusters.to_dict(orient="records") if feature_clusters is not None else [],
        "silhouette_scores": silhouette_df.to_dict(orient="records") if not silhouette_df.empty else [],
        "plots": plots,
    })
    
    logger.info("Hierarchical clustering complete")
    return result
