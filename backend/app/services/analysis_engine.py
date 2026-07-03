"""
Meta2bAnalyst - Analysis Engine Service (Python Statistical Analysis)
Implements Alpha/Beta diversity, differential abundance, PCoA, NMDS, heatmap.
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.spatial.distance import braycurtis, euclidean, jaccard, pdist, squareform
from scipy.stats import mannwhitneyu, wilcoxon, spearmanr, pearsonr, ttest_ind, kruskal, shapiro, f_oneway
from sklearn.decomposition import PCA
from sklearn.manifold import MDS
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ─────────────────────────────── Alpha Diversity

def calculate_shannon(df: pd.DataFrame) -> pd.Series:
    """Calculate Shannon diversity index for each sample."""
    proportions = df.div(df.sum(axis=0), axis=1).fillna(0)
    proportions = proportions[proportions > 0]
    shannon = -proportions.multiply(np.log(proportions)).sum(axis=0)
    return shannon


def calculate_simpson(df: pd.DataFrame) -> pd.Series:
    """Calculate Simpson diversity index for each sample."""
    proportions = df.div(df.sum(axis=0), axis=1).fillna(0)
    simpson = 1 - (proportions ** 2).sum(axis=0)
    return simpson


def calculate_observed_richness(df: pd.DataFrame) -> pd.Series:
    """Calculate observed species richness for each sample."""
    return (df > 0).sum(axis=0)


def calculate_chao1(df: pd.DataFrame) -> pd.Series:
    """Calculate Chao1 richness estimator for each sample."""
    # Simplified Chao1: S_obs + (n1^2 / (2 * n2)) where n1= singletons, n2=doubletons
    singletons = (df == 1).sum(axis=0)
    doubletons = (df == 2).sum(axis=0)
    observed = (df > 0).sum(axis=0)
    chao1 = observed + (singletons ** 2) / (2 * (doubletons + 1e-10))
    return chao1


def calculate_pielou_evenness(df: pd.DataFrame) -> pd.Series:
    """Calculate Pielou's evenness index."""
    shannon = calculate_shannon(df)
    richness = calculate_observed_richness(df)
    evenness = shannon / np.log(richness + 1e-10)
    return evenness


