"""
Sparse Canonical Correlation Analysis (Sparse CCA)
====================================================
Integrates microbiome and metabolome data by finding sparse linear combinations
of features from each omics layer that maximize their cross-correlation.

Uses iterative soft-thresholding (ISTA) to enforce sparsity (L1 penalty) on
canonical vectors, producing interpretable multi-omics associations.
"""
import logging
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def _soft_threshold(x: np.ndarray, gamma: float) -> np.ndarray:
    """Soft-thresholding operator (proximal operator for L1)."""
    return np.sign(x) * np.maximum(np.abs(x) - gamma, 0.0)


def sparse_cca(X: np.ndarray, Y: np.ndarray,
               n_components: int = 2,
               sparsity_x: float = 0.3,
               sparsity_y: float = 0.3,
               max_iter: int = 500,
               tol: float = 1e-6,
               learning_rate: float = 0.01) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Sparse CCA via iterative soft-thresholding (ISTA).

    Parameters
    ----------
    X : array, shape (n_samples, p1) — microbiome data
    Y : array, shape (n_samples, p2) — metabolome data
    n_components : number of canonical components
    sparsity_x : fraction of non-zero weights to retain in X (lower = sparser)
    sparsity_y : fraction of non-zero weights to retain in Y
    max_iter : maximum iterations per component
    tol : convergence tolerance

    Returns
    -------
    u : canonical weights for X (p1 × n_components)
    v : canonical weights for Y (p2 × n_components)
    correlations : canonical correlations per component
    """
    n, p1 = X.shape
    _, p2 = Y.shape

    # Standardize
    Xs = StandardScaler().fit_transform(X)
    Ys = StandardScaler().fit_transform(Y)

    # Covariance matrix
    Cxy = Xs.T @ Ys / n

    u = np.zeros((p1, n_components))
    v = np.zeros((p2, n_components))
    correlations = np.zeros(n_components)

    for k in range(n_components):
        # Initialize with standard CCA (SVD of residual covariance)
        if k == 0:
            R = Cxy.copy()
        else:
            # Deflate: remove previous components
            Xk = Xs @ u[:, :k]
            Yk = Ys @ v[:, :k]
            R = Cxy - (Xs.T @ Xk) @ (Yk.T @ Ys) / n

        # Initialize with SVD top singular vectors
        try:
            U_svd, s, Vt_svd = np.linalg.svd(R, full_matrices=False)
            uk = U_svd[:, 0]
            vk = Vt_svd[0, :]
        except np.linalg.LinAlgError:
            uk = np.random.randn(p1)
            vk = np.random.randn(p2)
            uk = uk / np.linalg.norm(uk)
            vk = vk / np.linalg.norm(vk)

        # ISTA iterations
        for it in range(max_iter):
            uk_old = uk.copy()
            vk_old = vk.copy()

            # Update u
            grad_u = -R @ vk
            uk_temp = uk - learning_rate * grad_u
            gamma_u = np.percentile(np.abs(uk_temp), (1 - sparsity_x) * 100)
            uk = _soft_threshold(uk_temp, gamma_u)
            uk_norm = np.linalg.norm(uk)
            if uk_norm > 0:
                uk = uk / uk_norm

            # Update v
            grad_v = -R.T @ uk
            vk_temp = vk - learning_rate * grad_v
            gamma_v = np.percentile(np.abs(vk_temp), (1 - sparsity_y) * 100)
            vk = _soft_threshold(vk_temp, gamma_v)
            vk_norm = np.linalg.norm(vk)
            if vk_norm > 0:
                vk = vk / vk_norm

            # Check convergence
            du = np.linalg.norm(uk - uk_old)
            dv = np.linalg.norm(vk - vk_old)
            if du < tol and dv < tol:
                break

        u[:, k] = uk
        v[:, k] = vk
        correlations[k] = float((Xs @ uk).T @ (Ys @ vk) / n)

    return u, v, correlations


def run_sparse_cca_analysis(microbiome_df: pd.DataFrame,
                            metabolome_df: pd.DataFrame,
                            metadata_df: Optional[pd.DataFrame] = None,
                            parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Sparse CCA analysis for microbiome × metabolome integration.

    Parameters
    ----------
    microbiome_df : samples × features (genus/taxa)
    metabolome_df : samples × features (metabolites)
    metadata_df : optional sample metadata
    parameters : dict with keys:
        - n_components (2)
        - sparsity_x (0.3)
        - sparsity_y (0.3)
        - max_iter (500)
    """
    params = parameters or {}
    n_components = params.get('n_components', 2)
    sparsity_x = params.get('sparsity_x', 0.3)
    sparsity_y = params.get('sparsity_y', 0.3)
    max_iter = params.get('max_iter', 500)

    # Ensure common samples
    common = microbiome_df.index.intersection(metabolome_df.index)
    if len(common) == 0:
        raise ValueError("No common samples between microbiome and metabolome data")

    X = microbiome_df.loc[common].values.astype(float)
    Y = metabolome_df.loc[common].values.astype(float)

    # Remove zero-variance features
    X = X[:, X.std(axis=0) > 0]
    Y = Y[:, Y.std(axis=0) > 0]

    u, v, correlations = sparse_cca(X, Y, n_components=n_components,
                                     sparsity_x=sparsity_x, sparsity_y=sparsity_y,
                                     max_iter=max_iter)

    # Build results
    x_features = microbiome_df.loc[common].columns[microbiome_df.loc[common].std(axis=0) > 0].tolist()
    y_features = metabolome_df.loc[common].columns[metabolome_df.loc[common].std(axis=0) > 0].tolist()

    u_df = pd.DataFrame(u, index=x_features, columns=[f'CC{i+1}' for i in range(n_components)])
    v_df = pd.DataFrame(v, index=y_features, columns=[f'CC{i+1}' for i in range(n_components)])

    # Extract significant loadings
    top_microbiome = {}
    top_metabolome = {}
    for k in range(n_components):
        cc_name = f'CC{k+1}'
        u_k = u_df[cc_name].abs().sort_values(ascending=False)
        v_k = v_df[cc_name].abs().sort_values(ascending=False)
        top_microbiome[cc_name] = u_k[u_k > 0].head(20).to_dict()
        top_metabolome[cc_name] = v_k[v_k > 0].head(20).to_dict()

    # Canonical variable scores
    Xs = StandardScaler().fit_transform(X)
    Ys = StandardScaler().fit_transform(Y)
    scores_x = Xs @ u
    scores_y = Ys @ v

    score_df = pd.DataFrame({
        **{f'X_CC{i+1}': scores_x[:, i] for i in range(n_components)},
        **{f'Y_CC{i+1}': scores_y[:, i] for i in range(n_components)},
    }, index=common)

    # Permutation test for significance
    n_perm = params.get('n_permutations', 999)
    perm_corr = np.zeros((n_perm, n_components))
    for i in range(n_perm):
        idx = np.random.permutation(X.shape[0])
        _, _, c = sparse_cca(X[idx], Y, n_components=n_components,
                              sparsity_x=sparsity_x, sparsity_y=sparsity_y,
                              max_iter=100, learning_rate=0.01)
        perm_corr[i] = c

    pvalues = [(perm_corr[:, k] >= correlations[k]).mean() for k in range(n_components)]

    return {
        'n_components': n_components,
        'n_samples': len(common),
        'n_microbiome_features': X.shape[1],
        'n_metabolome_features': Y.shape[1],
        'canonical_correlations': correlations.tolist(),
        'pvalues': pvalues,
        'sparsity_x': sparsity_x,
        'sparsity_y': sparsity_y,
        'u_loadings': u_df.to_dict(),
        'v_loadings': v_df.to_dict(),
        'top_microbiome_features': top_microbiome,
        'top_metabolome_features': top_metabolome,
        'canonical_scores': score_df.to_dict(),
        'plot_data': _sparse_cca_plot_data(score_df, metadata_df, common),
    }


def _sparse_cca_plot_data(score_df, metadata_df, common):
    """Build Plotly scatter data for canonical scores."""
    traces = []
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
                'x': score_df.loc[samps, 'X_CC1'].tolist(),
                'y': score_df.loc[samps, 'Y_CC1'].tolist(),
                'mode': 'markers',
                'name': str(grp),
                'text': samps.tolist(),
                'marker': {'size': 10, 'opacity': 0.8},
            })
    else:
        traces.append({
            'x': score_df['X_CC1'].tolist(),
            'y': score_df['Y_CC1'].tolist(),
            'mode': 'markers',
            'name': 'Samples',
            'text': score_df.index.tolist(),
            'marker': {'size': 10, 'opacity': 0.8},
        })

    return {
        'data': traces,
        'layout': {
            'title': 'Sparse CCA: Microbiome CC1 vs Metabolome CC1',
            'xaxis': {'title': 'Microbiome Canonical Score (CC1)'},
            'yaxis': {'title': 'Metabolome Canonical Score (CC1)'},
            'hovermode': 'closest',
        }
    }
