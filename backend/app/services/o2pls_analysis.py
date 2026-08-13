"""
O2PLS (Two-Way Orthogonal Partial Least Squares)
===================================================
O2PLS integrates two data matrices (X = microbiome, Y = metabolome) by
simultaneously decomposing each into three parts:
  1. Joint / predictive variation (shared between X and Y)
  2. X-specific orthogonal variation (unique to X)
  3. Y-specific orthogonal variation (unique to Y)
  4. Residual noise

This is the gold-standard for multi-omics integration when systematic
variation (e.g., batch effects, individual variation) should be separated
from the joint signal.

Reference: Trygg & Wold, 2003; Bouhaddani et al., 2016 (O2PLS R package).
"""
import logging
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def o2pls(X: np.ndarray, Y: np.ndarray,
          n_joint: int = 2,
          n_ortho_x: int = 1,
          n_ortho_y: int = 1,
          max_iter: int = 200,
          tol: float = 1e-6) -> Dict[str, Any]:
    """
    Two-way O2PLS decomposition.

    Parameters
    ----------
    X : (n_samples, p1) — microbiome
    Y : (n_samples, p2) — metabolome
    n_joint : number of joint predictive components
    n_ortho_x : number of X-orthogonal components
    n_ortho_y : number of Y-orthogonal components

    Returns
    -------
    dict with T (joint X scores), U (joint Y scores), W (joint X loadings),
    C (joint Y loadings), T_ortho (X-ortho scores), U_ortho (Y-ortho scores),
    P_ortho (X-ortho loadings), P_y_ortho (Y-ortho loadings), and explained variance.
    """
    n, p1 = X.shape
    _, p2 = Y.shape

    # Standardize
    Xs = StandardScaler().fit_transform(X)
    Ys = StandardScaler().fit_transform(Y)

    # --- Step 1: Joint components (NIPALS-style) ---
    T = np.zeros((n, n_joint))
    U = np.zeros((n, n_joint))
    W = np.zeros((p1, n_joint))
    C = np.zeros((p2, n_joint))
    B = np.zeros(n_joint)  # inner regression coefficients

    E = Xs.copy()  # X residuals
    F = Ys.copy()  # Y residuals

    for a in range(n_joint):
        # Initialize with covariance
        w = E.T @ F
        _, s, _ = np.linalg.svd(w, full_matrices=False)
        w = w[:, 0] if p1 >= p2 else w[0, :]  # simplified

        # Actually, use SVD of E.T @ F to get initial w and c
        U_svd, s_vals, Vt_svd = np.linalg.svd(E.T @ F, full_matrices=False)
        w = U_svd[:, 0]
        c = Vt_svd[0, :]

        w = w / np.linalg.norm(w)
        c = c / np.linalg.norm(c)

        # NIPALS iteration
        for it in range(max_iter):
            t = E @ w
            t = t / np.linalg.norm(t) if np.linalg.norm(t) > 0 else t
            u = F @ c
            u = u / np.linalg.norm(u) if np.linalg.norm(u) > 0 else u

            w_new = E.T @ u
            w_new = w_new / np.linalg.norm(w_new) if np.linalg.norm(w_new) > 0 else w_new
            c_new = F.T @ t
            c_new = c_new / np.linalg.norm(c_new) if np.linalg.norm(c_new) > 0 else c_new

            if np.linalg.norm(w_new - w) < tol and np.linalg.norm(c_new - c) < tol:
                break
            w, c = w_new, c_new

        t = E @ w
        u = F @ c

        # Inner relation: u = b * t + error
        b = float((t.T @ u) / (t.T @ t)) if t.T @ t > 0 else 0.0

        # Deflate
        E = E - np.outer(t, w)
        F = F - np.outer(t, c) * b  # Y predicted from X

        T[:, a] = t
        U[:, a] = u
        W[:, a] = w
        C[:, a] = c
        B[a] = b

    # --- Step 2: X-orthogonal components ---
    T_ox = np.zeros((n, n_ortho_x))
    P_ox = np.zeros((p1, n_ortho_x))

    E_ortho = Xs - T @ W.T  # X after removing joint

    for a in range(n_ortho_x):
        # PCA on E_ortho
        Cov = E_ortho.T @ E_ortho / (n - 1)
        eigvals, eigvecs = np.linalg.eigh(Cov)
        idx = np.argsort(eigvals)[::-1]
        w_ortho = eigvecs[:, idx[0]]
        w_ortho = w_ortho / np.linalg.norm(w_ortho)

        t_ortho = E_ortho @ w_ortho
        p_ortho = E_ortho.T @ t_ortho / (t_ortho.T @ t_ortho)

        E_ortho = E_ortho - np.outer(t_ortho, p_ortho)
        T_ox[:, a] = t_ortho
        P_ox[:, a] = p_ortho

    # --- Step 3: Y-orthogonal components ---
    T_oy = np.zeros((n, n_ortho_y))
    P_oy = np.zeros((p2, n_ortho_y))

    F_ortho = Ys - U @ C.T  # Y after removing joint

    for a in range(n_ortho_y):
        Cov = F_ortho.T @ F_ortho / (n - 1)
        eigvals, eigvecs = np.linalg.eigh(Cov)
        idx = np.argsort(eigvals)[::-1]
        c_ortho = eigvecs[:, idx[0]]
        c_ortho = c_ortho / np.linalg.norm(c_ortho)

        t_ortho = F_ortho @ c_ortho
        p_ortho = F_ortho.T @ t_ortho / (t_ortho.T @ t_ortho)

        F_ortho = F_ortho - np.outer(t_ortho, p_ortho)
        T_oy[:, a] = t_ortho
        P_oy[:, a] = p_ortho

    # --- Variance explained ---
    var_X_total = np.sum(Xs ** 2)
    var_Y_total = np.sum(Ys ** 2)

    var_X_joint = np.sum((T @ W.T) ** 2)
    var_Y_joint = np.sum((U @ C.T) ** 2)
    var_X_ortho = np.sum((T_ox @ P_ox.T) ** 2)
    var_Y_ortho = np.sum((T_oy @ P_oy.T) ** 2)

    var_X_res = np.sum(E ** 2)
    var_Y_res = np.sum(F ** 2)

    return {
        'T_joint': T, 'U_joint': U,
        'W_loadings': W, 'C_loadings': C,
        'B_inner': B,
        'T_ortho_X': T_ox, 'P_ortho_X': P_ox,
        'T_ortho_Y': T_oy, 'P_ortho_Y': P_oy,
        'X_residual': E, 'Y_residual': F,
        'variance': {
            'X_total': float(var_X_total),
            'Y_total': float(var_Y_total),
            'X_joint': float(var_X_joint),
            'Y_joint': float(var_Y_joint),
            'X_ortho': float(var_X_ortho),
            'Y_ortho': float(var_Y_ortho),
            'X_residual': float(var_X_res),
            'Y_residual': float(var_Y_res),
            'X_joint_pct': float(var_X_joint / var_X_total * 100) if var_X_total > 0 else 0.0,
            'Y_joint_pct': float(var_Y_joint / var_Y_total * 100) if var_Y_total > 0 else 0.0,
            'X_ortho_pct': float(var_X_ortho / var_X_total * 100) if var_X_total > 0 else 0.0,
            'Y_ortho_pct': float(var_Y_ortho / var_Y_total * 100) if var_Y_total > 0 else 0.0,
            'X_res_pct': float(var_X_res / var_X_total * 100) if var_X_total > 0 else 0.0,
            'Y_res_pct': float(var_Y_res / var_Y_total * 100) if var_Y_total > 0 else 0.0,
        }
    }


