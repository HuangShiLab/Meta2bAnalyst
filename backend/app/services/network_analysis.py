"""
Meta2bAnalyst - Network Analysis Module (SparCC & Spearman)
Implements SparCC correlation for compositional microbiome data, network
construction, topology statistics, and interactive Plotly visualization.

Reference:
    Friedman J, Alm EJ. (2012) Inferring Correlation Networks from Genomic
    Survey Data. PLoS Computational Biology 8(9): e1002687.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# ─────────────────────────────── SparCC Implementation


def _compute_variation_matrix(log_prop: np.ndarray) -> np.ndarray:
    """Compute pairwise log-ratio variance matrix T_ij = var(log(xi/xj)).

    Args:
        log_prop: Array of shape (n_samples, n_features) with log-proportions.

    Returns:
        T: (n_features, n_features) variance matrix.
    """
    n_samples, n_features = log_prop.shape
    T = np.zeros((n_features, n_features), dtype=float)
    for i in range(n_features):
        for j in range(i + 1, n_features):
            lr = log_prop[:, i] - log_prop[:, j]
            var_lr = np.var(lr, ddof=1) if n_samples > 1 else 0.0
            T[i, j] = var_lr
            T[j, i] = var_lr
    return T


def sparcc_correlation(
    counts: pd.DataFrame,
    iterations: int = 20,
    exclude_threshold: float = 0.1,
) -> pd.DataFrame:
    """Compute SparCC correlation matrix for compositional data.

    This is a simplified but functional pure-Python implementation of the
    SparCC algorithm. It estimates basis correlations by iteratively
    excluding strongly correlated pairs from variance estimation.

    Args:
        counts: Feature table (features x samples) with raw or normalized counts.
        iterations: Number of iterative refinement steps for variance estimation.
        exclude_threshold: Correlation magnitude threshold for excluding pairs
            from variance re-estimation (default 0.1 as in original SparCC).

    Returns:
        DataFrame with features as both index and columns containing
        Pearson-like basis correlations.
    """
    # Transpose to (samples, features) and add pseudocount
    data = counts.values.T.astype(float)
    n_samples, n_features = data.shape

    if n_features < 2:
        return pd.DataFrame(np.ones((1, 1)), index=counts.index, columns=counts.index)

    # Convert to proportions and log-transform
    prop = data / (data.sum(axis=1, keepdims=True) + 1e-10)
    # Add small pseudocount to avoid log(0)
    prop = prop + 1e-10
    log_prop = np.log(prop)

    # Compute variation matrix T_ij = var(log(xi/xj))
    T = _compute_variation_matrix(log_prop)

    # Initial variance estimate: V_i = mean_j(T_ij) / 2
    V = np.mean(T, axis=1) / 2.0

    # Iterative refinement
    for _ in range(iterations):
        # Estimate covariance from current variances
        # C_ij = (V_i + V_j - T_ij) / 2
        V_mat = np.add.outer(V, V)  # V_i + V_j
        C = (V_mat - T) / 2.0
        np.fill_diagonal(C, V)

        # Compute correlation to identify strong correlations to exclude
        std = np.sqrt(V)
        std_outer = np.outer(std, std)
        with np.errstate(divide='ignore', invalid='ignore'):
            corr = C / (std_outer + 1e-15)
        np.fill_diagonal(corr, 1.0)

        # Exclude pairs with |correlation| >= exclude_threshold from variance estimation
        exclude_mask = np.abs(corr) >= exclude_threshold
        np.fill_diagonal(exclude_mask, False)

        # Re-estimate variances using only non-excluded pairs
        for i in range(n_features):
            valid = ~exclude_mask[i, :]
            valid[i] = False  # exclude self
            if valid.sum() > 0:
                V[i] = np.mean(T[i, valid]) / 2.0
            # else: keep previous estimate

    # Final covariance and correlation
    V_mat = np.add.outer(V, V)
    C = (V_mat - T) / 2.0
    np.fill_diagonal(C, V)

    std = np.sqrt(V)
    std_outer = np.outer(std, std)
    with np.errstate(divide='ignore', invalid='ignore'):
        corr = C / (std_outer + 1e-15)
    np.fill_diagonal(corr, 1.0)

    # Clip to [-1, 1] to handle numerical noise
    corr = np.clip(corr, -1.0, 1.0)

    corr_df = pd.DataFrame(corr, index=counts.index, columns=counts.index)
    return corr_df


def sparcc_pvalues(
    counts: pd.DataFrame,
    corr_df: pd.DataFrame,
    n_permutations: int = 100,
) -> pd.DataFrame:
    """Compute approximate p-values for SparCC via permutation testing.

    Uses row permutation to generate a null distribution of the maximum
    absolute correlation. For computational efficiency, this is a simplified
    permutation test that permutes sample labels for each feature independently.

    Args:
        counts: Feature table (features x samples).
        corr_df: SparCC correlation matrix from sparcc_correlation().
        n_permutations: Number of permutations for null distribution.

    Returns:
        DataFrame of p-values with same shape as corr_df.
    """
    n_features = len(corr_df)
    pval_matrix = np.ones((n_features, n_features), dtype=float)

    if n_permutations <= 0:
        return pd.DataFrame(pval_matrix, index=corr_df.index, columns=corr_df.columns)

    # For efficiency, we use a simplified permutation: permute samples for each feature
    # and compute the fraction of permutations where |perm_corr| >= |obs_corr|
    # We'll use a subset of permutations for speed.
    n_perm = min(n_permutations, 200)
    data = counts.values.T.astype(float)  # (samples, features)
    n_samples = data.shape[0]

    if n_samples < 5:
        logger.warning("Too few samples for reliable SparCC permutation p-values")
        return pd.DataFrame(pval_matrix, index=corr_df.index, columns=corr_df.columns)

    # To speed up, we'll estimate p-values using the Fisher z-transform approximation
    # adjusted for compositional bias, which is much faster than full permutation.
    # For a more rigorous test, users should increase n_permutations.
    obs_corr = corr_df.values.copy()
    np.fill_diagonal(obs_corr, 0)

    # Simple permutation: shuffle rows for each feature independently and recompute
    # We do this in a vectorized way where possible.
    perm_counts = np.zeros_like(obs_corr)
    rng = np.random.default_rng(42)

    for _ in range(n_perm):
        perm_data = rng.permuted(data, axis=0)
        # Fast correlation via standardized values
        # Compute log-proportions on permuted data
        perm_prop = perm_data / (perm_data.sum(axis=1, keepdims=True) + 1e-10) + 1e-10
        perm_log = np.log(perm_prop)
        # Center
        perm_log_c = perm_log - perm_log.mean(axis=0, keepdims=True)
        # Std
        perm_std = np.std(perm_log, axis=0, ddof=1)
        # Correlation
        with np.errstate(divide='ignore', invalid='ignore'):
            perm_corr = (perm_log_c.T @ perm_log_c) / ((n_samples - 1) * np.outer(perm_std, perm_std) + 1e-15)
        perm_corr = np.clip(perm_corr, -1, 1)
        np.fill_diagonal(perm_corr, 0)
        perm_counts += (np.abs(perm_corr) >= np.abs(obs_corr)).astype(int)

    pvals = (perm_counts + 1) / (n_perm + 1)
    np.fill_diagonal(pvals, 1.0)

    return pd.DataFrame(pvals, index=corr_df.index, columns=corr_df.columns)


# ─────────────────────────────── Spearman Fallback


def spearman_correlation(counts: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compute Spearman rank correlation and p-values.

    Args:
        counts: Feature table (features x samples).

    Returns:
        Tuple of (correlation DataFrame, p-value DataFrame).
    """
    # Transpose to samples x features for scipy
    data = counts.values.T
    n_features = counts.shape[0]

    corr_mat = np.ones((n_features, n_features), dtype=float)
    pval_mat = np.ones((n_features, n_features), dtype=float)

    for i in range(n_features):
        for j in range(i + 1, n_features):
            # Handle all-zeros or constant features
            x, y = data[:, i], data[:, j]
            if np.std(x) == 0 or np.std(y) == 0:
                corr_mat[i, j] = corr_mat[j, i] = 0.0
                pval_mat[i, j] = pval_mat[j, i] = 1.0
                continue
            try:
                r, p = spearmanr(x, y)
                corr_mat[i, j] = corr_mat[j, i] = float(r)
                pval_mat[i, j] = pval_mat[j, i] = float(p)
            except Exception:
                corr_mat[i, j] = corr_mat[j, i] = 0.0
                pval_mat[i, j] = pval_mat[j, i] = 1.0

    corr_df = pd.DataFrame(corr_mat, index=counts.index, columns=counts.index)
    pval_df = pd.DataFrame(pval_mat, index=counts.index, columns=counts.index)
    return corr_df, pval_df


