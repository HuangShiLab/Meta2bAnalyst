"""
Redundancy Analysis (RDA) for Multi-omics Integration
=======================================================
RDA is a constrained ordination technique that models the metabolome (response)
as a linear function of the microbiome (explanatory). It is conceptually
PCA on the fitted values from a multivariate regression of Y on X.

This implementation uses QR decomposition for numerical stability.
"""
import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def redundancy_analysis(X: np.ndarray, Y: np.ndarray,
                        n_components: int = 2) -> Dict[str, Any]:
    """
    Redundancy Analysis (RDA) — model Y ~ X + error.

    Parameters
    ----------
    X : array (n_samples, p1) — microbiome (explanatory)
    Y : array (n_samples, p2) — metabolome (response)
    n_components : number of RDA axes to retain

    Returns
    -------
    dict with scores, loadings, eigenvalues, and variance partitioning.
    """
    n, p1 = X.shape
    _, p2 = Y.shape

    # Standardize
    Xs = StandardScaler().fit_transform(X)
    Ys = StandardScaler().fit_transform(Y)

    # QR decomposition of X for stable projection
    Q, R = np.linalg.qr(Xs)

    # Fitted values (predicted Y from X)
    Y_hat = Q @ (Q.T @ Ys)

    # Residuals (unexplained Y)
    Y_res = Ys - Y_hat

    # PCA on fitted Y (RDA axes)
    n_comp = min(n_components, n - 1, p2)

    # Covariance of fitted Y
    Cov_Yhat = Y_hat.T @ Y_hat / (n - 1)
    eigvals, eigvecs = np.linalg.eigh(Cov_Yhat)
    idx = np.argsort(eigvals)[::-1]
    eigvals = eigvals[idx]
    eigvecs = eigvecs[:, idx]

    # RDA scores (samples)
    rda_scores = Y_hat @ eigvecs[:, :n_comp]

    # RDA loadings (features)
    rda_loadings = eigvecs[:, :n_comp]

    # PCA on residuals (unconstrained axes)
    Cov_res = Y_res.T @ Y_res / (n - 1)
    eigvals_res, eigvecs_res = np.linalg.eigh(Cov_res)
    idx_res = np.argsort(eigvals_res)[::-1]
    eigvals_res = eigvals_res[idx_res]
    eigvecs_res = eigvecs_res[:, idx_res]

    res_scores = Y_res @ eigvecs_res[:, :n_comp]
    res_loadings = eigvecs_res[:, :n_comp]

    # Variance partitioning
    total_var = np.trace(np.cov(Ys.T))
    constrained_var = np.trace(np.cov(Y_hat.T))
    unconstrained_var = np.trace(np.cov(Y_res.T))

    prop_constrained = constrained_var / total_var if total_var > 0 else 0.0

    # Eigenvalues (constrained)
    constrained_eig = eigvals[:n_comp].tolist()
    total_constrained_eig = sum(constrained_eig) if sum(constrained_eig) > 0 else 1.0
    prop_eig = [e / total_constrained_eig for e in constrained_eig]

    return {
        'n_samples': n,
        'n_constrained_axes': n_comp,
        'constrained_eigenvalues': constrained_eig,
        'constrained_proportions': prop_eig,
        'total_variance': float(total_var),
        'constrained_variance': float(constrained_var),
        'unconstrained_variance': float(unconstrained_var),
        'proportion_constrained': float(prop_constrained),
        'proportion_unconstrained': float(1 - prop_constrained),
        'rda_scores': rda_scores,
        'rda_loadings': rda_loadings,
        'residual_scores': res_scores,
        'residual_loadings': res_loadings,
    }