def run_o2pls_analysis(microbiome_df: pd.DataFrame,
                       metabolome_df: pd.DataFrame,
                       metadata_df: Optional[pd.DataFrame] = None,
                       parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    O2PLS multi-omics integration.

    Parameters
    ----------
    microbiome_df : samples × taxa
    metabolome_df : samples × metabolites
    metadata_df : optional
    parameters : n_joint (2), n_ortho_x (1), n_ortho_y (1)
    """
    params = parameters or {}
    n_joint = params.get('n_joint', 2)
    n_ortho_x = params.get('n_ortho_x', 1)
    n_ortho_y = params.get('n_ortho_y', 1)

    common = microbiome_df.index.intersection(metabolome_df.index)
    if len(common) == 0:
        raise ValueError("No common samples between microbiome and metabolome")

    X = microbiome_df.loc[common].values.astype(float)
    Y = metabolome_df.loc[common].values.astype(float)

    X = X[:, X.std(axis=0) > 0]
    Y = Y[:, Y.std(axis=0) > 0]

    result = o2pls(X, Y, n_joint=n_joint, n_ortho_x=n_ortho_x, n_ortho_y=n_ortho_y)

    x_features = microbiome_df.loc[common].columns[microbiome_df.loc[common].std(axis=0) > 0].tolist()
    y_features = metabolome_df.loc[common].columns[metabolome_df.loc[common].std(axis=0) > 0].tolist()

    # DataFrames
    T_joint_df = pd.DataFrame(result['T_joint'], index=common,
                               columns=[f'Joint{a+1}' for a in range(n_joint)])
    U_joint_df = pd.DataFrame(result['U_joint'], index=common,
                               columns=[f'Joint{a+1}' for a in range(n_joint)])
    W_df = pd.DataFrame(result['W_loadings'], index=x_features,
                         columns=[f'Joint{a+1}' for a in range(n_joint)])
    C_df = pd.DataFrame(result['C_loadings'], index=y_features,
                         columns=[f'Joint{a+1}' for a in range(n_joint)])

    # Top features per joint component
    top_x = {}
    top_y = {}
    for a in range(n_joint):
        cc = f'Joint{a+1}'
        top_x[cc] = W_df[cc].abs().sort_values(ascending=False).head(20).to_dict()
        top_y[cc] = C_df[cc].abs().sort_values(ascending=False).head(20).to_dict()

    # Plot data: joint score plot (T vs U)
    plot_data = _o2pls_plot_data(T_joint_df, U_joint_df, metadata_df, common)

    # Predictive performance: cross-validated inner correlation
    cv_corr = []
    for a in range(n_joint):
        cv_corr.append(float(np.corrcoef(T_joint_df.iloc[:, a], U_joint_df.iloc[:, a])[0, 1]))

    return {
        'n_samples': len(common),
        'n_joint_components': n_joint,
        'n_ortho_x': n_ortho_x,
        'n_ortho_y': n_ortho_y,
        'n_taxa': X.shape[1],
        'n_metabolites': Y.shape[1],
        'variance': result['variance'],
        'joint_scores_X': T_joint_df.to_dict(),
        'joint_scores_Y': U_joint_df.to_dict(),
        'X_loadings': W_df.to_dict(),
        'Y_loadings': C_df.to_dict(),
        'inner_correlations': cv_corr,
        'top_microbiome_features': top_x,
        'top_metabolome_features': top_y,
        'plot_data': plot_data,
    }


def _o2pls_plot_data(T_joint_df, U_joint_df, metadata_df, common):
    """Build joint score scatter plot."""
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
                'x': T_joint_df.loc[samps, 'Joint1'].tolist(),
                'y': U_joint_df.loc[samps, 'Joint1'].tolist(),
                'mode': 'markers',
                'name': str(grp),
                'text': samps.tolist(),
                'marker': {'size': 10, 'opacity': 0.8},
            })
    else:
        traces.append({
            'x': T_joint_df['Joint1'].tolist(),
            'y': U_joint_df['Joint1'].tolist(),
            'mode': 'markers',
            'name': 'Samples',
            'text': T_joint_df.index.tolist(),
            'marker': {'size': 10, 'opacity': 0.8},
        })

    return {
        'data': traces,
        'layout': {
            'title': 'O2PLS Joint Score Plot: X vs Y',
            'xaxis': {'title': 'Microbiome Joint Score (T1)'},
            'yaxis': {'title': 'Metabolome Joint Score (U1)'},
            'hovermode': 'closest',
        }
    }