# ─────────────────────────────── Network Construction


def build_network(
    corr_df: pd.DataFrame,
    pval_df: pd.DataFrame,
    threshold: float = 0.3,
    pvalue_threshold: float = 0.05,
) -> nx.Graph:
    """Build a NetworkX graph from significant correlations.

    Args:
        corr_df: Correlation matrix DataFrame.
        pval_df: P-value matrix DataFrame.
        threshold: Minimum absolute correlation threshold (default 0.3).
        pvalue_threshold: Maximum p-value threshold (default 0.05).

    Returns:
        NetworkX Graph with nodes and weighted edges.
    """
    G = nx.Graph()
    features = corr_df.index.tolist()
    G.add_nodes_from(features)

    n_features = len(features)
    for i in range(n_features):
        for j in range(i + 1, n_features):
            corr = corr_df.iloc[i, j]
            pval = pval_df.iloc[i, j]
            if abs(corr) > threshold and pval < pvalue_threshold:
                G.add_edge(
                    features[i],
                    features[j],
                    weight=abs(corr),
                    correlation=float(corr),
                    pvalue=float(pval),
                )

    return G


def compute_network_statistics(G: nx.Graph) -> Dict[str, Any]:
    """Compute network topology statistics and identify hub nodes.

    Args:
        G: NetworkX Graph.

    Returns:
        Dictionary with network statistics and hub nodes.
    """
    if len(G.nodes) == 0:
        return {
            'node_count': 0,
            'edge_count': 0,
            'density': 0.0,
            'average_degree': 0.0,
            'average_clustering': 0.0,
            'modularity': 0.0,
            'hubs': [],
            'nodes': {},
            'edges': [],
        }

    stats = {
        'node_count': len(G.nodes),
        'edge_count': len(G.edges),
        'density': nx.density(G),
    }

    # Degree centrality
    degree_dict = dict(G.degree())
    stats['average_degree'] = sum(degree_dict.values()) / len(G.nodes) if G.nodes else 0.0

    # Betweenness centrality
    try:
        betweenness = nx.betweenness_centrality(G, weight='weight')
    except Exception:
        betweenness = {n: 0.0 for n in G.nodes}

    # Clustering coefficient
    try:
        clustering = nx.clustering(G, weight='weight')
        stats['average_clustering'] = sum(clustering.values()) / len(G.nodes) if G.nodes else 0.0
    except Exception:
        clustering = {n: 0.0 for n in G.nodes}
        stats['average_clustering'] = 0.0

    # Modularity (using greedy modularity communities)
    try:
        communities = nx.community.greedy_modularity_communities(G, weight='weight')
        modularity = nx.community.modularity(G, communities, weight='weight')
        stats['modularity'] = float(modularity)
        stats['n_communities'] = len(communities)
        # Map node to community
        node_community = {}
        for comm_id, comm in enumerate(communities):
            for node in comm:
                node_community[node] = comm_id
    except Exception:
        stats['modularity'] = 0.0
        stats['n_communities'] = 0
        node_community = {n: 0 for n in G.nodes}

    # Identify hub nodes (top 20% by degree, or top 10 if small graph)
    if len(G.nodes) > 0:
        sorted_by_degree = sorted(degree_dict.items(), key=lambda x: x[1], reverse=True)
        n_hubs = max(1, min(10, int(np.ceil(0.2 * len(G.nodes)))))
        hub_nodes = [node for node, _ in sorted_by_degree[:n_hubs]]
    else:
        hub_nodes = []

    stats['hubs'] = hub_nodes

    # Per-node statistics
    nodes_stats = {}
    for node in G.nodes:
        nodes_stats[node] = {
            'degree': int(degree_dict.get(node, 0)),
            'betweenness': float(betweenness.get(node, 0.0)),
            'clustering': float(clustering.get(node, 0.0)),
            'community': int(node_community.get(node, 0)),
            'is_hub': node in hub_nodes,
        }
    stats['nodes'] = nodes_stats

    # Edge list for export
    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            'source': u,
            'target': v,
            'correlation': float(data.get('correlation', 0)),
            'pvalue': float(data.get('pvalue', 1)),
            'weight': float(data.get('weight', 0)),
        })
    stats['edges'] = edges

    return stats


# ─────────────────────────────── Plotly Visualization


def plotly_network_graph(
    G: nx.Graph,
    layout: str = 'spring',
    width: int = 900,
    height: int = 700,
) -> dict:
    """Generate an interactive Plotly network graph figure dict.

    Args:
        G: NetworkX Graph with 'correlation' edge attributes.
        layout: Network layout algorithm ('spring', 'circular', 'kamada_kawai',
            'spectral').
        width: Plot width in pixels.
        height: Plot height in pixels.

    Returns:
        Plotly figure JSON dict.
    """
    if len(G.nodes) == 0:
        fig = go.Figure()
        fig.update_layout(
            title='Network Graph (No significant edges)',
            width=width,
            height=height,
        )
        return fig.to_dict()

    # Compute layout positions
    pos = _compute_layout(G, layout)

    # Node sizes proportional to degree centrality
    degree_dict = dict(G.degree())
    max_degree = max(degree_dict.values()) if degree_dict else 1
    node_sizes = {
        node: 10 + 30 * (degree_dict.get(node, 0) / (max_degree + 1e-10))
        for node in G.nodes
    }

    # Build edge traces (positive = red, negative = blue)
    pos_edges_x, pos_edges_y = [], []
    neg_edges_x, neg_edges_y = [], []
    pos_edge_texts = []
    neg_edge_texts = []

    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        corr = data.get('correlation', 0)
        pval = data.get('pvalue', 1)
        hover_text = f"{u} — {v}<br>Correlation: {corr:.3f}<br>P-value: {pval:.3g}"

        if corr >= 0:
            pos_edges_x.extend([x0, x1, None])
            pos_edges_y.extend([y0, y1, None])
            pos_edge_texts.append(hover_text)
        else:
            neg_edges_x.extend([x0, x1, None])
            neg_edges_y.extend([y0, y1, None])
            neg_edge_texts.append(hover_text)

    edge_traces = []
    if pos_edges_x:
        edge_traces.append(go.Scatter(
            x=pos_edges_x,
            y=pos_edges_y,
            mode='lines',
            line=dict(color='#e11d48', width=1.5),  # rose-600
            hoverinfo='text',
            text=pos_edge_texts,
            name='Positive correlation',
            showlegend=True,
        ))
    if neg_edges_x:
        edge_traces.append(go.Scatter(
            x=neg_edges_x,
            y=neg_edges_y,
            mode='lines',
            line=dict(color='#2563eb', width=1.5),  # blue-600
            hoverinfo='text',
            text=neg_edge_texts,
            name='Negative correlation',
            showlegend=True,
        ))

    # Node trace with hover info
    node_x = []
    node_y = []
    node_text = []
    node_color = []
    node_size = []

    # Betweenness for hover
    try:
        betweenness = nx.betweenness_centrality(G, weight='weight')
    except Exception:
        betweenness = {n: 0.0 for n in G.nodes}

    for node in G.nodes:
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        deg = degree_dict.get(node, 0)
        bet = betweenness.get(node, 0.0)
        node_text.append(
            f"<b>{node}</b><br>Degree: {deg}<br>Betweenness: {bet:.4f}"
        )
        node_size.append(node_sizes[node])
        # Color hub nodes distinctly
        if deg >= sorted(degree_dict.values(), reverse=True)[max(0, min(9, len(degree_dict)-1))] if degree_dict else False:
            # Simple heuristic: top degree nodes get darker color
            node_color.append('#7c3aed')  # violet-600
        else:
            node_color.append('#64748b')  # slate-500

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode='markers+text',
        text=[str(n) for n in G.nodes],
        textposition='top center',
        textfont=dict(size=9, color='#1e293b'),
        hoverinfo='text',
        hovertext=node_text,
        marker=dict(
            color=node_color,
            size=node_size,
            line=dict(width=1.5, color='#ffffff'),
        ),
        name='Nodes',
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        title='Correlation Network',
        width=width,
        height=height,
        hovermode='closest',
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='white',
        margin=dict(l=20, r=20, t=60, b=20),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
        ),
    )

    return fig.to_dict()