def run_rda_analysis(microbiome_df: pd.DataFrame,
                     metabolome_df: pd.DataFrame,
                     metadata_df: Optional[pd.DataFrame] = None,
                     parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    RDA: model metabolome as function of microbiome composition.

    Parameters
    ----------
    microbiome_df : samples × taxa
    metabolome_df : samples × metabolites
    metadata_df : optional
    parameters : n_components (2), test_permutation (True), n_permutations (999)
    """
    params = parameters or {}
    n_components = params.get('n_components', 2)
    test_permutation = params.get('test_permutation', True)
    n_perm = params.get('n_permutations', 999)

    common = microbiome_df.index.intersection(metabolome_df.index)
    if len(common) == 0:
        raise ValueError("No common samples between microbiome and metabolome")

    X = microbiome_df.loc[common].values.astype(float)
    Y = metabolome_df.loc[common].values.astype(float)

    # Remove zero-variance
    X = X[:, X.std(axis=0) > 0]
    Y = Y[:, Y.std(axis=0) > 0]

    rda_result = redundancy_analysis(X, Y, n_components=n_components)

    # Permutation test for overall model significance
    f_stat = None
    p_value = None
    if test_permutation:
        obs_constrained = rda_result['proportion_constrained']
        perm_stats = []
        for i in range(n_perm):
            idx = np.random.permutation(X.shape[0])
            perm_rda = redundancy_analysis(X[idx], Y, n_components=n_components)
            perm_stats.append(perm_rda['proportion_constrained'])
        perm_stats = np.array(perm_stats)
        p_value = (perm_stats >= obs_constrained).mean()
        f_stat = obs_constrained / (1 - obs_constrained + 1e-10)  # pseudo-F

    # Build DataFrames for output
    x_features = microbiome_df.loc[common].columns[microbiome_df.loc[common].std(axis=0) > 0].tolist()
    y_features = metabolome_df.loc[common].columns[metabolome_df.loc[common].std(axis=0) > 0].tolist()

    rda_scores_df = pd.DataFrame(
        rda_result['rda_scores'],
        index=common,
        columns=[f'RDA{i+1}' for i in range(n_components)]
    )
    rda_loadings_df = pd.DataFrame(
        rda_result['rda_loadings'],
        index=y_features,
        columns=[f'RDA{i+1}' for i in range(n_components)]
    )

    # Top loading metabolites per axis
    top_metabolites = {}
    for i in range(n_components):
        col = f'RDA{i+1}'
        loadings = rda_loadings_df[col].abs().sort_values(ascending=False)
        top_metabolites[col] = loadings.head(20).to_dict()

    # X loadings (biplot scores) — correlation of taxa with RDA axes
    Xs = StandardScaler().fit_transform(X)
    x_loadings = np.corrcoef(Xs.T, rda_result['rda_scores'].T)[:X.shape[1], X.shape[1]:]
    x_loadings_df = pd.DataFrame(
        x_loadings,
        index=x_features,
        columns=[f'RDA{i+1}' for i in range(n_components)]
    )
    top_taxa = {}
    for i in range(n_components):
        col = f'RDA{i+1}'
        loadings = x_loadings_df[col].abs().sort_values(ascending=False)
        top_taxa[col] = loadings.head(20).to_dict()

    # Plot data
    plot_data = _rda_plot_data(rda_scores_df, x_loadings_df, rda_loadings_df, metadata_df, common, x_features, y_features)

    return {
        'n_samples': len(common),
        'n_taxa': X.shape[1],
        'n_metabolites': Y.shape[1],
        'proportion_constrained': rda_result['proportion_constrained'],
        'proportion_unconstrained': rda_result['proportion_unconstrained'],
        'constrained_eigenvalues': rda_result['constrained_eigenvalues'],
        'constrained_proportions': rda_result['constrained_proportions'],
        'permutation_pvalue': float(p_value) if p_value is not None else None,
        'pseudo_f': float(f_stat) if f_stat is not None else None,
        'rda_scores': rda_scores_df.to_dict(),
        'metabolite_loadings': rda_loadings_df.to_dict(),
        'taxa_loadings': x_loadings_df.to_dict(),
        'top_metabolites': top_metabolites,
        'top_taxa': top_taxa,
        'plot_data': plot_data,
    }


def _rda_plot_data(rda_scores_df, x_loadings_df, y_loadings_df, metadata_df, common, x_features, y_features):
    """Build triplot data: samples + taxa arrows + metabolite arrows."""
    traces = []

    # Sample scores
    group_col = None
    if metadata_df is not None:
        for col in metadata_df.columns:
            if metadata_df[col].dtype == 'object' or metadata_df[col].nunique() < 15:
                group_col = col
                break

    if group_col and group_col in metadata_df.columns:
        common_meta = common.intersection(metadata_df.index)
        groups = metadata_df.loc[common_meta, group_col]
        for grp in groups.unique():
            mask = groups == grp
            samps = mask[mask].index
            traces.append({
                'x': rda_scores_df.loc[samps, 'RDA1'].tolist(),
                'y': rda_scores_df.loc[samps, 'RDA2'].tolist(),
                'mode': 'markers',
                'name': str(grp),
                'text': samps.tolist(),
                'marker': {'size': 10, 'opacity': 0.8},
            })
    else:
        traces.append({
            'x': rda_scores_df['RDA1'].tolist(),
            'y': rda_scores_df['RDA2'].tolist(),
            'mode': 'markers',
            'name': 'Samples',
            'text': rda_scores_df.index.tolist(),
            'marker': {'size': 10, 'opacity': 0.8},
        })

    # Taxa arrows (scaled for visibility)
    scale = 0.3
    for taxon in x_features[:20]:  # top 20
        if taxon in x_loadings_df.index:
            x = x_loadings_df.loc[taxon, 'RDA1'] * scale
            y = x_loadings_df.loc[taxon, 'RDA2'] * scale
            traces.append({
                'x': [0, x], 'y': [0, y],
                'mode': 'lines+text',
                'line': {'color': 'red', 'width': 1},
                'text': ['', taxon],
                'textposition': 'top center',
                'showlegend': False,
                'hoverinfo': 'text',
            })

    return {
        'data': traces,
        'layout': {
            'title': 'RDA Triplot: Samples + Taxa Arrows',
            'xaxis': {'title': 'RDA1'},
            'yaxis': {'title': 'RDA2'},
            'hovermode': 'closest',
        }
    }
