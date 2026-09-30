"""
Meta2bAnalyst - Cross-omics Integration Module (Procrustes + Mantel Test)
Implements Procrustes analysis and Mantel test for comparing sample structures
across different omics data types (e.g., 16S vs metabolomics).

References:
  - Procrustes: Gower 1975, Psychometrika 40:33-51
  - Mantel: Mantel 1967, Cancer Res 27:209-220
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial.distance import braycurtis, pdist, squareform
from scipy.stats import pearsonr, spearmanr

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


# ─────────────────────────────── Procrustes Analysis

def procrustes_analysis(
    X: np.ndarray,
    Y: np.ndarray,
    n_permutations: int = 999,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Symmetric Procrustes analysis with a permutation test (PROTEST).

    Both configurations are centred and scaled to unit sum of squares, Y is
    rotated (reflections allowed) onto X, and the residual sum of squares is
    the symmetric Procrustes statistic m^2 = 1 - r^2, where r is the Procrustes
    correlation (Gower 1975; Peres-Neto & Jackson 2001; vegan::protest).
    m^2 lies in [0, 1]: 0 for identical configurations, 1 for none shared.

    The previous implementation scaled Y by the ratio of matrix norms instead
    of the least-squares optimum and reported SS/||X||^2 as a "normalised m2",
    which equals 2(1 - r) and can exceed 1. The rotation itself was right.

    Args:
        X, Y: Configurations (n_samples x k), rows in the same sample order.
        n_permutations: Row permutations of Y for the significance of r
            (0 skips the test).
        random_seed: Seed for the permutation RNG (reproducible p-values).

    Returns:
        Dict with the standardised X, the fitted Y, m2, procrustes_r, pvalue.
    """
    from scipy.spatial import procrustes as _scipy_procrustes

    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    n = X.shape[0]
    if n != Y.shape[0]:
        raise ValueError(f"X and Y must have same number of rows, got {n} and {Y.shape[0]}")
    # scipy needs equal dimensionality: pad the narrower configuration with zeros
    # (adds no variance, so the fit is unchanged).
    k = max(X.shape[1], Y.shape[1])
    if X.shape[1] < k:
        X = np.hstack([X, np.zeros((n, k - X.shape[1]))])
    if Y.shape[1] < k:
        Y = np.hstack([Y, np.zeros((n, k - Y.shape[1]))])

    X_std, Y_fit, m2 = _scipy_procrustes(X, Y)
    r = float(np.sqrt(max(0.0, 1.0 - m2)))

    pvalue = None
    if n_permutations and n_permutations > 0:
        rng = np.random.default_rng(random_seed)
        hits = 0
        for _ in range(n_permutations):
            _, _, m2_perm = _scipy_procrustes(X, Y[rng.permutation(n)])
            if m2_perm <= m2 + 1e-12:
                hits += 1
        pvalue = (hits + 1) / (n_permutations + 1)

    return {
        "X_transformed": X_std,
        "Y_transformed": Y_fit,
        "m2": float(m2),
        "procrustes_r": r,
        "pvalue": pvalue,
        "n_permutations": int(n_permutations or 0),
        "n_samples": n,
    }


def _zscore(df: pd.DataFrame) -> pd.DataFrame:
    return ((df - df.mean(axis=0)) / (df.std(axis=0) + 1e-10)).fillna(0)


