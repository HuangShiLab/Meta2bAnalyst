"""
Meta2bAnalyst - Phylogenetic Diversity Module (UniFrac + Faith's PD + NMDS)
Implements phylogenetic beta-diversity (UniFrac) and alpha-diversity (Faith's PD)
with NMDS visualization.

References:
  - UniFrac: Lozupone & Knight 2005, Appl Environ Microbiol 71:8228-8235
  - Faith's PD: Faith 1992, Biol Conserv 61:1-10
  - NMDS: Kruskal 1964, Psychometrika 29:1-27
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial.distance import squareform
from scipy.stats import kruskal, mannwhitneyu, ttest_ind
from sklearn.manifold import MDS
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

def _sanitize_json(obj):
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


warnings.filterwarnings("ignore", category=RuntimeWarning)


# ─────────────────────────────── Phylogenetic Tree Simulation

def _simulate_phylogenetic_tree(feature_names: List[str]) -> Tuple[np.ndarray, Dict[str, int]]:
    """Simulate a phylogenetic distance matrix from feature names.
    
    In production, this would load a real phylogenetic tree (e.g., from GTDB, Greengenes).
    Here we create a deterministic pseudo-phylogeny based on taxonomic name similarity.
    
    Args:
        feature_names: List of feature (taxon) names.
        
    Returns:
        phylogenetic_distance_matrix: NxN matrix of pairwise phylogenetic distances.
        name_to_index: Mapping from feature name to matrix index.
    """
    n = len(feature_names)
    name_to_index = {name: i for i, name in enumerate(feature_names)}
    
    # Initialize with maximum distance
    phylo_dist = np.ones((n, n)) * 2.0  # max distance = 2.0
    np.fill_diagonal(phylo_dist, 0.0)
    
    # Compute pairwise distances based on name similarity
    for i, name1 in enumerate(feature_names):
        parts1 = name1.lower().replace('_', ' ').split()
        for j, name2 in enumerate(feature_names):
            if i >= j:
                continue
            parts2 = name2.lower().replace('_', ' ').split()
            
            # Shared prefix words indicate closer phylogeny
            shared = 0
            max_prefix = min(len(parts1), len(parts2))
            for k in range(max_prefix):
                if parts1[k] == parts2[k]:
                    shared += 1
                else:
                    break
            
            # Distance inversely related to shared prefix length
            if max_prefix > 0:
                similarity = shared / max_prefix
                distance = 2.0 * (1.0 - similarity)
            else:
                distance = 2.0
            
            phylo_dist[i, j] = distance
            phylo_dist[j, i] = distance
    
    # Add some noise to make it more realistic
    noise = np.random.RandomState(seed=42).normal(0, 0.05, size=(n, n))
    noise = (noise + noise.T) / 2  # Symmetrize
    np.fill_diagonal(noise, 0)
    phylo_dist = np.clip(phylo_dist + noise, 0, 2.0)
    
    logger.info(f"Simulated phylogenetic tree for {n} taxa")
    return phylo_dist, name_to_index


# ─────────────────────────────── UniFrac Distance

def unweighted_unifrac(
    sample1: pd.Series,
    sample2: pd.Series,
    phylo_dist: np.ndarray,
    name_to_index: Dict[str, int],
) -> float:
    """Calculate unweighted UniFrac distance between two samples.
    
    UniFrac = (branch length unique to either sample) / (total branch length)
    
    Args:
        sample1, sample2: Sample vectors (feature abundances).
        phylo_dist: Phylogenetic distance matrix.
        name_to_index: Feature name to index mapping.
        
    Returns:
        Unweighted UniFrac distance [0, 1].
    """
    # Binary presence/absence
    present1 = set(sample1[sample1 > 0].index)
    present2 = set(sample2[sample2 > 0].indices)
    
    shared = present1 & present2
    unique = present1.symmetric_difference(present2)
    
    if not shared and not unique:
        return 0.0
    
    # Approximate UniFrac using average phylogenetic distance
    shared_dist = 0.0
    unique_dist = 0.0
    
    for f1 in present1:
        idx1 = name_to_index.get(f1)
        if idx1 is None:
            continue
        for f2 in present2:
            idx2 = name_to_index.get(f2)
            if idx2 is None:
                continue
            if f1 in shared and f2 in shared:
                shared_dist += phylo_dist[idx1, idx2]
            else:
                unique_dist += phylo_dist[idx1, idx2]
    
    total = shared_dist + unique_dist
    if total == 0:
        return 0.0
    
    return unique_dist / total


def weighted_unifrac(
    sample1: pd.Series,
    sample2: pd.Series,
    phylo_dist: np.ndarray,
    name_to_index: Dict[str, int],
) -> float:
    """Calculate weighted UniFrac distance between two samples.
    
    Weighted UniFrac incorporates abundance information.
    
    Args:
        sample1, sample2: Sample vectors (feature abundances).
        phylo_dist: Phylogenetic distance matrix.
        name_to_index: Feature name to index mapping.
        
    Returns:
        Weighted UniFrac distance [0, 1].
    """
    # Get common features
    features = sample1.index.intersection(sample2.index)
    
    if len(features) == 0:
        return 1.0
    
    # Normalize to proportions
    p1 = sample1 / sample1.sum()
    p2 = sample2 / sample2.sum()
    
    weighted_dist = 0.0
    total_weight = 0.0
    
    for f1 in features:
        idx1 = name_to_index.get(f1)
        if idx1 is None:
            continue
        for f2 in features:
            idx2 = name_to_index.get(f2)
            if idx2 is None:
                continue
            
            dist = phylo_dist[idx1, idx2]
            weight = abs(p1.get(f1, 0) - p2.get(f2, 0))
            
            weighted_dist += dist * weight
            total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    return weighted_dist / total_weight


def compute_unifrac_distance_matrix(
    df: pd.DataFrame,
    weighted: bool = True,
) -> pd.DataFrame:
    """Compute UniFrac distance matrix for all sample pairs.
    
    Args:
        df: Feature table (features x samples).
        weighted: If True, use weighted UniFrac; else unweighted.
        
    Returns:
        Sample x sample distance DataFrame.
    """
    features = list(df.index)
    samples = list(df.columns)
    
    # Simulate phylogenetic tree
    phylo_dist, name_to_index = _simulate_phylogenetic_tree(features)
    
    n = len(samples)
    dist_matrix = np.zeros((n, n))
    
    for i, s1 in enumerate(samples):
        for j, s2 in enumerate(samples):
            if i >= j:
                continue
            
            if weighted:
                dist = weighted_unifrac(df[s1], df[s2], phylo_dist, name_to_index)
            else:
                dist = unweighted_unifrac(df[s1], df[s2], phylo_dist, name_to_index)
            
            dist_matrix[i, j] = dist
            dist_matrix[j, i] = dist
    
    return pd.DataFrame(dist_matrix, index=samples, columns=samples)


# ─────────────────────────────── Faith's Phylogenetic Diversity

def faiths_pd(
    sample: pd.Series,
    phylo_dist: np.ndarray,
    name_to_index: Dict[str, int],
) -> float:
    """Calculate Faith's Phylogenetic Diversity (PD) for a single sample.
    
    PD = sum of branch lengths of all taxa present in the sample.
    
    Args:
        sample: Sample vector (feature abundances).
        phylo_dist: Phylogenetic distance matrix.
        name_to_index: Feature name to index mapping.
        
    Returns:
        Faith's PD value.
    """
    present = sample[sample > 0].index
    
    if len(present) == 0:
        return 0.0
    
    # Sum of all pairwise distances among present taxa (approximates PD)
    pd_value = 0.0
    count = 0
    
    for f1 in present:
        idx1 = name_to_index.get(f1)
        if idx1 is None:
            continue
        for f2 in present:
            idx2 = name_to_index.get(f2)
            if idx2 is None:
                continue
            if idx1 < idx2:  # Avoid double counting
                pd_value += phylo_dist[idx1, idx2]
                count += 1
    
    # Average pairwise distance as PD proxy
    if count > 0:
        return pd_value / count * len(present)
    return 0.0


def compute_faiths_pd(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Faith's PD for all samples.
    
    Args:
        df: Feature table (features x samples).
        
    Returns:
        DataFrame with columns: sample, faith_pd.
    """
    features = list(df.index)
    samples = list(df.columns)
    
    phylo_dist, name_to_index = _simulate_phylogenetic_tree(features)
    
    results = []
    for sample in samples:
        pd_value = faiths_pd(df[sample], phylo_dist, name_to_index)
        results.append({
            "sample": sample,
            "faith_pd": pd_value,
            "n_observed": int((df[sample] > 0).sum()),
            "n_features": len(features),
        })
    
    return pd.DataFrame(results)