def _compute_layout(G: nx.Graph, layout: str) -> Dict[str, Tuple[float, float]]:
    """Compute node positions for the given layout algorithm."""
    if layout == 'circular':
        return nx.circular_layout(G)
    elif layout == 'kamada_kawai':
        return nx.kamada_kawai_layout(G)
    elif layout == 'spectral':
        return nx.spectral_layout(G)
    else:
        # Default spring layout
        return nx.spring_layout(G, k=0.5, iterations=50, seed=42)


# ─────────────────────────────── High-level Runner


def run_network_analysis(
    df: pd.DataFrame,
    method: str = 'sparcc',
    threshold: float = 0.3,
    pvalue_threshold: float = 0.05,
    n_permutations: int = 100,
    top_n_features: Optional[int] = 150,
) -> Dict[str, Any]:
    """Run complete network analysis pipeline.

    Args:
        df: Feature table (features x samples).
        method: 'sparcc' or 'spearman'.
        threshold: Absolute correlation threshold for edge inclusion.
        pvalue_threshold: P-value threshold for edge inclusion.
        n_permutations: Permutations for SparCC p-value estimation.
        top_n_features: If set, restrict analysis to top N most abundant
            features to keep computation tractable.

    Returns:
        Dictionary with correlation matrix, network statistics, and Plotly data.
    """
    # Subset to top features if needed (network analysis is O(n^2))
    if top_n_features and len(df) > top_n_features:
        top_features = df.sum(axis=1).sort_values(ascending=False).head(top_n_features).index
        df_sub = df.loc[top_features]
        logger.info(f"Network analysis restricted to top {top_n_features} features (from {len(df)})")
    else:
        df_sub = df.copy()

    # Filter out zero-variance features
    var_mask = df_sub.var(axis=1) > 0
    if not var_mask.all():
        df_sub = df_sub.loc[var_mask]
        logger.info(f"Removed {(~var_mask).sum()} zero-variance features for network analysis")

    if len(df_sub) < 2:
        return {
            'method': method,
            'error': 'Need at least 2 features with variance for network analysis',
            'node_count': 0,
            'edge_count': 0,
        }

    # Compute correlations
    if method == 'sparcc':
        corr_df = sparcc_correlation(df_sub, iterations=20, exclude_threshold=0.1)
        pval_df = sparcc_pvalues(df_sub, corr_df, n_permutations=n_permutations)
    elif method == 'spearman':
        corr_df, pval_df = spearman_correlation(df_sub)
    else:
        raise ValueError(f"Unknown correlation method: {method}. Use 'sparcc' or 'spearman'.")

    # Build network
    G = build_network(corr_df, pval_df, threshold=threshold, pvalue_threshold=pvalue_threshold)
    network_stats = compute_network_statistics(G)

    # Plotly visualization
    plot_data = plotly_network_graph(G, layout='spring')

    # Serialize correlation matrix (upper triangle only to save space)
    corr_records = []
    features = corr_df.index.tolist()
    for i in range(len(features)):
        for j in range(i + 1, len(features)):
            corr_records.append({
                'source': features[i],
                'target': features[j],
                'correlation': float(corr_df.iloc[i, j]),
                'pvalue': float(pval_df.iloc[i, j]),
            })

    return {
        'method': method,
        'threshold': threshold,
        'pvalue_threshold': pvalue_threshold,
        'feature_count': len(df_sub),
        'correlation_edges': corr_records,
        'network': network_stats,
        'plot_data': plot_data,
    }