def _ordinate(samples_x_features: pd.DataFrame, metric: str, n_components: int) -> Tuple[np.ndarray, str]:
    """Ordinate one table. Euclidean -> PCA of z-scored features (identical to a
    PCoA of Euclidean distances on them); any other metric -> PCoA of that
    ecological distance on the supplied values."""
    from sklearn.decomposition import PCA

    n = samples_x_features.shape[0]
    k = min(n_components, n - 1)
    if metric == "euclidean":
        coords = PCA(n_components=k).fit_transform(_zscore(samples_x_features))
        return coords, "PCA of z-scored features"
    values = samples_x_features.values.astype(float)
    if metric in ("braycurtis", "jaccard") and (values < 0).any():
        raise ValueError(
            f"{metric} distance needs non-negative abundances; this table has negative "
            "values (already log-ratio transformed?). Use metric='euclidean'."
        )
    zero = values.sum(axis=1) == 0
    if zero.any():
        raise ValueError(
            f"{int(zero.sum())} sample(s) have zero total abundance; {metric} distance is undefined."
        )
    from skbio import DistanceMatrix
    from skbio.stats.ordination import pcoa as _pcoa

    dm = DistanceMatrix(squareform(pdist(values, metric=metric)))
    coords = _pcoa(dm, number_of_dimensions=k).samples.values[:, :k]
    return coords, f"PCoA of {metric} distances"