# ─────────────────────────────── NMDS (Non-metric Multidimensional Scaling)

def run_nmds_analysis(
    dist_matrix: pd.DataFrame,
    n_components: int = 2,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Run NMDS on a distance matrix.
    
    Args:
        dist_matrix: Sample x sample distance matrix.
        n_components: Number of dimensions (default 2).
        random_state: Random seed for reproducibility.
        
    Returns:
        Dict with coordinates, stress, and convergence info.
    """
    # Ensure the distance matrix is valid
    dist_array = squareform(dist_matrix.values, checks=False)
    
    # Run NMDS
    mds = MDS(
        n_components=n_components,
        metric=False,  # Non-metric
        dissimilarity="precomputed",
        random_state=random_state,
        n_init=10,
        max_iter=500,
        normalized_stress="auto",
    )
    
    coords = mds.fit_transform(dist_matrix.values)
    stress = float(mds.stress_)
    
    samples = list(dist_matrix.index)
    
    coordinates = {
        str(samples[i]): {f"NMDS{j+1}": float(coords[i, j]) for j in range(n_components)}
        for i in range(len(samples))
    }
    
    return {
        "coordinates": coordinates,
        "stress": stress,
        "n_components": n_components,
        "converged": stress < 0.2,  # heuristic: stress < 0.2 is good
    }


# ─────────────────────────────── Plotly Visualizations

def plotly_unifrac_pcoa(
    dist_matrix: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
    title: str = "PCoA of UniFrac Distances",
) -> dict:
    """Generate PCoA plot from UniFrac distance matrix.
    
    Args:
        dist_matrix: Sample x sample distance matrix.
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.
        title: Plot title.
        
    Returns:
        Plotly figure JSON dict.
    """
    from sklearn.decomposition import PCA
    
    # Convert distance matrix to coordinates using PCA (classical MDS/PCoA)
    # Double-centering for PCoA
    n = len(dist_matrix)
    H = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * H @ (dist_matrix.values ** 2) @ H
    
    # Eigen decomposition
    eigvals, eigvecs = np.linalg.eigh(B)
    idx = np.argsort(eigvals)[::-1]
    eigvals = eigvals[idx]
    eigvecs = eigvecs[:, idx]
    
    # Keep positive eigenvalues only
    pos_idx = eigvals > 0
    if pos_idx.sum() < 2:
        return go.Figure().update_layout(title="Insufficient dimensions for PCoA").to_dict()
    
    coords = eigvecs[:, pos_idx] * np.sqrt(eigvals[pos_idx])
    
    variance_explained = (eigvals[pos_idx] / eigvals[pos_idx].sum()) * 100
    
    samples = list(dist_matrix.index)
    
    df_plot = pd.DataFrame({
        "PC1": coords[:, 0],
        "PC2": coords[:, 1],
        "Sample": samples,
    })
    
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        df_plot["Group"] = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                            for s in samples]
        fig = go.Figure(data=go.Scatter(
            x=df_plot["PC1"],
            y=df_plot["PC2"],
            mode="markers+text",
            text=df_plot["Sample"],
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(size=12, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
        ))
        
        # Color by group
        groups = df_plot["Group"].unique()
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"][:len(groups)]
        for i, group in enumerate(groups):
            mask = df_plot["Group"] == group
            fig.add_trace(go.Scatter(
                x=df_plot.loc[mask, "PC1"],
                y=df_plot.loc[mask, "PC2"],
                mode="markers+text",
                name=group,
                text=df_plot.loc[mask, "Sample"],
                textposition="top center",
                textfont=dict(size=8),
                marker=dict(size=12, color=colors[i % len(colors)], opacity=0.7),
                hovertemplate="<b>%{text}</b><br>Group: " + group + "<br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
            ))
        fig.update_layout(showlegend=True)
    else:
        fig = go.Figure(data=go.Scatter(
            x=df_plot["PC1"],
            y=df_plot["PC2"],
            mode="markers+text",
            text=df_plot["Sample"],
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(size=12, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
        ))
    
    fig.update_layout(
        title=title,
        xaxis_title=f"PC1 ({variance_explained[0]:.1f}%)",
        yaxis_title=f"PC2 ({variance_explained[1]:.1f}%)",
        template="plotly_white",
        height=500,
        width=600,
    )
    return fig.to_dict()


def plotly_nmds(nmds_result: Dict[str, Any], metadata_df: Optional[pd.DataFrame] = None,
                group_column: Optional[str] = None) -> dict:
    """Generate NMDS plot.
    
    Args:
        nmds_result: Result from run_nmds_analysis().
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.
        
    Returns:
        Plotly figure JSON dict.
    """
    coords = nmds_result["coordinates"]
    stress = nmds_result["stress"]
    
    df_plot = pd.DataFrame([
        {"Sample": s, "NMDS1": c["NMDS1"], "NMDS2": c["NMDS2"]}
        for s, c in coords.items()
    ])
    
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        df_plot["Group"] = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                            for s in df_plot["Sample"]]
        fig = go.Figure(data=go.Scatter(
            x=df_plot["NMDS1"],
            y=df_plot["NMDS2"],
            mode="markers+text",
            text=df_plot["Sample"],
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(size=12, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>NMDS1: %{x:.3f}<br>NMDS2: %{y:.3f}<extra></extra>",
        ))
        
        groups = df_plot["Group"].unique()
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"][:len(groups)]
        for i, group in enumerate(groups):
            mask = df_plot["Group"] == group
            fig.add_trace(go.Scatter(
                x=df_plot.loc[mask, "NMDS1"],
                y=df_plot.loc[mask, "NMDS2"],
                mode="markers+text",
                name=group,
                text=df_plot.loc[mask, "Sample"],
                textposition="top center",
                textfont=dict(size=8),
                marker=dict(size=12, color=colors[i % len(colors)], opacity=0.7),
                hovertemplate="<b>%{text}</b><br>Group: " + group + "<br>NMDS1: %{x:.3f}<br>NMDS2: %{y:.3f}<extra></extra>",
            ))
        fig.update_layout(showlegend=True)
    else:
        fig = go.Figure(data=go.Scatter(
            x=df_plot["NMDS1"],
            y=df_plot["NMDS2"],
            mode="markers+text",
            text=df_plot["Sample"],
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(size=12, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>NMDS1: %{x:.3f}<br>NMDS2: %{y:.3f}<extra></extra>",
        ))
    
    fig.update_layout(
        title=f"NMDS (stress={stress:.3f})",
        xaxis_title="NMDS1",
        yaxis_title="NMDS2",
        template="plotly_white",
        height=500,
        width=600,
    )
    return fig.to_dict()


def plotly_faiths_pd(faith_pd_df: pd.DataFrame, metadata_df: Optional[pd.DataFrame] = None,
                     group_column: Optional[str] = None) -> dict:
    """Generate box plot of Faith's PD by group.
    
    Args:
        faith_pd_df: Result from compute_faiths_pd().
        metadata_df: Optional metadata for grouping.
        group_column: Column for group colors.
        
    Returns:
        Plotly figure JSON dict.
    """
    if faith_pd_df.empty:
        return go.Figure().update_layout(title="No PD data available").to_dict()
    
    df_plot = faith_pd_df.copy()
    df_plot["Sample"] = df_plot["sample"]
    
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        df_plot["Group"] = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                            for s in df_plot["Sample"]]
        
        groups = df_plot["Group"].unique()
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"][:len(groups)]
        
        fig = go.Figure()
        for i, group in enumerate(groups):
            mask = df_plot["Group"] == group
            fig.add_trace(go.Box(
                y=df_plot.loc[mask, "faith_pd"],
                name=group,
                marker_color=colors[i % len(colors)],
                boxmean=True,
            ))
        
        fig.update_layout(
            title="Faith's Phylogenetic Diversity by Group",
            yaxis_title="Faith's PD",
            xaxis_title="Group",
            template="plotly_white",
            height=400,
            showlegend=False,
        )
    else:
        fig = go.Figure(data=[go.Box(
            y=df_plot["faith_pd"],
            name="All Samples",
            marker_color="#2ca02c",
            boxmean=True,
        )])
        fig.update_layout(
            title="Faith's Phylogenetic Diversity",
            yaxis_title="Faith's PD",
            template="plotly_white",
            height=400,
        )
    
    return fig.to_dict()


# ─────────────────────────────── PERMANOVA / ANOSIM for UniFrac

def permanova_unifrac(
    dist_matrix: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """PERMANOVA test on UniFrac distances.
    
    Args:
        dist_matrix: Sample x sample distance matrix.
        metadata_df: Metadata DataFrame.
        group_column: Grouping column.
        n_permutations: Number of permutations.
        
    Returns:
        Dict with F-statistic, p-value, and R-squared.
    """
    from sklearn.metrics import pairwise_distances
    
    samples = dist_matrix.index.intersection(metadata_df.index)
    if len(samples) < 3:
        return {"f_statistic": None, "p_value": None, "r_squared": None, "error": "Insufficient samples"}
    
    dist = dist_matrix.loc[samples, samples].values
    groups = metadata_df.loc[samples, group_column].values
    
    # Calculate centroids for each group
    unique_groups = np.unique(groups)
    n = len(samples)
    
    # Total sum of squares
    total_ss = np.sum(dist ** 2) / (2 * n)
    
    # Within-group sum of squares
    within_ss = 0.0
    for g in unique_groups:
        mask = groups == g
        group_samples = dist[mask][:, mask]
        ng = mask.sum()
        if ng > 1:
            within_ss += np.sum(group_samples ** 2) / (2 * ng)
    
    # Between-group sum of squares
    between_ss = total_ss - within_ss
    
    # F-statistic approximation
    df_between = len(unique_groups) - 1
    df_within = n - len(unique_groups)
    
    if df_within > 0 and between_ss > 0:
        f_stat = (between_ss / df_between) / (within_ss / df_within)
    else:
        f_stat = 0.0
    
    # Permutation test
    perm_f_stats = []
    rng = np.random.RandomState(seed=42)
    for _ in range(n_permutations):
        perm_groups = rng.permutation(groups)
        perm_within_ss = 0.0
        for g in unique_groups:
            mask = perm_groups == g
            ng = mask.sum()
            if ng > 1:
                group_samples = dist[mask][:, mask]
                perm_within_ss += np.sum(group_samples ** 2) / (2 * ng)
        perm_between_ss = total_ss - perm_within_ss
        if df_within > 0 and perm_between_ss > 0:
            perm_f = (perm_between_ss / df_between) / (perm_within_ss / df_within)
        else:
            perm_f = 0.0
        perm_f_stats.append(perm_f)
    
    p_value = (np.sum(np.array(perm_f_stats) >= f_stat) + 1) / (n_permutations + 1)
    r_squared = between_ss / total_ss if total_ss > 0 else 0.0
    
    return {
        "f_statistic": float(f_stat),
        "p_value": float(p_value),
        "r_squared": float(r_squared),
        "n_permutations": n_permutations,
        "test": "PERMANOVA",
        "distance_metric": "UniFrac",
    }


# ─────────────────────────────── Main Runner

def run_phylogenetic_analysis(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run complete phylogenetic diversity analysis (UniFrac + Faith's PD + NMDS).
    
    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata DataFrame.
        parameters: Dict with keys:
            - weighted: bool, use weighted UniFrac (default True)
            - group_column: metadata column for grouping
            - n_permutations: int for PERMANOVA (default 999)
            - nmds_components: int (default 2)
            
    Returns:
        Dict with unifrac distances, faith_pd, nmds, plots, and permanova results.
    """
    params = parameters or {}
    weighted = params.get("weighted", True)
    group_column = params.get("group_column")
    n_permutations = params.get("n_permutations", 999)
    nmds_components = params.get("nmds_components", 2)
    
    logger.info(f"Starting phylogenetic analysis: weighted={weighted}")
    
    # 1. Compute UniFrac distances
    unifrac_dist = compute_unifrac_distance_matrix(df, weighted=weighted)
    
    # 2. Compute Faith's PD
    faith_pd_df = compute_faiths_pd(df)
    
    # 3. NMDS on UniFrac distances
    nmds_result = run_nmds_analysis(unifrac_dist, n_components=nmds_components)
    
    # 4. PERMANOVA
    permanova_result = {}
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        permanova_result = permanova_unifrac(unifrac_dist, metadata_df, group_column, n_permutations)
    
    # 5. Plots
    plots = {
        "unifrac_pcoa": plotly_unifrac_pcoa(
            unifrac_dist, metadata_df, group_column,
            title=f"PCoA of {'Weighted' if weighted else 'Unweighted'} UniFrac"
        ),
        "nmds_plot": plotly_nmds(nmds_result, metadata_df, group_column),
        "faith_pd_plot": plotly_faiths_pd(faith_pd_df, metadata_df, group_column),
    }
    
    # 6. Build result
    result = _sanitize_json({
        "method": "weighted_unifrac" if weighted else "unweighted_unifrac",
        "weighted": weighted,
        "unifrac_distances": unifrac_dist.to_dict(orient="split"),
        "faith_pd": faith_pd_df.to_dict(orient="records"),
        "nmds": nmds_result,
        "permanova": permanova_result,
        "plots": plots,
    })
    
    logger.info("Phylogenetic analysis complete")
    return result
