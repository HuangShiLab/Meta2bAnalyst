"""
Meta2bAnalyst - WGCNA Module (Weighted Gene Co-expression Network Analysis)
Adapted for microbiome co-occurrence network analysis.

Implements:
  1. Soft-thresholding adjacency construction (|correlation|^power)
  2. Topological Overlap Matrix (TOM) approximation
  3. Hierarchical clustering + dynamic tree cut for module detection
  4. Module-trait correlation heatmap
  5. Interactive Plotly dendrogram and heatmap visualization

Reference:
  Langfelder P, Horvath S. (2008) WGCNA: an R package for weighted
  correlation network analysis. BMC Bioinformatics 9:559.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from scipy.spatial.distance import squareform
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


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
        return _sanitize_json(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return _sanitize_json(obj.to_dict())
    return obj


def _soft_threshold(correlation: np.ndarray, power: int) -> np.ndarray:
    """Apply soft-thresholding to correlation matrix."""
    adjacency = np.abs(correlation) ** power
    np.fill_diagonal(adjacency, 0.0)
    return adjacency


def _tom_similarity(adjacency: np.ndarray) -> np.ndarray:
    """Compute Topological Overlap Matrix (TOM) approximation.

    TOM_ij = (sum_k(a_ik * a_kj) + a_ij) / (min(k_i, k_j) + 1 - a_ij)
    """
    n = adjacency.shape[0]
    k = adjacency.sum(axis=1)
    a2 = adjacency @ adjacency
    numerator = a2 + adjacency
    k_min = np.minimum.outer(k, k)
    denominator = k_min + 1.0 - adjacency
    with np.errstate(divide="ignore", invalid="ignore"):
        tom = numerator / denominator
    np.fill_diagonal(tom, 1.0)
    tom = np.clip(tom, 0.0, 1.0)
    return tom


def _tom_dissimilarity(tom: np.ndarray) -> np.ndarray:
    """Convert TOM similarity to dissimilarity for clustering."""
    return 1.0 - tom


def _dynamic_tree_cut(
    linkage_matrix: np.ndarray,
    min_cluster_size: int = 10,
    cut_height: Optional[float] = None,
    deep_split: int = 2,
) -> np.ndarray:
    """Simplified dynamic tree cut for hierarchical clustering."""
    n_obs = linkage_matrix.shape[0] + 1

    if cut_height is None:
        max_dist = linkage_matrix[:, 2].max()
        cut_height = max_dist * 0.75

    labels = fcluster(linkage_matrix, t=cut_height, criterion="distance")
    labels = labels - 1

    # Merge small clusters
    unique, counts = np.unique(labels, return_counts=True)
    small_clusters = unique[counts < min_cluster_size]

    if len(small_clusters) > 0:
        large_mask = ~np.isin(labels, small_clusters)
        if large_mask.sum() == 0:
            return labels

        for sc in small_clusters:
            sc_mask = labels == sc
            best_label = -1
            best_count = -1
            for lc in unique[~np.isin(unique, small_clusters)]:
                lc_count = (labels == lc).sum()
                if lc_count > best_count:
                    best_count = lc_count
                    best_label = lc
            if best_label >= 0:
                labels[sc_mask] = best_label

    unique_labels = np.unique(labels)
    label_map = {old: new for new, old in enumerate(unique_labels)}
    labels = np.array([label_map[l] for l in labels])
    return labels


def _merge_similar_modules(
    data: np.ndarray,
    labels: np.ndarray,
    cut_height: float = 0.25,
) -> np.ndarray:
    """Merge modules with similar eigengene profiles."""
    from sklearn.decomposition import PCA

    unique_labels = np.unique(labels)
    if len(unique_labels) <= 1:
        return labels

    eigengenes = {}
    for lab in unique_labels:
        mask = labels == lab
        if mask.sum() < 2:
            eigengenes[lab] = data[:, mask].flatten()
            continue
        mod_data = data[:, mask]
        pca = PCA(n_components=1)
        eg = pca.fit_transform(mod_data)[:, 0]
        eigengenes[lab] = eg

    n_modules = len(unique_labels)
    eg_corr = np.zeros((n_modules, n_modules))
    for i, lab_i in enumerate(unique_labels):
        for j, lab_j in enumerate(unique_labels):
            if i == j:
                eg_corr[i, j] = 1.0
            else:
                r = np.corrcoef(eigengenes[lab_i], eigengenes[lab_j])[0, 1]
                eg_corr[i, j] = r if not np.isnan(r) else 0.0

    merge_threshold = 1.0 - cut_height
    merged = labels.copy()

    for i in range(n_modules):
        for j in range(i + 1, n_modules):
            if eg_corr[i, j] > merge_threshold:
                lab_i, lab_j = unique_labels[i], unique_labels[j]
                size_i = (merged == lab_i).sum()
                size_j = (merged == lab_j).sum()
                if size_i >= size_j:
                    merged[merged == lab_j] = lab_i
                else:
                    merged[merged == lab_i] = lab_j

    unique_merged = np.unique(merged)
    label_map = {old: new for new, old in enumerate(unique_merged)}
    merged = np.array([label_map[l] for l in merged])
    return merged


def _compute_module_trait_correlation(
    data: np.ndarray,
    labels: np.ndarray,
    metadata: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compute module-trait correlations and p-values."""
    from sklearn.decomposition import PCA

    unique_labels = np.unique(labels)
    n_modules = len(unique_labels)

    eigengenes = {}
    for lab in unique_labels:
        mask = labels == lab
        if mask.sum() < 2:
            eigengenes[lab] = data[:, mask].flatten()
        else:
            mod_data = data[:, mask]
            pca = PCA(n_components=1)
            eg = pca.fit_transform(mod_data)[:, 0]
            eigengenes[lab] = eg

    numeric_cols = [c for c in metadata.columns if pd.api.types.is_numeric_dtype(metadata[c])]

    if len(numeric_cols) == 0:
        idx = [f"Module_{i}" for i in unique_labels]
        return pd.DataFrame(index=idx), pd.DataFrame(index=idx)

    corr_matrix = np.zeros((n_modules, len(numeric_cols)))
    pval_matrix = np.ones((n_modules, len(numeric_cols)))

    for i, lab in enumerate(unique_labels):
        eg = eigengenes[lab]
        for j, col in enumerate(numeric_cols):
            trait = metadata[col].values
            valid = ~(np.isnan(eg) | np.isnan(trait))
            if valid.sum() < 3:
                continue
            try:
                r, p = spearmanr(eg[valid], trait[valid])
                corr_matrix[i, j] = r if not np.isnan(r) else 0.0
                pval_matrix[i, j] = p if not np.isnan(p) else 1.0
            except Exception:
                pass

    module_names = [f"Module_{i}" for i in unique_labels]
    corr_df = pd.DataFrame(corr_matrix, index=module_names, columns=numeric_cols)
    pval_df = pd.DataFrame(pval_matrix, index=module_names, columns=numeric_cols)
    return corr_df, pval_df


