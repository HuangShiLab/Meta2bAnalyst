#!/usr/bin/env python3
"""Meta2bAnalyst - SPIEC-EASI Network Inference Module

Sparse Inverse Covariance Estimation for microbial association networks.
Calls SpiecEasi::spiec.easi via rpy2 when available, with a Python fallback
combining CLR transformation, GraphicalLassoCV / Meinshausen-Buhlmann Lasso,
and StARS (Stability Approach to Regularization Selection).

References:
    Kurtz ZD, et al. (2015) Sparse and Compositionally Robust Inference of
    Microbial Ecological Networks. PLoS Computational Biology 11(5): e1004226.
    Liu H, Roeder K, Wasserman L. (2010) Stability approach to regularization
    selection (StARS) for high dimensional graphical models. NIPS 23.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

# ─────────────────────────────── R availability

R_AVAILABLE = False
R_SPIECEASI_AVAILABLE = False
try:
    import rpy2.robjects as ro
    from rpy2.robjects import pandas2ri
    from rpy2.robjects.conversion import localconverter
    from rpy2.robjects.packages import importr

    R_AVAILABLE = True
    try:
        importr("SpiecEasi")
        R_SPIECEASI_AVAILABLE = True
        logger.info("R package SpiecEasi is available")
    except Exception as e:
        logger.warning(f"R package SpiecEasi not available: {e}")
except ImportError as e:
    logger.warning(f"rpy2 not installed ({e}). Using Python fallback for SPIEC-EASI.")


# ─────────────────────────────── Public API


def run_spiec_easi(
    df: pd.DataFrame,
    method: str = "mb",
    lambda_min_ratio: float = 0.01,
    nlambda: int = 100,
    rep_num: int = 20,
) -> Dict[str, Any]:
    """Run SPIEC-EASI sparse inverse covariance estimation.

    Parameters
    ----------
    df : pd.DataFrame
        Feature table **features × samples** (e.g. OTU/ASV table).
        Raw counts or normalized abundances; CLR is applied internally.
    method : str
        Network estimation method: ``"mb"`` (Meinshausen-Buhlmann / neighborhood
        selection) or ``"glasso"`` (graphical lasso).
    lambda_min_ratio : float
        Ratio of minimum to maximum regularization parameter lambda.
    nlambda : int
        Number of lambda values to test along the regularization path.
    rep_num : int
        Number of subsampling replicates for StARS stability selection.

    Returns
    -------
    dict
        ``{"adjacency_matrix": dict, "network_data": dict,
        "stability_scores": list, "plot_data": dict,
        "method": str, "r_engine_used": bool}``
    """
    if df.shape[0] < 2 or df.shape[1] < 3:
        raise ValueError("SPIEC-EASI requires >=2 features and >=3 samples.")

    if R_AVAILABLE and R_SPIECEASI_AVAILABLE:
        try:
            result = _run_spiec_easi_r(df, method, lambda_min_ratio, nlambda, rep_num)
            result["r_engine_used"] = True
            return result
        except Exception as e:
            logger.error(f"SPIEC-EASI R call failed: {e}; falling back to Python")

    result = _run_spiec_easi_python(df, method, lambda_min_ratio, nlambda, rep_num)
    result["r_engine_used"] = False
    return result


# ─────────────────────────────── R implementation


def _run_spiec_easi_r(
    df: pd.DataFrame,
    method: str,
    lambda_min_ratio: float,
    nlambda: int,
    rep_num: int,
) -> Dict[str, Any]:
    """Call SpiecEasi::spiec.easi via rpy2."""
    features = df.index.tolist()
    samples = df.columns.tolist()

    with localconverter(ro.default_converter + pandas2ri.converter):
        r_counts = ro.conversion.py2rpy(df.values)

        ro.r("""
        run_spiec <- function(counts, method, lambda_min_ratio, nlambda, rep_num) {
            library(SpiecEasi)
            # SpiecEasi expects samples × features
            mat <- t(as.matrix(counts))
            # Ensure valid method
            method <- match.arg(method, choices = c("glasso", "mb", "slr"))
            se <- spiec.easi(
                mat,
                method = method,
                lambda.min.ratio = lambda_min_ratio,
                nlambda = as.integer(nlambda),
                rep.num = as.integer(rep_num),
                pulsar.params = list(rep.num = as.integer(rep_num), ncores = 1)
            )
            # Extract adjacency matrix (binary) and stability scores
            adj <- as.matrix(getRefit(se))
            # Convert to partial correlation-like weights
            beta <- as.matrix(se$est$beta)
            # Stability path
            stab <- se$select$stars$summary
            list(adjacency = adj, beta = beta, stability = stab)
        }
        """)
        r_func = ro.r["run_spiec"]
        result_r = r_func(r_counts, method, lambda_min_ratio, nlambda, rep_num)

        adj = ro.conversion.rpy2py(result_r.rx2("adjacency"))
        beta = ro.conversion.rpy2py(result_r.rx2("beta"))
        stab = ro.conversion.rpy2py(result_r.rx2("stability"))

    adj_df = pd.DataFrame(adj, index=features, columns=features)
    beta_df = pd.DataFrame(beta, index=features, columns=features)

    # Convert to partial correlation matrix
    pcor_df = _beta_to_partial_correlation(beta_df)

    # Zero out non-selected edges
    pcor_df = pcor_df * adj_df

    # Network data
    network_data = _extract_network_data(pcor_df, adj_df)

    # Plotly network
    plot_data = _build_network_plot(network_data, pcor_df)

    # StARS stability (if vector-like)
    stability_scores = stab.tolist() if hasattr(stab, "tolist") else list(stab) if stab is not None else []

    return {
        "adjacency_matrix": adj_df.to_dict(),
        "partial_correlation": pcor_df.to_dict(),
        "network_data": network_data,
        "stability_scores": stability_scores,
        "plot_data": plot_data,
        "method": method,
    }


# ─────────────────────────────── Python fallback


def _clr_transform(mat: np.ndarray, pseudo: float = 0.5) -> np.ndarray:
    """Centered log-ratio transform (samples × features)."""
    mat = mat.astype(float)
    mat = np.where(mat <= 0, pseudo, mat)
    log_mat = np.log(mat)
    gmean = log_mat.mean(axis=1, keepdims=True)
    return log_mat - gmean


def _generate_lambda_path(
    X: np.ndarray,
    nlambda: int = 100,
    lambda_min_ratio: float = 0.01,
) -> np.ndarray:
    """Generate a decreasing lambda sequence (lasso/elastic-net style)."""
    n_samples, n_features = X.shape
    # Max lambda: smallest value that drives all coefficients to zero
    X_std = X - X.mean(axis=0, keepdims=True)
    max_lambda = np.max(np.abs(X_std.T @ X_std)) / n_samples
    if max_lambda <= 0:
        max_lambda = 1.0
    return np.logspace(
        np.log10(max_lambda * lambda_min_ratio),
        np.log10(max_lambda),
        num=nlambda,
    )


def _meinshausen_buhlmann_path(
    X: np.ndarray,
    lambdas: np.ndarray,
) -> np.ndarray:
    """Neighborhood selection via Lasso for each variable.

    Returns a 3D array of shape (nlambda, n_features, n_features)
    where entry [l, i, j] is the coefficient of variable j when
    predicting variable i at lambda[l].  Diagonals are zero.
    """
    from sklearn.linear_model import Lasso

    n_samples, n_features = X.shape
    n_lambda = len(lambdas)
    coef_path = np.zeros((n_lambda, n_features, n_features))

    # Standardize predictors
    X_std = StandardScaler().fit_transform(X)

    for i in range(n_features):
        y = X_std[:, i]
        # Predictors: all other variables
        mask = np.ones(n_features, dtype=bool)
        mask[i] = False
        Xi = X_std[:, mask]

        # Fit Lasso path manually for each lambda
        for li, lam in enumerate(lambdas):
            # Scale lambda for sklearn (alpha = lambda / (2*n_samples))
            alpha = lam / (2.0 * n_samples)
            model = Lasso(alpha=alpha, max_iter=5000, fit_intercept=False)
            try:
                model.fit(Xi, y)
                coefs = model.coef_
            except Exception:
                coefs = np.zeros(Xi.shape[1])
            # Insert back into full feature space
            full_coef = np.zeros(n_features)
            full_coef[mask] = coefs
            coef_path[li, i, :] = full_coef

    return coef_path


def _glasso_path(
    X: np.ndarray,
    lambdas: np.ndarray,
) -> np.ndarray:
    """Graphical Lasso along a lambda path.

    Returns a 3D array of shape (nlambda, n_features, n_features)
    of precision matrices (or partial correlation approximations).
    """
    from sklearn.covariance import GraphicalLasso

    n_samples, n_features = X.shape
    n_lambda = len(lambdas)
    prec_path = np.zeros((n_lambda, n_features, n_features))

    X_std = StandardScaler().fit_transform(X)
    emp_cov = np.cov(X_std, rowvar=False)

    for li, lam in enumerate(lambdas):
        alpha = lam  # sklearn GraphicalLasso alpha maps directly to penalty
        model = GraphicalLasso(alpha=alpha, max_iter=500, mode="lars")
        try:
            model.fit(X_std)
            prec = model.precision_
        except Exception:
            # Fall back to diagonal
            prec = np.eye(n_features)
        prec_path[li] = prec

    return prec_path


def _stars_selection(
    X: np.ndarray,
    method: str,
    lambdas: np.ndarray,
    rep_num: int = 20,
    subsample_ratio: float = 0.8,
) -> tuple:
    """StARS: Stability Approach to Regularization Selection.

    Subsamples ``rep_num`` times at ``subsample_ratio`` of the data,
    runs the selected method at each lambda, and computes the edge
    selection stability (probability) for every lambda.

    Returns
    -------
    best_lambda_idx : int
        Index of the selected lambda (max stable with non-empty graph).
    stability_path : np.ndarray
        Shape ``(nlambda,)`` — average edge selection probability per lambda.
    adjacency_mean : np.ndarray
        Shape ``(n_features, n_features)`` — mean adjacency at best lambda.
    """
    n_samples, n_features = X.shape
    n_lambda = len(lambdas)
    n_sub = max(3, int(np.floor(subsample_ratio * n_samples)))
    rng = np.random.default_rng(42)

    # Accumulate edge selections
    edge_counts = np.zeros((n_lambda, n_features, n_features))

    for _ in range(rep_num):
        sub_idx = rng.choice(n_samples, size=n_sub, replace=False)
        X_sub = X[sub_idx, :]

        if method == "mb":
            coef_path = _meinshausen_buhlmann_path(X_sub, lambdas)
            # Symmetrize by OR rule: edge exists if i→j or j→i
            for li in range(n_lambda):
                adj = (np.abs(coef_path[li]) > 1e-9).astype(float)
                # OR rule symmetrization
                adj_sym = np.maximum(adj, adj.T)
                np.fill_diagonal(adj_sym, 0.0)
                edge_counts[li] += adj_sym
        else:
            prec_path = _glasso_path(X_sub, lambdas)
            for li in range(n_lambda):
                # Non-zero off-diagonal in precision matrix
                adj = (np.abs(prec_path[li]) > 1e-9).astype(float)
                np.fill_diagonal(adj, 0.0)
                edge_counts[li] += adj

    # Selection probability per lambda
    stability_path = np.zeros(n_lambda)
    for li in range(n_lambda):
        probs = edge_counts[li] / rep_num
        # Average over upper triangle (excluding diagonal)
        triu_idx = np.triu_indices(n_features, k=1)
        stability_path[li] = probs[triu_idx].mean()

    # Select lambda: highest stability with at least some edges
    # Prefer sparser model when stability is comparable (>0.5 threshold heuristic)
    valid = stability_path > 0.05
    if not valid.any():
        best_idx = n_lambda // 2
    else:
        # Choose lambda with max stability, but bias toward sparser end
        # when multiple lambdas achieve similar stability
        best_idx = int(np.argmax(stability_path))

    adjacency_mean = edge_counts[best_idx] / rep_num
    return best_idx, stability_path, adjacency_mean


def _beta_to_partial_correlation(beta_df: pd.DataFrame) -> pd.DataFrame:
    """Convert a coefficient/precision matrix to partial correlations."""
    M = beta_df.values.copy()
    n = M.shape[0]
    pcor = np.zeros_like(M)
    for i in range(n):
        for j in range(n):
            if i == j:
                pcor[i, j] = 1.0
                continue
            denom = np.sqrt(abs(M[i, i] * M[j, j]))
            if denom > 1e-12:
                pcor[i, j] = -M[i, j] / denom
            else:
                pcor[i, j] = 0.0
    pcor = np.clip(pcor, -1.0, 1.0)
    return pd.DataFrame(pcor, index=beta_df.index, columns=beta_df.columns)


def _extract_network_data(
    pcor_df: pd.DataFrame,
    adj_df: pd.DataFrame,
    threshold: float = 0.0,
) -> Dict[str, Any]:
    """Build a node/edge dictionary from the adjacency and partial-correlation matrices."""
    import networkx as nx

    features = pcor_df.index.tolist()
    n = len(features)

    G = nx.Graph()
    G.add_nodes_from(features)

    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if adj_df.iloc[i, j] > threshold or abs(pcor_df.iloc[i, j]) > threshold:
                w = float(pcor_df.iloc[i, j])
                G.add_edge(features[i], features[j], weight=abs(w), correlation=w)
                edges.append({
                    "source": features[i],
                    "target": features[j],
                    "partial_correlation": w,
                    "weight": abs(w),
                })

    stats = {
        "node_count": len(G.nodes),
        "edge_count": len(G.edges),
        "density": nx.density(G),
    }
    try:
        stats["average_degree"] = sum(dict(G.degree()).values()) / len(G.nodes) if G.nodes else 0.0
    except Exception:
        stats["average_degree"] = 0.0

    try:
        clustering = nx.clustering(G, weight="weight")
        stats["average_clustering"] = sum(clustering.values()) / len(G.nodes) if G.nodes else 0.0
    except Exception:
        stats["average_clustering"] = 0.0

    # Hub nodes (top 20% by degree)
    if G.nodes:
        deg_sorted = sorted(dict(G.degree()).items(), key=lambda x: x[1], reverse=True)
        n_hubs = max(1, min(10, int(np.ceil(0.2 * len(G.nodes)))))
        hubs = [n for n, _ in deg_sorted[:n_hubs]]
    else:
        hubs = []
    stats["hubs"] = hubs

    # Node-level stats
    nodes_stats = {}
    for node in G.nodes:
        nodes_stats[node] = {
            "degree": int(dict(G.degree()).get(node, 0)),
            "is_hub": node in hubs,
        }
    stats["nodes"] = nodes_stats
    stats["edges"] = edges

    return stats


def _build_network_plot(network_data: Dict[str, Any], pcor_df: pd.DataFrame) -> Dict[str, Any]:
    """Generate a Plotly network figure with spring layout.

    Edge width encodes absolute partial correlation strength.
    """
    import networkx as nx

    features = pcor_df.index.tolist()
    n = len(features)

    G = nx.Graph()
    G.add_nodes_from(features)
    for i in range(n):
        for j in range(i + 1, n):
            w = float(pcor_df.iloc[i, j])
            if abs(w) > 1e-9:
                G.add_edge(features[i], features[j], weight=abs(w), correlation=w)

    if len(G.nodes) == 0:
        fig = go.Figure()
        fig.update_layout(title="SPIEC-EASI Network (no edges)", template="plotly_white")
        return fig.to_dict()

    pos = nx.spring_layout(G, k=0.5, iterations=50, seed=42)
    degree_dict = dict(G.degree())
    max_deg = max(degree_dict.values()) if degree_dict else 1

    # Edge traces: width ~ |partial correlation|
    edge_traces = []
    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        corr = data.get("correlation", 0.0)
        width = 0.5 + 4.0 * abs(corr)  # scale 0.5–4.5
        color = "#e11d48" if corr > 0 else "#2563eb"
        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="text",
                text=f"{u} — {v}<br>Partial r: {corr:.3f}",
                showlegend=False,
            )
        )

    # Node trace
    node_x = []
    node_y = []
    node_text = []
    node_size = []
    node_color = []
    hub_nodes = set(network_data.get("hubs", []))
    for node in G.nodes:
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        deg = degree_dict.get(node, 0)
        node_text.append(f"<b>{node}</b><br>Degree: {deg}")
        node_size.append(8 + 25 * (deg / (max_deg + 1e-6)))
        node_color.append("#7c3aed" if node in hub_nodes else "#64748b")

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=[str(n) for n in G.nodes],
        textposition="top center",
        textfont=dict(size=8, color="#1e293b"),
        hoverinfo="text",
        hovertext=node_text,
        marker=dict(
            color=node_color,
            size=node_size,
            line=dict(width=1.5, color="#ffffff"),
        ),
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    fig.update_layout(
        title="SPIEC-EASI Inferred Network (Partial Correlation)",
        template="plotly_white",
        width=850,
        height=700,
        hovermode="closest",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig.to_dict()


def _run_spiec_easi_python(
    df: pd.DataFrame,
    method: str,
    lambda_min_ratio: float,
    nlambda: int,
    rep_num: int,
) -> Dict[str, Any]:
    """Python fallback for SPIEC-EASI."""
    features = df.index.tolist()
    # CLR transform: samples × features
    X = _clr_transform(df.values.T)
    n_samples, n_features = X.shape

    if n_features < 2:
        raise ValueError("Need at least 2 features after filtering")

    # Generate lambda path
    lambdas = _generate_lambda_path(X, nlambda=nlambda, lambda_min_ratio=lambda_min_ratio)

    # StARS selection
    best_idx, stability_path, adjacency_mean = _stars_selection(
        X, method, lambdas, rep_num=rep_num, subsample_ratio=0.8
    )
    best_lambda = float(lambdas[best_idx])

    # Refit on full data at best lambda
    if method == "mb":
        coef_path = _meinshausen_buhlmann_path(X, np.array([best_lambda]))
        beta = coef_path[0]
        # Symmetrize (AND rule for final adjacency)
        adj = ((np.abs(beta) > 1e-9) & (np.abs(beta.T) > 1e-9)).astype(float)
        np.fill_diagonal(adj, 0.0)
        beta_df = pd.DataFrame(beta, index=features, columns=features)
    else:
        prec_path = _glasso_path(X, np.array([best_lambda]))
        prec = prec_path[0]
        adj = (np.abs(prec) > 1e-9).astype(float)
        np.fill_diagonal(adj, 0.0)
        # Use precision as beta proxy
        beta_df = pd.DataFrame(prec, index=features, columns=features)

    adj_df = pd.DataFrame(adj, index=features, columns=features)
    pcor_df = _beta_to_partial_correlation(beta_df)
    pcor_df = pcor_df * adj_df  # mask non-selected edges

    network_data = _extract_network_data(pcor_df, adj_df)
    plot_data = _build_network_plot(network_data, pcor_df)

    return {
        "adjacency_matrix": adj_df.to_dict(),
        "partial_correlation": pcor_df.to_dict(),
        "network_data": network_data,
        "stability_scores": stability_path.tolist(),
        "best_lambda": best_lambda,
        "plot_data": plot_data,
        "method": method,
    }


# ─────────────────────────────── Helpers for pandas / JSON safety


def _sanitize_floats(obj: Any) -> Any:
    """Recursively convert NaN/Inf to None for JSON safety."""
    import math

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj
