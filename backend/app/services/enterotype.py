"""
Enterotype clustering analysis for microbiome data.

Implements enterotype discovery via:
- Distance matrix computation (Jaccard, Bray-Curtis)
- PAM (Partitioning Around Medoids) clustering or K-Means fallback
- PCoA (Principal Coordinate Analysis) for visualization
- Silhouette scoring and cluster composition analysis

Uses only numpy, pandas, scipy, sklearn. No R required.
Includes fallback implementations if sklearn-extra is unavailable.
"""

import numpy as np
import pandas as pd
from scipy.spatial.distance import squareform, pdist
from scipy.linalg import eigh
from sklearn.metrics import silhouette_score
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from typing import Dict, Any, Optional, Tuple


def _compute_jaccard(X: np.ndarray) -> np.ndarray:
    """
    Compute Jaccard distance matrix for presence/absence data.
    
    Jaccard distance = 1 - (|A ∩ B| / |A ∪ B|)
    """
    # Binarize (presence/absence)
    X_bin = (X > 0).astype(int)
    n = X_bin.shape[0]
    
    # Compute intersection and union sizes
    intersection = X_bin @ X_bin.T
    row_sums = X_bin.sum(axis=1)
    union = row_sums[:, None] + row_sums[None, :] - intersection
    
    # Avoid division by zero
    union = np.maximum(union, 1)
    jaccard_sim = intersection / union
    
    return 1 - jaccard_sim


def _compute_bray_curtis(X: np.ndarray) -> np.ndarray:
    """
    Compute Bray-Curtis dissimilarity matrix.
    
    BC = Σ|x_i - x_j| / Σ(x_i + x_j)
    """
    n = X.shape[0]
    # Normalize to proportions per sample (compositional)
    row_sums = X.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1, row_sums)
    X_prop = X / row_sums
    
    # Compute pairwise
    diff = np.abs(X_prop[:, None, :] - X_prop[None, :, :])
    sum_vals = X_prop[:, None, :] + X_prop[None, :, :]
    
    bc = diff.sum(axis=2) / (sum_vals.sum(axis=2) + 1e-10)
    
    return bc


def _compute_distance_matrix(X: np.ndarray, metric: str = 'braycurtis') -> np.ndarray:
    """
    Compute sample distance matrix.
    
    Parameters
    ----------
    X : np.ndarray
        Sample matrix (samples x features) with non-negative values.
    metric : str
        Distance metric: 'jaccard', 'braycurtis', or any scipy metric.
    
    Returns
    -------
    np.ndarray
        Square distance matrix (n_samples x n_samples).
    """
    metric = metric.lower()
    
    if metric == 'jaccard':
        return _compute_jaccard(X)
    elif metric in ('braycurtis', 'bray_curtis', 'bray-curtis'):
        return _compute_bray_curtis(X)
    else:
        # Use scipy's pdist for other metrics
        # Need to handle the case where metric expects different input
        try:
            dist_vec = pdist(X, metric=metric)
            return squareform(dist_vec)
        except Exception:
            # Fallback to Euclidean on log-transformed data
            X_log = np.log1p(X)
            dist_vec = pdist(X_log, metric='euclidean')
            return squareform(dist_vec)


def _pcoa(distance_matrix: np.ndarray, n_components: int = 2) -> Tuple[np.ndarray, np.ndarray]:
    """
    Principal Coordinate Analysis (classical multidimensional scaling).
    
    Parameters
    ----------
    distance_matrix : np.ndarray
        Square distance matrix.
    n_components : int, default=2
        Number of dimensions to return.
    
    Returns
    -------
    tuple : (coords, eigenvalues)
        coords : np.ndarray (n_samples x n_components)
        eigenvalues : np.ndarray (n_components,)
    """
    n = distance_matrix.shape[0]
    
    # Convert distance to double-centered inner product matrix
    D2 = distance_matrix ** 2
    
    # Centering matrix
    H = np.eye(n) - np.ones((n, n)) / n
    
    # Double centering
    B = -0.5 * H @ D2 @ H
    
    # Eigendecomposition (symmetric)
    eigenvalues, eigenvectors = eigh(B)
    
    # Sort descending
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    
    # Keep only positive eigenvalues
    positive_mask = eigenvalues > 0
    eigenvalues = eigenvalues[positive_mask]
    eigenvectors = eigenvectors[:, positive_mask]

    # Compute coordinates
    coords = eigenvectors * np.sqrt(eigenvalues)

    # Always return exactly n_components columns, zero-padding when the matrix
    # is rank-deficient. A degenerate distance matrix (e.g. Jaccard on a table
    # where every sample shares every feature -> all distances 0) yields NO
    # positive eigenvalues, and returning a 0-column array made callers fail
    # with "index 0 is out of bounds for axis 1 with size 0" instead of
    # producing a plot or a clear message.
    n_ret = min(n_components, coords.shape[1])
    out_coords = np.zeros((n, n_components))
    out_eigen = np.zeros(n_components)
    if n_ret > 0:
        out_coords[:, :n_ret] = coords[:, :n_ret]
        out_eigen[:n_ret] = eigenvalues[:n_ret]

    return out_coords, out_eigen