def _get_module_colors(n_modules: int) -> List[str]:
    """Return a palette of distinct colors for modules."""
    colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
        "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
        "#393b79", "#637939", "#8c6d31", "#843c39", "#7b4173",
        "#de9ed6", "#3182bd", "#6baed6", "#9ecae1", "#c6dbef",
    ]
    if n_modules <= len(colors):
        return colors[:n_modules]
    rng = np.random.RandomState(42)
    extra = [
        f"#{rng.randint(0, 256):02x}{rng.randint(0, 256):02x}{rng.randint(0, 256):02x}"
        for _ in range(n_modules - len(colors))
    ]
    return colors + extra


def plotly_dendrogram_with_modules(
    linkage_matrix: np.ndarray,
    labels: np.ndarray,
    feature_names: List[str],
    width: int = 1000,
    height: int = 600,
) -> dict:
    """Generate a dendrogram plot with module color bars."""
    n_obs = linkage_matrix.shape[0] + 1
    colors = _get_module_colors(len(np.unique(labels)))

    dendro = dendrogram(linkage_matrix, no_plot=True, color_threshold=0)
    leaves = dendro["leaves"]

    ordered_labels = labels[leaves]
    ordered_names = [feature_names[i] for i in leaves]
    module_colors = [colors[l % len(colors)] for l in ordered_labels]

    icoord = np.array(dendro["icoord"])
    dcoord = np.array(dendro["dcoord"])

    edge_x = []
    edge_y = []
    for i in range(icoord.shape[0]):
        edge_x.extend([icoord[i, 0], icoord[i, 1], icoord[i, 2], icoord[i, 3], None])
        edge_y.extend([dcoord[i, 0], dcoord[i, 1], dcoord[i, 2], dcoord[i, 3], None])

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(color="#334155", width=1),
        hoverinfo="skip",
        showlegend=False,
    ))

    max_y = dcoord[:, [0, 3]].max() if dcoord.size > 0 else 1.0
    bar_height = max_y * 0.05

    fig.add_trace(go.Bar(
        x=list(range(n_obs)),
        y=[bar_height] * n_obs,
        marker=dict(color=module_colors),
        width=1.0,
        showlegend=False,
        hoverinfo="text",
        hovertext=[f"{name}<br>Module {ordered_labels[i]}" for i, name in enumerate(ordered_names)],
        opacity=1.0,
    ))

    fig.update_layout(
        title="WGCNA Dendrogram and Module Assignment",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, title="Distance"),
        plot_bgcolor="white",
        width=width,
        height=height,
        margin=dict(l=60, r=40, t=80, b=80),
        barmode="stack",
    )

    unique_modules = np.unique(ordered_labels)
    for mod in unique_modules:
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=12, color=colors[mod % len(colors)]),
            name=f"Module {mod}",
            showlegend=True,
        ))

    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
        ),
    )

    return fig.to_dict()