def run_procrustes(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    method: str = "pcoa",
    n_components: int = 2,
    metric_1: str = "braycurtis",
    metric_2: str = "euclidean",
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """Run Procrustes analysis on two feature tables.

    Args:
        df1: First feature table (features x samples), e.g. microbiome counts.
        df2: Second feature table (features x samples), e.g. metabolome.
        method: 'pcoa' ordinates each table with its own metric (default:
            Bray-Curtis PCoA for df1, PCA of z-scored features for df2);
            'pca' uses PCA of z-scored features for both (the behaviour that
            used to be mislabelled 'pcoa'); 'raw' uses the tables directly.
        n_components: Ordination axes kept for the superimposition.
        metric_1, metric_2: Distance metrics for method='pcoa'.
        n_permutations: Row permutations for the PROTEST p-value.

    Returns:
        Dict with m2 (symmetric, 0-1), procrustes_r, pvalue and coordinates.
    """
    common_samples = df1.columns.intersection(df2.columns)
    if len(common_samples) < 3:
        return {"error": f"Need >=3 common samples, got {len(common_samples)}"}

    X = df1[common_samples].T  # samples x features
    Y = df2[common_samples].T

    if method == "pcoa":
        X_coords, ord1 = _ordinate(X, metric_1, n_components)
        Y_coords, ord2 = _ordinate(Y, metric_2, n_components)
    elif method == "pca":
        X_coords, ord1 = _ordinate(X, "euclidean", n_components)
        Y_coords, ord2 = _ordinate(Y, "euclidean", n_components)
    elif method == "raw":
        X_coords, ord1 = X.values.astype(float), "raw feature values"
        Y_coords, ord2 = Y.values.astype(float), "raw feature values"
    else:
        raise ValueError(f"Unknown Procrustes method '{method}' (use 'pcoa', 'pca' or 'raw')")

    result = procrustes_analysis(X_coords, Y_coords, n_permutations=n_permutations)

    Xt, Yt = result["X_transformed"], result["Y_transformed"]
    coords_df = pd.DataFrame({
        "sample": common_samples,
        "X_PC1": Xt[:, 0],
        "X_PC2": Xt[:, 1] if Xt.shape[1] > 1 else np.zeros(len(common_samples)),
        "Y_PC1": Yt[:, 0],
        "Y_PC2": Yt[:, 1] if Yt.shape[1] > 1 else np.zeros(len(common_samples)),
    })

    return {
        "method": method,
        "ordination": {"table_1": ord1, "table_2": ord2, "n_components": int(X_coords.shape[1])},
        "n_common_samples": len(common_samples),
        "common_samples": list(common_samples),
        "m2": result["m2"],
        "procrustes_r": result["procrustes_r"],
        "pvalue": result["pvalue"],
        "n_permutations": result["n_permutations"],
        "statistic_note": "m2 = 1 - r^2 (symmetric Procrustes); 0 = identical, 1 = no shared structure",
        "engine": "python::scipy.spatial.procrustes",
        "coordinates": coords_df.to_dict(orient="records"),
    }


# ─────────────────────────────── Mantel Test

def mantel_test(
    dist1: np.ndarray,
    dist2: np.ndarray,
    method: str = "pearson",
    n_permutations: int = 999,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Mantel test between two square distance matrices (scikit-bio).

    The null distribution permutes *sample labels* -- rows and columns of one
    matrix together (Mantel 1967). The previous implementation shuffled the
    individual distances of the flattened upper triangle, which destroys the
    dependence among distances that share a sample and produces a null
    distribution several times too narrow (anti-conservative P values).

    Args:
        dist1, dist2: Square (n x n) distance matrices in the same sample order.
        method: 'pearson' or 'spearman'.
        n_permutations: Label permutations for the p-value.
        random_seed: Seed for reproducible p-values.
    """
    from skbio import DistanceMatrix
    from skbio.stats.distance import mantel as _skbio_mantel

    d1 = np.asarray(dist1, dtype=float)
    d2 = np.asarray(dist2, dtype=float)
    if d1.ndim != 2 or d1.shape[0] != d1.shape[1] or d1.shape != d2.shape:
        raise ValueError(
            "mantel_test needs two square distance matrices of the same shape; "
            "flattened distance vectors cannot be permuted correctly."
        )
    ids = [str(i) for i in range(d1.shape[0])]
    corr, p_value, _ = _skbio_mantel(
        DistanceMatrix(np.ascontiguousarray(d1), ids=ids),
        DistanceMatrix(np.ascontiguousarray(d2), ids=ids),
        method=method, permutations=n_permutations, seed=random_seed,
    )
    return {
        "correlation": float(corr),
        "p_value": float(p_value),
        "n_permutations": n_permutations,
        "method": method,
        "permutation_scheme": "sample labels (rows and columns permuted together)",
        "engine": "python::skbio.stats.distance.mantel",
    }


def run_mantel(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    metric: str = "braycurtis",
    method: str = "pearson",
    n_permutations: int = 999,
    metric_2: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Mantel test on two feature tables.

    Args:
        df1, df2: Feature tables (features x samples).
        metric: Distance metric for df1 (and for df2 unless metric_2 is given).
        metric_2: Optional separate metric for df2.
        method: 'pearson' or 'spearman'.
        n_permutations: Number of permutations.

    Returns:
        Dict with Mantel test results.
    """
    common_samples = df1.columns.intersection(df2.columns)
    if len(common_samples) < 3:
        return {"error": f"Need >=3 common samples, got {len(common_samples)}"}

    metric_2 = metric_2 or metric
    dist1_matrix = squareform(pdist(df1[common_samples].T, metric=metric))
    dist2_matrix = squareform(pdist(df2[common_samples].T, metric=metric_2))
    if np.isnan(dist1_matrix).any() or np.isnan(dist2_matrix).any():
        return {"error": f"{metric} distance is undefined for some samples (all-zero profiles?)"}

    result = mantel_test(dist1_matrix, dist2_matrix, method=method, n_permutations=n_permutations)

    return {
        "n_common_samples": len(common_samples),
        "common_samples": list(common_samples),
        "metric": metric,
        "metric_2": metric_2,
        **result,
    }


# ─────────────────────────────── Plotly Visualizations

def plotly_procrustes(coords_df: pd.DataFrame, metadata_df: Optional[pd.DataFrame] = None,
                      group_column: Optional[str] = None) -> dict:
    """Generate Procrustes comparison plot.
    
    Args:
        coords_df: DataFrame with X_PC1, X_PC2, Y_PC1, Y_PC2 columns.
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.
        
    Returns:
        Plotly figure JSON dict.
    """
    fig = go.Figure()

    # Paired-sample connectors batched into ONE trace with None breaks.
    # The previous version added a separate trace per sample (261 traces for
    # the demo data), which bloated the payload and slowed rendering.
    lx: list = []
    ly: list = []
    for _, row in coords_df.iterrows():
        lx += [row["X_PC1"], row["Y_PC1"], None]
        ly += [row["X_PC2"], row["Y_PC2"], None]
    fig.add_trace(go.Scatter(
        x=lx,
        y=ly,
        mode="lines",
        line=dict(color="gray", width=0.5, dash="dot"),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Sample names live in the hover tooltip only. Printing every label at a
    # fixed position (markers+text) turned dense plots into an unreadable
    # wall of overlapping text.
    fig.add_trace(go.Scatter(
        x=coords_df["X_PC1"],
        y=coords_df["X_PC2"],
        mode="markers",
        name="Microbiome",
        text=coords_df["sample"],
        marker=dict(size=9, color="#1f77b4", symbol="circle", opacity=0.7),
        hovertemplate="<b>%{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
    ))

    # Plot Y coordinates (transformed)
    fig.add_trace(go.Scatter(
        x=coords_df["Y_PC1"],
        y=coords_df["Y_PC2"],
        mode="markers",
        name="Metabolome (Procrustes aligned)",
        text=coords_df["sample"],
        marker=dict(size=9, color="#ff7f0e", symbol="diamond", opacity=0.7),
        hovertemplate="<b>%{text}</b><br>PC1: %{x:.3f}<br>PC2: %{y:.3f}<extra></extra>",
    ))

    fig.update_layout(
        title="Procrustes Analysis: Cross-omics Comparison",
        xaxis_title="PC1",
        yaxis_title="PC2",
        template="plotly_white",
        height=500,
        width=600,
        showlegend=True,
    )

    return fig.to_dict()


def plotly_mantel_scatter(dist1_flat: np.ndarray, dist2_flat: np.ndarray,
                          correlation: float, p_value: float) -> dict:
    """Generate Mantel test scatter plot.
    
    Args:
        dist1_flat, dist2_flat: Flattened distance vectors.
        correlation: Correlation coefficient.
        p_value: P-value.
        
    Returns:
        Plotly figure JSON dict.
    """
    fig = go.Figure(data=go.Scatter(
        x=dist1_flat,
        y=dist2_flat,
        mode="markers",
        marker=dict(size=8, opacity=0.5, color="#2ca02c"),
        hovertemplate="Microbiome dist: %{x:.3f}<br>Metabolome dist: %{y:.3f}<extra></extra>",
    ))
    
    # Add regression line
    z = np.polyfit(dist1_flat, dist2_flat, 1)
    p = np.poly1d(z)
    x_line = np.linspace(dist1_flat.min(), dist1_flat.max(), 100)
    
    fig.add_trace(go.Scatter(
        x=x_line,
        y=p(x_line),
        mode="lines",
        line=dict(color="#d62728", width=2),
        name=f"r={correlation:.3f}, p={p_value:.4f}",
    ))
    
    fig.update_layout(
        title=f"Mantel Test: r={correlation:.3f}, p={p_value:.4f}",
        xaxis_title="Microbiome pairwise distance",
        yaxis_title="Metabolome pairwise distance",
        template="plotly_white",
        height=500,
        width=500,
        showlegend=True,
    )
    
    return fig.to_dict()


# ─────────────────────────────── Pairwise Cross-omics Correlation


def run_cross_omics_correlation(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    method: str = "spearman",
    alpha: float = 0.05,
    top_heatmap_metabolites: int = 60,
    max_reported_pairs: int = 500,
) -> Dict[str, Any]:
    """Pairwise feature-level correlation between two omics layers.

    Computes the full |df1 features| x |df2 features| correlation matrix
    (e.g. bacterial genera x metabolites) over the samples shared by both
    tables, with per-pair p-values and Benjamini-Hochberg FDR correction.

    Args:
        df1: Feature table (features x samples), e.g. genus-level microbiome.
        df2: Feature table (features x samples), e.g. metabolome.
        method: 'spearman' (default) or 'pearson'.
        alpha: FDR significance threshold (default 0.05).
        top_heatmap_metabolites: Number of df2 features (ranked by best FDR)
            shown in the heatmap. All df1 features are always shown.
        max_reported_pairs: Cap on significant pairs returned in the report.

    Returns:
        Dict with correlation statistics, significant pairs, and heatmap data.
    """
    from scipy.stats import rankdata, t as t_dist

    from app.services.analysis_engine import adjust_pvalues

    if df2 is None:
        return {"error": "Cross-omics correlation requires both omics feature tables."}

    # 1. Align on shared samples
    common = df1.columns.intersection(df2.columns)
    if len(common) < 5:
        return {
            "error": (
                f"Only {len(common)} samples are shared between the two omics tables "
                "(need >= 5). Check that sample IDs match across both files."
            )
        }
    X1 = df1[common].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    X2 = df2[common].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    n = len(common)

    # Drop zero-variance features (correlation undefined)
    v1 = X1.var(axis=1)
    v2 = X2.var(axis=1)
    X1 = X1.loc[v1 > 0]
    X2 = X2.loc[v2 > 0]
    if X1.empty or X2.empty:
        return {"error": "No variable features left after filtering zero-variance rows."}

    # 2. Rank-transform (Spearman) or keep raw (Pearson), then row-wise z-score
    if method == "spearman":
        A = np.apply_along_axis(rankdata, 1, X1.values)
        B = np.apply_along_axis(rankdata, 1, X2.values)
    else:
        A = X1.values.astype(float)
        B = X2.values.astype(float)
    A = (A - A.mean(axis=1, keepdims=True)) / A.std(axis=1, keepdims=True)
    B = (B - B.mean(axis=1, keepdims=True)) / B.std(axis=1, keepdims=True)

    # 3. Full correlation matrix + t-approximation p-values
    R = (A @ B.T) / (n - 1)
    R = np.clip(R, -1.0, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        T = R * np.sqrt((n - 2) / np.maximum(1e-12, 1.0 - R ** 2))
    P = 2.0 * t_dist.sf(np.abs(T), df=n - 2)
    P = np.nan_to_num(P, nan=1.0)

    # 4. BH-FDR over all pairs
    Q = adjust_pvalues(P.ravel(), "fdr_bh").reshape(P.shape)

    # 5. Significant pairs (FDR < alpha), sorted by FDR then |rho|
    sig_idx = np.argwhere(Q < alpha)
    pairs: List[Dict[str, Any]] = []
    if sig_idx.size:
        order = sorted(
            sig_idx.tolist(),
            key=lambda ij: (Q[ij[0], ij[1]], -abs(R[ij[0], ij[1]])),
        )
        for i, j in order[:max_reported_pairs]:
            pairs.append({
                "feature_1": str(X1.index[i]),
                "feature_2": str(X2.index[j]),
                "correlation": float(R[i, j]),
                "pvalue": float(P[i, j]),
                "fdr": float(Q[i, j]),
            })

    n_sig_fdr = int((Q < alpha).sum())
    n_sig_p = int((P < alpha).sum())

    # 6. Heatmap: all df1 features x top df2 features (by best FDR), clustered rows
    best_q_per_metabolite = Q.min(axis=0)
    top_j = np.argsort(best_q_per_metabolite)[: min(top_heatmap_metabolites, R.shape[1])]
    top_j = np.sort(top_j)
    heat_z = R[:, top_j]
    heat_x = [str(c) for c in X2.index[top_j]]
    heat_y = [str(ix) for ix in X1.index]

    # Cluster df1 rows by correlation profile for readability
    try:
        from scipy.cluster.hierarchy import leaves_list, linkage
        if heat_z.shape[0] > 2:
            row_order = leaves_list(linkage(pdist(heat_z, metric="correlation"), method="average"))
            heat_z = heat_z[row_order]
            heat_y = [heat_y[k] for k in row_order]
    except Exception:
        pass

    fig = go.Figure(data=go.Heatmap(
        z=heat_z,
        x=heat_x,
        y=heat_y,
        colorscale="RdBu_r",
        zmid=0,
        zmin=-1,
        zmax=1,
        colorbar=dict(title=f"{method.capitalize()} rho"),
        hovertemplate="Genus: %{y}<br>Metabolite: %{x}<br>rho: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        title=(
            f"Cross-omics Correlation Heatmap ({method.capitalize()})<br>"
            f"<sup>{R.shape[0]} genera x {R.shape[1]} metabolites = {R.size:,} pairs; "
            f"{n_sig_fdr:,} significant at FDR<{alpha} "
            f"(heatmap shows top {len(heat_x)} metabolites by best FDR)</sup>"
        ),
        xaxis_title=f"Metabolites (top {len(heat_x)} of {R.shape[1]})",
        yaxis_title=f"Bacterial genera (n={R.shape[0]})",
        template="plotly_white",
        height=max(500, 16 * len(heat_y) + 200),
        width=1000,
    )

    return {
        "method": method,
        "n_samples": n,
        "n_features_1": int(R.shape[0]),
        "n_features_2": int(R.shape[1]),
        "n_pairs_tested": int(R.size),
        "n_significant_fdr": n_sig_fdr,
        "n_significant_p": n_sig_p,
        "alpha": alpha,
        "significant_pairs": pairs,
        "plot_data": fig.to_dict(),
    }


# ─────────────────────────────── Main Runner

def run_cross_omics_analysis(
    df1: pd.DataFrame,
    df2: Optional[pd.DataFrame] = None,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run cross-omics analysis (Procrustes and/or Mantel).

    Args:
        df1: Primary feature table (features x samples), e.g. microbiome.
        df2: Secondary feature table (features x samples), e.g. metabolome.
             Required for analysis_type='correlation'. If None for procrustes/mantel,
             a noisy version of df1 is used (testing only).
        metadata_df: Optional metadata.
        parameters: Dict with keys:
            - analysis_type: 'procrustes', 'mantel', 'correlation', or 'both' (default 'both')
            - procrustes_method: 'pcoa', 'pca' or 'raw' (default 'pcoa')
            - procrustes_metric_1 / _2: metrics for 'pcoa' (default braycurtis / euclidean)
            - mantel_metric: 'braycurtis', 'euclidean' (default 'braycurtis')
            - mantel_method: 'pearson' or 'spearman' (default 'pearson')
            - n_permutations: int (default 999)
            - group_column: metadata column for coloring

    Returns:
        Normalized dict with keys plot_data, statistics, data, and method-specific keys.
    """
    params = parameters or {}
    analysis_type = params.get("analysis_type", "both")
    procrustes_method = params.get("procrustes_method", "pcoa")
    mantel_metric = params.get("mantel_metric", "braycurtis")
    mantel_method = params.get("mantel_method", "pearson")
    n_permutations = params.get("n_permutations", 999)
    group_column = params.get("group_column")

    logger.info(
        f"Starting cross-omics analysis: type={analysis_type}, "
        f"procrustes={procrustes_method}, mantel={mantel_metric}"
    )

    # Never fabricate a second table. (This used to add noise to df1 and report
    # Procrustes/Mantel results on the copy when no metabolome was loaded.)
    if df2 is None:
        raise ValueError(
            "Cross-omics analysis needs a second omics table (e.g. metabolome) "
            "for the same samples; none is loaded in this session."
        )

    result: Dict[str, Any] = {"analysis_type": analysis_type}

    # 0. Pairwise cross-omics correlation (feature-level, e.g. genus x metabolite)
    if analysis_type == "correlation":
        corr_method = params.get("correlation_method", "spearman")
        corr_result = run_cross_omics_correlation(df1, df2, method=corr_method)
        if "error" in corr_result:
            return corr_result

        result["correlation"] = _sanitize_json({
            "method": corr_result["method"],
            "n_samples": corr_result["n_samples"],
            "n_features_1": corr_result["n_features_1"],
            "n_features_2": corr_result["n_features_2"],
            "n_pairs_tested": corr_result["n_pairs_tested"],
            "n_significant_fdr": corr_result["n_significant_fdr"],
            "n_significant_p": corr_result["n_significant_p"],
            "alpha": corr_result["alpha"],
        })
        result["plot_data"] = corr_result["plot_data"]
        result["statistics"] = {
            "method": corr_result["method"],
            "n_samples": corr_result["n_samples"],
            "n_genera": corr_result["n_features_1"],
            "n_metabolites": corr_result["n_features_2"],
            "n_pairs_tested": corr_result["n_pairs_tested"],
            "n_significant_fdr": corr_result["n_significant_fdr"],
            "n_significant_p_nominal": corr_result["n_significant_p"],
            "fdr_threshold": corr_result["alpha"],
        }
        result["data"] = _sanitize_json(corr_result["significant_pairs"])
        logger.info(
            f"Cross-omics correlation complete: {corr_result['n_pairs_tested']:,} pairs, "
            f"{corr_result['n_significant_fdr']:,} significant at FDR<{corr_result['alpha']}"
        )
        return result

    # 1. Procrustes analysis (if requested)
    if analysis_type in ("procrustes", "both"):
        procrustes_result = run_procrustes(
            df1, df2, method=procrustes_method,
            metric_1=params.get("procrustes_metric_1", "braycurtis"),
            metric_2=params.get("procrustes_metric_2", "euclidean"),
            n_permutations=n_permutations,
        )
        if "error" in procrustes_result:
            return procrustes_result

        result["procrustes"] = _sanitize_json({
            k: procrustes_result[k] for k in (
                "method", "ordination", "n_common_samples", "m2", "procrustes_r",
                "pvalue", "n_permutations", "statistic_note", "engine", "coordinates",
            )
        })

    # 2. Mantel test (if requested)
    if analysis_type in ("mantel", "both"):
        mantel_result = run_mantel(df1, df2, metric=mantel_metric, method=mantel_method,
                                   n_permutations=n_permutations, metric_2=params.get("mantel_metric_2"))
        if "error" in mantel_result:
            return mantel_result
        result["mantel"] = _sanitize_json(mantel_result)

    # 3. Generate plots
    plots: Dict[str, Any] = {}

    if "procrustes" in result:
        coords_df = pd.DataFrame(result["procrustes"]["coordinates"])
        plots["procrustes_plot"] = plotly_procrustes(coords_df, metadata_df, group_column)

    if "mantel" in result:
        common_samples = df1.columns.intersection(df2.columns)
        dist1_matrix = squareform(pdist(df1[common_samples].T, metric=mantel_metric))
        dist2_matrix = squareform(pdist(df2[common_samples].T, metric=params.get("mantel_metric_2") or mantel_metric))
        n = len(common_samples)
        idx = np.triu_indices(n, k=1)
        dist1_flat = dist1_matrix[idx]
        dist2_flat = dist2_matrix[idx]
        plots["mantel_scatter"] = plotly_mantel_scatter(
            dist1_flat, dist2_flat, result["mantel"]["correlation"], result["mantel"]["p_value"]
        )

    result["plots"] = plots

    # 4. Normalize top-level output for the Agent integrator / frontend
    if analysis_type == "procrustes":
        result["plot_data"] = plots.get("procrustes_plot")
        result["statistics"] = {
            "m2": result["procrustes"]["m2"],
            "procrustes_r": result["procrustes"]["procrustes_r"],
            "pvalue": result["procrustes"]["pvalue"],
            "n_permutations": result["procrustes"]["n_permutations"],
            "n_common_samples": result["procrustes"]["n_common_samples"],
        }
    elif analysis_type == "mantel":
        result["plot_data"] = plots.get("mantel_scatter")
        result["statistics"] = {
            "correlation": result["mantel"]["correlation"],
            "pvalue": result["mantel"]["p_value"],
            "n_permutations": result["mantel"]["n_permutations"],
            "n_common_samples": result["mantel"]["n_common_samples"],
        }
    else:
        result["plot_data"] = plots.get("procrustes_plot")
        result["statistics"] = {
            "procrustes_m2": result["procrustes"]["m2"],
            "procrustes_r": result["procrustes"]["procrustes_r"],
            "procrustes_pvalue": result["procrustes"]["pvalue"],
            "mantel_correlation": result["mantel"]["correlation"],
            "mantel_pvalue": result["mantel"]["p_value"],
        }

    logger.info("Cross-omics analysis complete")
    return result