def _pam_clustering(
    distance_matrix: np.ndarray,
    n_clusters: int,
    random_state: int = 42,
    max_iter: int = 300
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    """
    PAM (Partitioning Around Medoids) clustering.
    
    First tries sklearn_extra.KMedoids if available, otherwise implements
    a custom PAM algorithm or falls back to K-Means on PCoA coordinates.
    
    Parameters
    ----------
    distance_matrix : np.ndarray
        Square distance matrix (n_samples x n_samples).
    n_clusters : int
        Number of clusters.
    random_state : int, default=42
        Random seed for initialization.
    max_iter : int, default=300
        Maximum iterations.
    
    Returns
    -------
    tuple : (labels, medoids, silhouette, used_fallback)
        labels : cluster assignments
        medoids : indices of medoid samples
        silhouette : silhouette score (or -1 if not computable)
        used_fallback : whether fallback method was used
    """
    n_samples = distance_matrix.shape[0]
    
    if n_samples < n_clusters * 2:
        raise ValueError(f"Need at least {n_clusters * 2} samples for {n_clusters} clusters, got {n_samples}")
    
    # Try sklearn-extra KMedoids first
    try:
        from sklearn_extra.cluster import KMedoids
        
        model = KMedoids(
            n_clusters=n_clusters,
            metric='precomputed',
            method='pam',
            max_iter=max_iter,
            random_state=random_state
        )
        model.fit(distance_matrix)
        
        labels = model.labels_
        medoids = model.medoid_indices_
        
        # Silhouette on precomputed distance
        if n_clusters > 1 and len(np.unique(labels)) > 1:
            sil = silhouette_score(distance_matrix, labels, metric='precomputed')
        else:
            sil = -1.0
        
        return labels, medoids, sil, False
    
    except ImportError:
        pass  # Fall through to custom implementation
    
    # Custom PAM implementation
    rng = np.random.RandomState(random_state)
    
    # BUILD phase: initialize medoids
    # Start with the point that minimizes total distance to all others
    total_distances = distance_matrix.sum(axis=1)
    medoids = [int(np.argmin(total_distances))]
    
    # Greedily add medoids
    for _ in range(1, n_clusters):
        # For each non-medoid, compute gain from adding as medoid
        gains = np.zeros(n_samples)
        for i in range(n_samples):
            if i in medoids:
                continue
            # Compute reduction in total cost
            gain = 0
            for j in range(n_samples):
                if j in medoids:
                    continue
                # Current distance to nearest medoid
                current_dist = min(distance_matrix[j, m] for m in medoids)
                # New distance if i is medoid
                new_dist = distance_matrix[j, i]
                if new_dist < current_dist:
                    gain += current_dist - new_dist
            gains[i] = gain
        
        # Add point with max gain
        best = int(np.argmax(gains))
        if best in medoids:
            # Fallback: random non-medoid
            non_medoids = [i for i in range(n_samples) if i not in medoids]
            best = rng.choice(non_medoids)
        medoids.append(best)
    
    medoids = np.array(medoids)
    
    # SWAP phase: iteratively improve medoids
    for iteration in range(max_iter):
        old_medoids = medoids.copy()
        
        # Assign to nearest medoid
        labels = np.argmin(distance_matrix[:, medoids], axis=1)
        
        # Try swapping each medoid with non-medoid
        improved = False
        for mi, med in enumerate(medoids):
            for non_med in range(n_samples):
                if non_med in medoids:
                    continue
                
                # Compute cost with swap
                new_medoids = medoids.copy()
                new_medoids[mi] = non_med
                new_labels = np.argmin(distance_matrix[:, new_medoids], axis=1)
                
                # Total cost
                old_cost = sum(distance_matrix[i, medoids[labels[i]]] for i in range(n_samples))
                new_cost = sum(distance_matrix[i, new_medoids[new_labels[i]]] for i in range(n_samples))
                
                if new_cost < old_cost:
                    medoids = new_medoids
                    improved = True
                    break
            if improved:
                break
        
        if not improved or np.array_equal(old_medoids, medoids):
            break
    
    # Final assignment
    labels = np.argmin(distance_matrix[:, medoids], axis=1)
    
    # Silhouette score
    if n_clusters > 1 and len(np.unique(labels)) > 1:
        sil = silhouette_score(distance_matrix, labels, metric='precomputed')
    else:
        sil = -1.0
    
    return labels, medoids, sil, True


def _kmeans_on_pcoa(
    distance_matrix: np.ndarray,
    n_clusters: int,
    n_components: int = 10,
    random_state: int = 42
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Fallback: K-Means clustering on PCoA coordinates.
    
    Parameters
    ----------
    distance_matrix : np.ndarray
        Square distance matrix.
    n_clusters : int
        Number of clusters.
    n_components : int, default=10
        Number of PCoA dimensions to use.
    random_state : int, default=42
        Random seed.
    
    Returns
    -------
    tuple : (labels, centers, silhouette)
    """
    coords, _ = _pcoa(distance_matrix, n_components=min(n_components, distance_matrix.shape[0] - 1))
    
    model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = model.fit_predict(coords)
    
    if n_clusters > 1 and len(np.unique(labels)) > 1:
        sil = silhouette_score(coords, labels)
    else:
        sil = -1.0
    
    return labels, model.cluster_centers_, sil


def _cluster_composition(
    labels: np.ndarray,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compute cluster composition statistics.
    
    Parameters
    ----------
    labels : np.ndarray
        Cluster assignments.
    metadata_df : pd.DataFrame, optional
        Metadata for enrichment analysis.
    group_column : str, optional
        Column for group enrichment.
    
    Returns
    -------
    dict
        Composition statistics and bar chart data.
    """
    unique_labels = np.unique(labels)
    n_clusters = len(unique_labels)
    n_samples = len(labels)
    
    # Cluster sizes
    sizes = {f"cluster_{i}": int((labels == i).sum()) for i in unique_labels}
    proportions = {k: v / n_samples for k, v in sizes.items()}
    
    composition = {
        'cluster_sizes': sizes,
        'cluster_proportions': proportions,
        'n_clusters': n_clusters,
        'n_samples': n_samples
    }
    
    # Bar chart data
    bar_data = {
        'labels': [f"Cluster {i+1}" for i in unique_labels],
        'values': [sizes[f"cluster_{i}"] for i in unique_labels],
        'proportions': [proportions[f"cluster_{i}"] for i in unique_labels]
    }
    
    # Group enrichment if metadata provided
    if metadata_df is not None and group_column is not None:
        if group_column in metadata_df.columns:
            groups = metadata_df.iloc[:len(labels)][group_column]
            
            enrichment = {}
            for cluster_id in unique_labels:
                cluster_mask = labels == cluster_id
                cluster_groups = groups[cluster_mask]
                group_counts = cluster_groups.value_counts()
                
                enrichment[f"cluster_{cluster_id}"] = {
                    'dominant_group': str(group_counts.index[0]) if len(group_counts) > 0 else None,
                    'group_counts': {str(k): int(v) for k, v in group_counts.items()},
                    'group_proportions': {str(k): float(v / cluster_mask.sum()) for k, v in group_counts.items()}
                }
            
            composition['enrichment'] = enrichment
            
            # Stacked bar data
            all_groups = groups.unique()
            stacked_data = {
                'clusters': [f"Cluster {i+1}" for i in unique_labels],
                'groups': [str(g) for g in all_groups],
                'data': []
            }
            
            for cluster_id in unique_labels:
                cluster_mask = labels == cluster_id
                cluster_groups = groups[cluster_mask]
                group_counts = cluster_groups.value_counts()
                
                row = []
                for g in all_groups:
                    row.append(int(group_counts.get(g, 0)))
                stacked_data['data'].append(row)
            
            composition['stacked_bar'] = stacked_data
    
    return composition


def run_enterotype(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    n_clusters: int = 3,
    distance_metric: str = 'jaccard',
    clustering_method: str = 'pam',
    pcoa_components: int = 2,
    random_state: int = 42,
    max_iter: int = 300,
    group_column: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run enterotype clustering analysis.
    
    Clusters samples into enterotypes using PAM clustering on a distance matrix,
    with PCoA for visualization.
    
    Parameters
    ----------
    df : pd.DataFrame
        Feature abundance table (samples x features) with non-negative values.
    metadata_df : pd.DataFrame, optional
        Sample metadata with sample IDs as index.
    n_clusters : int, default=3
        Number of enterotypes to identify.
    distance_metric : str, default='jaccard'
        Distance metric: 'jaccard', 'braycurtis', or any scipy metric.
    clustering_method : str, default='pam'
        Clustering method: 'pam' (k-medoids), 'kmeans' (K-means on PCoA),
        or 'auto' (try PAM, fallback to K-Means).
    pcoa_components : int, default=2
        Number of PCoA dimensions for visualization.
    random_state : int, default=42
        Random seed.
    max_iter : int, default=300
        Maximum iterations for clustering.
    group_column : str, optional
        Metadata column for group enrichment analysis.
    
    Returns
    -------
    dict
        {
            'plot_data': {
                'pcoa_scatter': {
                    'x': list[float],           # PCoA1
                    'y': list[float],           # PCoA2
                    'sample_ids': list[str],
                    'cluster_labels': list[int],
                    'cluster_colors': list[str],
                    'variance_explained': list[float],
                    'axis_labels': list[str]
                },
                'cluster_bar': {
                    'labels': list[str],
                    'values': list[int],
                    'proportions': list[float]
                }
            },
            'statistics': {
                'n_samples': int,
                'n_features': int,
                'n_clusters': int,
                'silhouette_score': float,
                'cluster_sizes': dict,
                'distance_metric': str,
                'clustering_method': str,
                'used_fallback': bool,
                'variance_explained_pct': list[float]
            },
            'cluster_assignments': pd.Series,
            'distance_matrix': np.ndarray,
            'pcoa_coords': np.ndarray,
            'composition': dict
        }
    """
    n_samples, n_features = df.shape
    
    if n_samples < n_clusters * 2:
        raise ValueError(f"Need at least {n_clusters * 2} samples, got {n_samples}")
    
    # Step 1: Compute distance matrix
    X = df.values.astype(float)
    dist_matrix = _compute_distance_matrix(X, metric=distance_metric)

    # A distance matrix with no variation cannot be clustered into enterotypes.
    # The usual cause is a presence/absence metric (jaccard) on a dense table
    # where every sample carries every feature, which makes all distances 0.
    if not np.any(dist_matrix > 0):
        raise ValueError(
            f"All pairwise distances are zero under the '{distance_metric}' metric, so "
            f"no enterotypes can be distinguished. This happens when every sample "
            f"contains the same set of features (common for genus-level tables with "
            f"'jaccard'). Use an abundance-weighted metric such as 'braycurtis' or "
            f"'jsd' instead."
        )
    
    # Step 2: Clustering
    used_fallback = False
    
    if clustering_method == 'pam':
        try:
            labels, medoids, sil_score, used_fallback = _pam_clustering(
                dist_matrix, n_clusters, random_state=random_state, max_iter=max_iter
            )
            method_used = 'pam'
        except Exception:
            # Fallback to K-Means on PCoA
            labels, centers, sil_score = _kmeans_on_pcoa(
                dist_matrix, n_clusters, random_state=random_state
            )
            used_fallback = True
            method_used = 'kmeans_on_pcoa'
    
    elif clustering_method == 'kmeans':
        labels, centers, sil_score = _kmeans_on_pcoa(
            dist_matrix, n_clusters, random_state=random_state
        )
        method_used = 'kmeans_on_pcoa'
    
    else:  # auto
        try:
            labels, medoids, sil_score, used_fallback = _pam_clustering(
                dist_matrix, n_clusters, random_state=random_state, max_iter=max_iter
            )
            method_used = 'pam'
        except Exception:
            labels, centers, sil_score = _kmeans_on_pcoa(
                dist_matrix, n_clusters, random_state=random_state
            )
            used_fallback = True
            method_used = 'kmeans_on_pcoa'
    
    # Step 3: PCoA for visualization
    pcoa_coords, eigenvalues = _pcoa(dist_matrix, n_components=pcoa_components)
    
    # Variance explained
    total_var = np.sum(np.maximum(eigenvalues, 0))
    if total_var > 0:
        var_explained = eigenvalues / total_var
    else:
        var_explained = np.zeros_like(eigenvalues)
    
    var_explained_pct = (var_explained * 100).tolist()
    
    # Step 4: Build plot data
    sample_ids = list(df.index)
    
    # Assign colors to clusters
    cluster_colors = _get_cluster_colors(n_clusters)
    point_colors = [cluster_colors[l % len(cluster_colors)] for l in labels]
    
    pcoa_scatter = {
        'x': pcoa_coords[:, 0].tolist(),
        'y': pcoa_coords[:, 1].tolist() if pcoa_coords.shape[1] > 1 else [0] * n_samples,
        'sample_ids': sample_ids,
        'cluster_labels': labels.tolist(),
        'cluster_colors': point_colors,
        'variance_explained': var_explained_pct,
        'axis_labels': [
            f"PCoA 1 ({var_explained_pct[0]:.1f}%)" if len(var_explained_pct) > 0 else "PCoA 1",
            f"PCoA 2 ({var_explained_pct[1]:.1f}%)" if len(var_explained_pct) > 1 else "PCoA 2"
        ]
    }
    
    # Cluster composition
    composition = _cluster_composition(labels, metadata_df, group_column)
    
    # Step 5: Statistics
    unique_labels = np.unique(labels)
    cluster_sizes = {int(l): int((labels == l).sum()) for l in unique_labels}
    
    stats_summary = {
        'n_samples': n_samples,
        'n_features': n_features,
        'n_clusters': n_clusters,
        'silhouette_score': float(sil_score),
        'cluster_sizes': cluster_sizes,
        'distance_metric': distance_metric,
        'clustering_method': method_used,
        'used_fallback': used_fallback,
        'variance_explained_pct': var_explained_pct,
        'eigenvalues': eigenvalues[:pcoa_components].tolist()
    }
    
    # Cluster assignments as Series
    cluster_assignments = pd.Series(labels, index=sample_ids, name='enterotype')
    
    return {
        'plot_data': {
            'pcoa_scatter': pcoa_scatter,
            'cluster_bar': composition.get('stacked_bar', {
                'labels': [f"Cluster {i+1}" for i in unique_labels],
                'values': [cluster_sizes[i] for i in unique_labels],
                'proportions': [cluster_sizes[i] / n_samples for i in unique_labels]
            })
        },
        'statistics': stats_summary,
        'cluster_assignments': cluster_assignments,
        'distance_matrix': dist_matrix,
        'pcoa_coords': pcoa_coords,
        'composition': composition
    }


def _get_cluster_colors(n: int) -> list:
    """Generate distinct colors for clusters."""
    base = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]
    if n <= len(base):
        return base[:n]
    
    # Generate more colors
    colors = []
    for i in range(n):
        hue = (i * 0.618033988749895) % 1.0  # Golden ratio for distribution
        saturation = 0.6 + 0.2 * (i % 3)
        value = 0.75 + 0.15 * ((i // 3) % 2)
        
        c = value * saturation
        x = c * (1 - abs((hue * 6) % 2 - 1))
        m = value - c
        
        if hue < 1/6:
            r, g, b = c, x, 0
        elif hue < 2/6:
            r, g, b = x, c, 0
        elif hue < 3/6:
            r, g, b = 0, c, x
        elif hue < 4/6:
            r, g, b = 0, x, c
        elif hue < 5/6:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        
        rgb = tuple(int((v + m) * 255) for v in [r, g, b])
        colors.append(f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")
    
    return colors


# API compatibility alias
def run_enterotype_analysis(df, metadata_df=None, **kwargs):
    """Alias for run_enterotype for backward compatibility."""
    return run_enterotype(df, metadata_df, **kwargs)