def plotly_module_trait_heatmap(
    corr_df: pd.DataFrame,
    pval_df: pd.DataFrame,
    width: int = 700,
    height: int = 500,
) -> dict:
    """Generate module-trait correlation heatmap."""
    if corr_df.empty or corr_df.shape[1] == 0:
        fig = go.Figure()
        fig.update_layout(
            title="Module-Trait Correlation (no numeric traits)",
            width=width, height=height,
        )
        return fig.to_dict()

    sig_text = pval_df.map(
        lambda p: "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    )
    hover_text = [
        [
            f"{corr_df.index[i]} × {corr_df.columns[j]}<br>"
            f"r = {corr_df.iloc[i, j]:.3f}<br>p = {pval_df.iloc[i, j]:.4f}"
            for j in range(corr_df.shape[1])
        ]
        for i in range(corr_df.shape[0])
    ]

    fig = go.Figure(data=go.Heatmap(
        z=corr_df.values,
        x=corr_df.columns.tolist(),
        y=corr_df.index.tolist(),
        colorscale="RdBu_r",
        zmid=0,
        zmin=-1,
        zmax=1,
        text=sig_text.values,
        texttemplate="%{text}",
        textfont=dict(size=10, color="black"),
        hoverongaps=False,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_text,
    ))

    fig.update_layout(
        title="Module-Trait Correlation",
        xaxis_title="Trait",
        yaxis_title="Module",
        template="plotly_white",
        width=width,
        height=height,
        margin=dict(l=100, r=40, t=60, b=80),
    )

    return fig.to_dict()


def plotly_module_adjacency_heatmap(
    adjacency: np.ndarray,
    labels: np.ndarray,
    feature_names: List[str],
    width: int = 700,
    height: int = 700,
) -> dict:
    """Generate adjacency matrix heatmap ordered by modules."""
    order = np.argsort(labels)
    adj_sorted = adjacency[np.ix_(order, order)]

    fig = go.Figure(data=go.Heatmap(
        z=adj_sorted,
        x=[feature_names[i] for i in order],
        y=[feature_names[i] for i in order],
        colorscale="YlOrRd",
        zmin=0,
        zmax=1,
        hoverongaps=False,
        hovertemplate="%{x} × %{y}<br>Adj: %{z:.3f}<extra></extra>",
        colorbar=dict(title="Adjacency", x=1.02),
    ))

    fig.update_layout(
        title="Adjacency Matrix (ordered by module)",
        template="plotly_white",
        width=width,
        height=height,
        xaxis=dict(showticklabels=False),
        yaxis=dict(showticklabels=False),
        margin=dict(l=40, r=100, t=60, b=40),
    )

    return fig.to_dict()


def run_wgcna(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    power: int = 6,
    min_module_size: int = 10,
    merge_cut_height: float = 0.25,
) -> Dict[str, Any]:
    """WGCNA-style co-occurrence network analysis for microbiome data.

    Steps:
        1. Compute pairwise correlation matrix (Spearman)
        2. Apply soft-thresholding: adjacency = |correlation|^power
        3. Compute TOM (topological overlap matrix) approximation
        4. Hierarchical clustering + dynamic tree cut for modules
        5. Merge similar modules

    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata DataFrame (samples x traits).
        power: Soft-thresholding power (default 6).
        min_module_size: Minimum module size (default 10).
        merge_cut_height: Dissimilarity threshold for merging modules
            (default 0.25, i.e., merge if eigengene correlation > 0.75).

    Returns:
        Dictionary with plot_data and statistics.
    """
    logger.info(
        f"Starting WGCNA: power={power}, min_module_size={min_module_size}, "
        f"merge_cut_height={merge_cut_height}"
    )

    data = df.values.T.astype(float)
    n_samples, n_features = data.shape
    feature_names = df.index.tolist()

    if n_features < 2:
        return {
            "error": "Need at least 2 features for WGCNA",
            "n_modules": 0,
            "plot_data": {},
            "statistics": {},
        }

    # Filter zero-variance features
    var_mask = df.var(axis=1) > 0
    if not var_mask.all():
        df = df.loc[var_mask]
        data = df.values.T.astype(float)
        n_features = data.shape[1]
        feature_names = df.index.tolist()
        logger.info(f"Removed {(~var_mask).sum()} zero-variance features")

    # 1. Spearman correlation
    logger.info("Computing Spearman correlation matrix")
    corr_mat = np.ones((n_features, n_features), dtype=float)

    for i in range(n_features):
        for j in range(i + 1, n_features):
            x, y = data[:, i], data[:, j]
            if np.std(x) == 0 or np.std(y) == 0:
                corr_mat[i, j] = corr_mat[j, i] = 0.0
                continue
            try:
                r, _ = spearmanr(x, y)
                corr_mat[i, j] = corr_mat[j, i] = float(r) if not np.isnan(r) else 0.0
            except Exception:
                corr_mat[i, j] = corr_mat[j, i] = 0.0

    np.fill_diagonal(corr_mat, 1.0)
    corr_mat = np.clip(corr_mat, -1.0, 1.0)

    # 2. Soft-thresholding
    logger.info(f"Applying soft-thresholding with power={power}")
    adjacency = _soft_threshold(corr_mat, power)

    # 3. TOM
    logger.info("Computing TOM")
    tom = _tom_similarity(adjacency)
    tom_dissim = _tom_dissimilarity(tom)

    # 4. Hierarchical clustering
    logger.info("Hierarchical clustering on TOM dissimilarity")
    dist_condensed = squareform(tom_dissim, checks=False)
    linkage_matrix = linkage(dist_condensed, method="average")

    # 5. Dynamic tree cut
    logger.info("Dynamic tree cut for module detection")
    labels = _dynamic_tree_cut(
        linkage_matrix,
        min_cluster_size=min_module_size,
        deep_split=2,
    )

    # 6. Merge similar modules
    logger.info("Merging similar modules")
    labels = _merge_similar_modules(data, labels, cut_height=merge_cut_height)

    n_modules = len(np.unique(labels))
    module_sizes = pd.Series(labels).value_counts().sort_index().to_dict()

    logger.info(f"WGCNA complete: {n_modules} modules detected")

    # Module-trait correlations
    trait_corr = None
    trait_pval = None
    if metadata_df is not None:
        common_samples = df.columns.intersection(metadata_df.index)
        if len(common_samples) > 0:
            meta_aligned = metadata_df.loc[common_samples]
            data_aligned = df[common_samples].values.T.astype(float)
            trait_corr, trait_pval = _compute_module_trait_correlation(
                data_aligned, labels, meta_aligned
            )

    # Plotly visualizations
    plot_data = {
        "dendrogram": plotly_dendrogram_with_modules(
            linkage_matrix, labels, feature_names
        ),
        "adjacency_heatmap": plotly_module_adjacency_heatmap(
            adjacency, labels, feature_names
        ),
    }

    if trait_corr is not None and not trait_corr.empty:
        plot_data["trait_heatmap"] = plotly_module_trait_heatmap(trait_corr, trait_pval)

    statistics = {
        "n_features": n_features,
        "n_modules": n_modules,
        "power": power,
        "min_module_size": min_module_size,
        "merge_cut_height": merge_cut_height,
        "module_sizes": {f"Module_{k}": int(v) for k, v in module_sizes.items()},
        "mean_connectivity": float(adjacency.sum(axis=1).mean()),
        "median_connectivity": float(np.median(adjacency.sum(axis=1))),
    }

    if trait_corr is not None and not trait_corr.empty:
        statistics["trait_correlations"] = _sanitize_json(trait_corr.to_dict())
        statistics["trait_pvalues"] = _sanitize_json(trait_pval.to_dict())

    module_membership = {}
    for lab in np.unique(labels):
        mask = labels == lab
        members = [feature_names[i] for i in range(n_features) if mask[i]]
        module_membership[f"Module_{lab}"] = members

    statistics["module_membership"] = module_membership

    return {
        "method": "wgcna",
        "plot_data": plot_data,
        "statistics": statistics,
    }