def run_alpha_diversity(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run alpha diversity analysis.

    Returns:
        Dict with diversity indices per sample and group statistics
    """
    params = parameters or {}
    indices = params.get("indices", ["shannon", "simpson", "observed", "chao1", "evenness"])
    
    results = {"sample_diversity": {}}
    
    for sample in df.columns:
        sample_results = {}
        if "shannon" in indices:
            sample_results["shannon"] = float(calculate_shannon(df)[sample])
        if "simpson" in indices:
            sample_results["simpson"] = float(calculate_simpson(df)[sample])
        if "observed" in indices:
            sample_results["observed"] = int(calculate_observed_richness(df)[sample])
        if "chao1" in indices:
            sample_results["chao1"] = float(calculate_chao1(df)[sample])
        if "evenness" in indices:
            sample_results["evenness"] = float(calculate_pielou_evenness(df)[sample])
        results["sample_diversity"][sample] = sample_results
    
    # Group statistics if metadata provided
    group_column = params.get("group_column")
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results["group_statistics"] = {}
        groups = metadata_df[group_column].dropna().unique()
        
        for index_name in indices:
            if index_name == "shannon":
                values = calculate_shannon(df)
            elif index_name == "simpson":
                values = calculate_simpson(df)
            elif index_name == "observed":
                values = calculate_observed_richness(df)
            elif index_name == "chao1":
                values = calculate_chao1(df)
            elif index_name == "evenness":
                values = calculate_pielou_evenness(df)
            else:
                continue
            
            group_stats = {}
            for group in groups:
                group_samples = metadata_df[metadata_df[group_column] == group].index
                group_samples = [s for s in group_samples if s in values.index]
                if group_samples:
                    group_vals = values[group_samples]
                    group_stats[str(group)] = {
                        "mean": float(group_vals.mean()),
                        "median": float(group_vals.median()),
                        "std": float(group_vals.std()),
                        "min": float(group_vals.min()),
                        "max": float(group_vals.max()),
                        "n": int(len(group_vals)),
                    }
            
            # Statistical test between groups
            if len(groups) == 2:
                g1, g2 = groups
                s1 = [s for s in metadata_df[metadata_df[group_column] == g1].index if s in values.index]
                s2 = [s for s in metadata_df[metadata_df[group_column] == g2].index if s in values.index]
                if s1 and s2:
                    try:
                        stat, pvalue = mannwhitneyu(values[s1], values[s2], alternative="two-sided")
                        group_stats["statistical_test"] = {
                            "test": "Mann-Whitney U",
                            "statistic": float(stat),
                            "pvalue": float(pvalue),
                            "significant": pvalue < 0.05,
                        }
                    except Exception as e:
                        logger.warning(f"Statistical test failed: {e}")
            elif len(groups) > 2:
                group_values = [values[[s for s in metadata_df[metadata_df[group_column] == g].index if s in values.index]] for g in groups]
                group_values = [g for g in group_values if len(g) > 0]
                if len(group_values) > 1:
                    try:
                        stat, pvalue = kruskal(*group_values)
                        group_stats["statistical_test"] = {
                            "test": "Kruskal-Wallis",
                            "statistic": float(stat),
                            "pvalue": float(pvalue),
                            "significant": pvalue < 0.05,
                        }
                    except Exception as e:
                        logger.warning(f"Kruskal-Wallis test failed: {e}")
            
            results["group_statistics"][index_name] = group_stats
    
    return results


# ─────────────────────────────── Beta Diversity

def calculate_beta_diversity(df: pd.DataFrame, metric: str = "braycurtis") -> pd.DataFrame:
    """Calculate beta diversity distance matrix."""
    # Transpose to samples x features for distance calculation
    df_t = df.T.fillna(0)
    
    if metric == "braycurtis":
        distances = pdist(df_t, metric="braycurtis")
    elif metric == "jaccard":
        distances = pdist(df_t, metric="jaccard")
    elif metric == "euclidean":
        distances = pdist(df_t, metric="euclidean")
    elif metric == "canberra":
        distances = pdist(df_t, metric="canberra")
    elif metric == "minkowski":
        distances = pdist(df_t, metric="minkowski")
    else:
        distances = pdist(df_t, metric="braycurtis")
    
    dist_matrix = squareform(distances)
    return pd.DataFrame(dist_matrix, index=df_t.index, columns=df_t.index)


def run_beta_diversity(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run beta diversity analysis.

    Returns:
        Dict with distance matrix and group statistics
    """
    params = parameters or {}
    metric = params.get("metric", "braycurtis")
    
    dist_matrix = calculate_beta_diversity(df, metric)
    
    results = {
        "metric": metric,
        "distance_matrix": dist_matrix.to_dict(),
        "sample_count": len(df.columns),
    }
    
    # Group statistics if metadata provided
    group_column = params.get("group_column")
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        # Per-group average distances
        groups = metadata_df[group_column].dropna().unique()
        group_stats = {}
        
        for group in groups:
            group_samples = metadata_df[metadata_df[group_column] == group].index
            group_samples = [s for s in group_samples if s in dist_matrix.index]
            if group_samples:
                group_dists = dist_matrix.loc[group_samples, group_samples]
                # Upper triangle mean (excluding diagonal)
                upper_tri = np.triu(group_dists.values, k=1)
                non_zero = upper_tri[upper_tri > 0]
                group_stats[str(group)] = {
                    "mean_within_group_distance": float(non_zero.mean()) if len(non_zero) > 0 else 0.0,
                    "n_samples": int(len(group_samples)),
                }
        
        results["group_statistics"] = group_stats
    
    return results


# ─────────────────────────────── PCoA

def run_pcoa(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run Principal Coordinates Analysis (PCoA).

    Returns:
        Dict with coordinates, variance explained, and plot data
    """
    params = parameters or {}
    metric = params.get("metric", "braycurtis")
    n_components = params.get("n_components", 3)
    
    # Calculate distance matrix
    dist_matrix = calculate_beta_diversity(df, metric)
    
    # Convert to matrix and handle numerical issues
    D = dist_matrix.values
    # Double centering for PCoA
    n = D.shape[0]
    H = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * H @ (D ** 2) @ H
    
    # Eigen decomposition
    eigenvalues, eigenvectors = np.linalg.eigh(B)
    
    # Sort in descending order
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    
    # Take positive eigenvalues only
    positive_mask = eigenvalues > 0
    eigenvalues = eigenvalues[positive_mask][:n_components]
    eigenvectors = eigenvectors[:, positive_mask][:, :n_components]
    
    # Coordinates
    coordinates = eigenvectors * np.sqrt(eigenvalues)
    
    # Variance explained
    total_variance = np.sum(eigenvalues[eigenvalues > 0])
    variance_explained = [(e / total_variance) * 100 for e in eigenvalues]
    
    results = {
        "metric": metric,
        "coordinates": {
            sample: coords.tolist()
            for sample, coords in zip(dist_matrix.index, coordinates)
        },
        "eigenvalues": eigenvalues.tolist(),
        "variance_explained": variance_explained,
        "n_components": len(eigenvalues),
    }
    
    # Add group colors if metadata available
    group_column = params.get("group_column")
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results["group_metadata"] = {
            sample: str(metadata_df.loc[sample, group_column])
            for sample in dist_matrix.index
            if sample in metadata_df.index
        }
    
    return results


# ─────────────────────────────── NMDS

def run_nmds(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run Non-metric Multidimensional Scaling (NMDS).

    Returns:
        Dict with coordinates and stress value
    """
    params = parameters or {}
    metric = params.get("metric", "braycurtis")
    n_components = params.get("n_components", 2)
    
    # Calculate distance matrix
    dist_matrix = calculate_beta_diversity(df, metric)
    
    # Use sklearn MDS
    mds = MDS(
        n_components=n_components,
        metric=False,  # NMDS
        dissimilarity="precomputed",
        random_state=42,
        max_iter=500,
        n_init=10,
    )
    
    coordinates = mds.fit_transform(dist_matrix.values)
    stress = float(mds.stress_)
    
    results = {
        "metric": metric,
        "coordinates": {
            sample: coords.tolist()
            for sample, coords in zip(dist_matrix.index, coordinates)
        },
        "stress": stress,
        "n_components": n_components,
    }
    
    group_column = params.get("group_column")
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results["group_metadata"] = {
            sample: str(metadata_df.loc[sample, group_column])
            for sample in dist_matrix.index
            if sample in metadata_df.index
        }
    
    return results


# ─────────────────────────────── Differential Abundance

def run_differential_analysis(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run differential abundance analysis between groups.

    Returns:
        Dict with differentially abundant features and statistics
    """
    params = parameters or {}
    group_column = params.get("group_column")
    test_method = params.get("test_method", "mannwhitney")
    pvalue_threshold = params.get("pvalue_threshold", 0.05)
    
    if metadata_df is None or group_column not in metadata_df.columns:
        return {"error": "Metadata with group column required for differential analysis"}
    
    groups = metadata_df[group_column].dropna().unique()
    if len(groups) != 2:
        return {"error": f"Differential analysis requires exactly 2 groups, found {len(groups)}"}
    
    g1, g2 = groups
    g1_samples = [s for s in metadata_df[metadata_df[group_column] == g1].index if s in df.columns]
    g2_samples = [s for s in metadata_df[metadata_df[group_column] == g2].index if s in df.columns]
    
    results = {
        "group_column": group_column,
        "group1": str(g1),
        "group2": str(g2),
        "group1_n": len(g1_samples),
        "group2_n": len(g2_samples),
        "test_method": test_method,
        "significant_features": [],
        "all_features": [],
    }
    
    for feature in df.index:
        g1_values = df.loc[feature, g1_samples].values
        g2_values = df.loc[feature, g2_samples].values
        
        # Skip if all zeros
        if g1_values.sum() == 0 and g2_values.sum() == 0:
            continue
        
        # Statistical test
        try:
            if test_method == "mannwhitney":
                stat, pvalue = mannwhitneyu(g1_values, g2_values, alternative="two-sided")
            elif test_method == "ttest":
                stat, pvalue = ttest_ind(g1_values, g2_values)
            elif test_method == "wilcoxon":
                stat, pvalue = wilcoxon(g1_values, g2_values)
            else:
                stat, pvalue = mannwhitneyu(g1_values, g2_values, alternative="two-sided")
        except Exception as e:
            logger.warning(f"Statistical test failed for feature {feature}: {e}")
            continue
        
        # Effect size (log2 fold change of means)
        g1_mean = g1_values.mean() + 1e-10
        g2_mean = g2_values.mean() + 1e-10
        log2fc = np.log2(g2_mean / g1_mean)
        
        feature_result = {
            "feature": str(feature),
            "group1_mean": float(g1_mean),
            "group2_mean": float(g2_mean),
            "log2_fold_change": float(log2fc),
            "statistic": float(stat),
            "pvalue": float(pvalue),
            "significant": pvalue < pvalue_threshold,
        }
        
        results["all_features"].append(feature_result)
        if pvalue < pvalue_threshold:
            results["significant_features"].append(feature_result)
    
    # Sort by p-value
    results["all_features"].sort(key=lambda x: x["pvalue"])
    results["significant_features"].sort(key=lambda x: x["pvalue"])
    
    return results


# ─────────────────────────────── Heatmap

def run_heatmap(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate heatmap data with optional clustering.

    Returns:
        Dict with heatmap matrix and dendrogram data
    """
    params = parameters or {}
    top_n = params.get("top_n", 50)
    cluster_rows = params.get("cluster_rows", True)
    cluster_cols = params.get("cluster_cols", True)
    normalize = params.get("normalize", "zscore")
    
    # Select top features by variance
    if len(df) > top_n:
        feature_var = df.var(axis=1).sort_values(ascending=False)
        top_features = feature_var.head(top_n).index
        df = df.loc[top_features]
    
    # Normalize
    if normalize == "zscore":
        df_norm = df.T.apply(lambda x: (x - x.mean()) / (x.std() + 1e-10), axis=0).T
    elif normalize == "relative":
        df_norm = df.div(df.sum(axis=0), axis=1).fillna(0)
    elif normalize == "log":
        df_norm = np.log10(df + 1e-10)
    else:
        df_norm = df.copy()
    
    # Clustering
    row_order = list(df_norm.index)
    col_order = list(df_norm.columns)
    
    if cluster_rows and len(df_norm) > 1:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import pdist
        try:
            row_dist = pdist(df_norm.values)
            row_linkage = linkage(row_dist, method="average")
            row_order = [df_norm.index[i] for i in leaves_list(row_linkage)]
        except Exception as e:
            logger.warning(f"Row clustering failed: {e}")
    
    if cluster_cols and len(df_norm.columns) > 1:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import pdist
        try:
            col_dist = pdist(df_norm.T.values)
            col_linkage = linkage(col_dist, method="average")
            col_order = [df_norm.columns[i] for i in leaves_list(col_linkage)]
        except Exception as e:
            logger.warning(f"Column clustering failed: {e}")
    
    # Reorder matrix
    df_ordered = df_norm.loc[row_order, col_order]
    
    results = {
        "matrix": df_ordered.to_dict(),
        "row_order": row_order,
        "col_order": col_order,
        "row_labels": row_order,
        "col_labels": col_order,
        "normalize": normalize,
    }
    
    group_column = params.get("group_column")
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results["group_metadata"] = {
            sample: str(metadata_df.loc[sample, group_column])
            for sample in col_order
            if sample in metadata_df.index
        }
    
    return results
