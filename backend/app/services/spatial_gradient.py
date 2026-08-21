"""
Meta2bAnalyst - Spatial Gradient Analysis Module
================================================
Analyzes spatial (anatomical) gradients of microbiome composition across body sites.

Methods:
- distance_decay: Bray-Curtis dissimilarity vs. anatomical distance with curve fitting
- mantel_correlogram: Mantel test across distance classes
- gradient_forest: Feature importance of body sites via RandomForest

References:
- Distance decay: Nekola & White 1999, J Biogeogr 26:867-878
- Mantel correlogram: Legendre & Legendre 2012, Numerical Ecology
"""
import logging
import warnings
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.optimize import curve_fit
from scipy.spatial.distance import braycurtis, pdist, squareform
from scipy.stats import pearsonr, spearmanr

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=RuntimeWarning)


# ─────────────────────────────── Pre-defined Anatomical Distance Matrix

_DEFAULT_ANATOMICAL_SITES = [
    "oral", "saliva", "buccal_mucosa", "tongue", "subgingival_plaque",
    "supragingival_plaque", "gut", "stool", "feces", "rectum",
    "skin", "volar_forearm", "antecubital_fossa", "vaginal",
    "vagina", "cervix", "urethra", "nasal", "nose", "nostril",
    "pharynx", "throat", "esophagus", "stomach", "duodenum",
    "ileum", "colon", "sigmoid", "cecum", "ileal",
]

# Approximate anatomical distances (cm) between body sites
# These are rough biological approximations for demonstration.
_ANATOMICAL_DISTANCE_CM: Dict[Tuple[str, str], float] = {
    ("oral", "saliva"): 0.0,
    ("oral", "buccal_mucosa"): 2.0,
    ("oral", "tongue"): 3.0,
    ("oral", "subgingival_plaque"): 1.0,
    ("oral", "supragingival_plaque"): 0.5,
    ("oral", "gut"): 100.0,
    ("oral", "stool"): 100.0,
    ("oral", "skin"): 30.0,
    ("oral", "vaginal"): 80.0,
    ("oral", "nasal"): 10.0,
    ("gut", "stool"): 0.0,
    ("gut", "rectum"): 15.0,
    ("gut", "skin"): 50.0,
    ("gut", "vaginal"): 20.0,
    ("gut", "oral"): 100.0,
    ("skin", "vaginal"): 40.0,
    ("skin", "oral"): 30.0,
    ("skin", "gut"): 50.0,
    ("vaginal", "oral"): 80.0,
    ("vaginal", "gut"): 20.0,
    ("vaginal", "skin"): 40.0,
    ("nasal", "oral"): 10.0,
    ("nasal", "skin"): 15.0,
    ("nasal", "gut"): 90.0,
}


def _normalize_site_name(site: str) -> str:
    """Normalize site name to lower-case with underscores."""
    return site.lower().strip().replace(" ", "_").replace("-", "_")


def _get_anatomical_distance(site1: str, site2: str) -> float:
    """Return approximate anatomical distance between two body sites (cm)."""
    s1 = _normalize_site_name(site1)
    s2 = _normalize_site_name(site2)
    if s1 == s2:
        return 0.0
    # Direct lookup
    key = (s1, s2)
    if key in _ANATOMICAL_DISTANCE_CM:
        return _ANATOMICAL_DISTANCE_CM[key]
    key_rev = (s2, s1)
    if key_rev in _ANATOMICAL_DISTANCE_CM:
        return _ANATOMICAL_DISTANCE_CM[key_rev]
    # Fallback: common site synonyms
    synonym_map = {
        "feces": "stool", "stool": "gut",
        "vagina": "vaginal", "cervix": "vaginal",
        "nostril": "nasal", "nose": "nasal",
        "saliva": "oral", "buccal_mucosa": "oral",
        "tongue": "oral", "subgingival_plaque": "oral",
        "supragingival_plaque": "oral",
        "volar_forearm": "skin", "antecubital_fossa": "skin",
        "throat": "oral", "pharynx": "oral",
        "esophagus": "gut", "stomach": "gut",
        "duodenum": "gut", "ileum": "gut",
        "colon": "gut", "sigmoid": "gut",
        "cecum": "gut", "ileal": "gut",
        "rectum": "gut",
    }
    s1_mapped = synonym_map.get(s1, s1)
    s2_mapped = synonym_map.get(s2, s2)
    if s1_mapped == s2_mapped:
        return 0.0
    key = (s1_mapped, s2_mapped)
    if key in _ANATOMICAL_DISTANCE_CM:
        return _ANATOMICAL_DISTANCE_CM[key]
    key_rev = (s2_mapped, s1_mapped)
    if key_rev in _ANATOMICAL_DISTANCE_CM:
        return _ANATOMICAL_DISTANCE_CM[key_rev]
    # Ultimate fallback: arbitrary large distance for completely different regions
    return 150.0


def _build_site_distance_matrix(sites: List[str]) -> np.ndarray:
    """Build a pairwise anatomical distance matrix for a list of site names."""
    n = len(sites)
    dist_mat = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_mat[i, j] = _get_anatomical_distance(sites[i], sites[j])
    return dist_mat


def _bray_curtis_pairwise(df: pd.DataFrame) -> np.ndarray:
    """Compute Bray-Curtis distance matrix for sample rows."""
    rel = df.div(df.sum(axis=1), axis=0).fillna(0)
    return squareform(pdist(rel.values, metric="braycurtis"))


def _sanitize_json(obj: Any) -> Any:
    """Recursively convert numpy/pandas types to native Python types."""
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


# ─────────────────────────────── Distance Decay

def _exp_decay(d, a, b):
    """Negative exponential decay: y = a * exp(-b * d)."""
    return a * np.exp(-b * d)


def _power_law(d, a, b):
    """Power-law decay: y = a * d^(-b)."""
    return a * np.power(d, -b)


def _fit_decay(distances: np.ndarray, dissimilarities: np.ndarray, model: str = "exp") -> Dict[str, Any]:
    """Fit a decay curve to distance-dissimilarity data."""
    # Filter out zero distances (same site pairs)
    mask = distances > 0
    x = distances[mask]
    y = dissimilarities[mask]

    if len(x) < 3:
        return {"fitted": False, "r2": None, "params": None, "model": model}

    # Initial guesses
    a0 = y.max() if y.max() > 0 else 1.0
    b0 = 0.01

    try:
        if model == "exp":
            popt, _ = curve_fit(_exp_decay, x, y, p0=[a0, b0], maxfev=5000)
            y_pred = _exp_decay(x, *popt)
        else:
            # Power law: avoid d=0
            popt, _ = curve_fit(_power_law, x, y, p0=[a0, b0], maxfev=5000)
            y_pred = _power_law(x, *popt)

        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        return {
            "fitted": True,
            "r2": float(r2),
            "params": {"a": float(popt[0]), "b": float(popt[1])},
            "model": model,
        }
    except Exception as e:
        logger.warning(f"Decay curve fitting failed: {e}")
        return {"fitted": False, "r2": None, "params": None, "model": model}


def _distance_decay_analysis(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: str,
    spatial_distance_matrix: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Core distance-decay computation."""
    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]
    sites = meta[site_column].unique()

    # Compute Bray-Curtis between all sample pairs
    bc_matrix = _bray_curtis_pairwise(df_aligned)
    n = len(common)

    # Spatial distance matrix
    if spatial_distance_matrix is not None:
        spatial_mat = np.array(spatial_distance_matrix)
        if spatial_mat.shape != (n, n):
            raise ValueError(f"spatial_distance_matrix shape {spatial_mat.shape} does not match sample count {n}")
    else:
        # Build from site labels
        site_labels = meta[site_column].values
        site_list = list(sites)
        site_idx_map = {s: i for i, s in enumerate(site_list)}
        site_dist = _build_site_distance_matrix(site_list)
        spatial_mat = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                si = site_idx_map.get(site_labels[i], 0)
                sj = site_idx_map.get(site_labels[j], 0)
                spatial_mat[i, j] = site_dist[si, sj]

    # Extract upper triangle (no diagonal)
    idx = np.triu_indices(n, k=1)
    spatial_dists = spatial_mat[idx]
    bc_dists = bc_matrix[idx]

    # Spearman correlation
    if len(spatial_dists) > 2:
        corr, pval = spearmanr(spatial_dists, bc_dists)
    else:
        corr, pval = np.nan, np.nan

    # Fit decay curves
    exp_fit = _fit_decay(spatial_dists, bc_dists, model="exp")
    power_fit = _fit_decay(spatial_dists, bc_dists, model="power")

    # Select best fit
    best_fit = exp_fit if (exp_fit["fitted"] and (not power_fit["fitted"] or exp_fit.get("r2", -1) >= power_fit.get("r2", -1))) else power_fit

    # Build decay plot data
    decay_data = pd.DataFrame({
        "spatial_distance": spatial_dists,
        "braycurtis_dissimilarity": bc_dists,
    })

    # Also compute mean per distance bin for plotting
    sorted_unique = np.sort(np.unique(spatial_dists))
    mean_by_dist = []
    for d in sorted_unique:
        mask = spatial_dists == d
        if mask.sum() > 0:
            mean_by_dist.append({
                "spatial_distance": float(d),
                "mean_bc": float(bc_dists[mask].mean()),
                "std_bc": float(bc_dists[mask].std()),
                "n_pairs": int(mask.sum()),
            })
    mean_df = pd.DataFrame(mean_by_dist)

    return {
        "decay_data": decay_data,
        "mean_by_distance": mean_df,
        "spearman_r": float(corr) if not np.isnan(corr) else None,
        "spearman_p": float(pval) if not np.isnan(pval) else None,
        "n_pairs": int(len(spatial_dists)),
        "n_sites": int(len(sites)),
        "best_fit": best_fit,
        "exp_fit": exp_fit,
        "power_fit": power_fit,
        "spatial_distance_matrix": spatial_mat.tolist(),
    }


def _plot_decay(decay_result: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Plotly distance-decay figure."""
    decay_data = decay_result["decay_data"]
    mean_df = decay_result["mean_by_distance"]
    best = decay_result["best_fit"]

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Distance Decay (Scatter)", "Mean Dissimilarity by Distance"))

    # Scatter plot
    fig.add_trace(
        go.Scatter(
            x=decay_data["spatial_distance"],
            y=decay_data["braycurtis_dissimilarity"],
            mode="markers",
            marker=dict(size=6, opacity=0.4, color="#1f77b4"),
            name="Sample pairs",
            hovertemplate="Distance: %{x:.1f}<br>BC: %{y:.3f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Fitted curve
    if best["fitted"]:
        x_fit = np.linspace(
            decay_data["spatial_distance"].min(),
            decay_data["spatial_distance"].max(),
            200,
        )
        a, b = best["params"]["a"], best["params"]["b"]
        if best["model"] == "exp":
            y_fit = a * np.exp(-b * x_fit)
            fit_label = f"Exp fit (R²={best['r2']:.3f})"
        else:
            y_fit = a * np.power(x_fit, -b)
            fit_label = f"Power fit (R²={best['r2']:.3f})"

        fig.add_trace(
            go.Scatter(
                x=x_fit,
                y=y_fit,
                mode="lines",
                line=dict(color="#d62728", width=2),
                name=fit_label,
            ),
            row=1, col=1,
        )

    # Mean by distance bar
    fig.add_trace(
        go.Bar(
            x=mean_df["spatial_distance"],
            y=mean_df["mean_bc"],
            error_y=dict(type="data", array=mean_df["std_bc"], visible=True),
            marker_color="#2ca02c",
            name="Mean ± SD",
            showlegend=False,
            hovertemplate="Dist: %{x:.1f}<br>Mean BC: %{y:.3f}<extra></extra>",
        ),
        row=1, col=2,
    )

    fig.update_layout(
        title_text=f"Distance Decay (r={decay_result['spearman_r'] or 'N/A'})",
        template="plotly_white",
        width=1000,
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
    )
    fig.update_xaxes(title_text="Anatomical Distance (cm)", row=1, col=1)
    fig.update_yaxes(title_text="Bray-Curtis Dissimilarity", row=1, col=1)
    fig.update_xaxes(title_text="Anatomical Distance (cm)", row=1, col=2)
    fig.update_yaxes(title_text="Mean Bray-Curtis", row=1, col=2)

    return fig.to_dict()


# ─────────────────────────────── Mantel Correlogram

def _mantel_correlogram_analysis(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: str,
    spatial_distance_matrix: Optional[np.ndarray] = None,
    n_classes: int = 5,
    n_permutations: int = 999,
) -> Dict[str, Any]:
    """Compute Mantel correlogram across distance classes."""
    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]
    sites = meta[site_column].unique()

    bc_matrix = _bray_curtis_pairwise(df_aligned)
    n = len(common)

    # Spatial distance matrix
    if spatial_distance_matrix is not None:
        spatial_mat = np.array(spatial_distance_matrix)
        if spatial_mat.shape != (n, n):
            raise ValueError(f"spatial_distance_matrix shape mismatch")
    else:
        site_labels = meta[site_column].values
        site_list = list(sites)
        site_dist = _build_site_distance_matrix(site_list)
        site_idx_map = {s: i for i, s in enumerate(site_list)}
        spatial_mat = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                si = site_idx_map.get(site_labels[i], 0)
                sj = site_idx_map.get(site_labels[j], 0)
                spatial_mat[i, j] = site_dist[si, sj]

    idx = np.triu_indices(n, k=1)
    spatial_dists = spatial_mat[idx]
    bc_dists = bc_matrix[idx]

    # Define distance classes (quantile-based)
    if len(np.unique(spatial_dists)) <= n_classes:
        # If too few unique distances, use each unique as a class
        class_edges = np.sort(np.unique(spatial_dists))
    else:
        class_edges = np.quantile(spatial_dists, q=np.linspace(0, 1, n_classes + 1))

    correlogram_rows = []
    rng = np.random.RandomState(seed=42)

    for i in range(len(class_edges) - 1):
        lower, upper = class_edges[i], class_edges[i + 1]
        if i == len(class_edges) - 2:
            class_mask = (spatial_dists >= lower) & (spatial_dists <= upper)
        else:
            class_mask = (spatial_dists >= lower) & (spatial_dists < upper)

        n_in_class = int(class_mask.sum())
        if n_in_class < 3:
            correlogram_rows.append({
                "class_index": i,
                "distance_lower": float(lower),
                "distance_upper": float(upper),
                "distance_mid": float((lower + upper) / 2),
                "n_pairs": n_in_class,
                "mantel_r": None,
                "mantel_p": None,
                "significant": False,
            })
            continue

        bc_class = bc_dists[class_mask]
        # Mantel-like: correlation between spatial distance (within class) and BC
        spatial_class = spatial_dists[class_mask]
        r_obs, _ = pearsonr(spatial_class, bc_class)

        # Permutation test
        perm_rs = []
        for _ in range(min(n_permutations, 999)):
            perm_bc = rng.permutation(bc_class)
            rp, _ = pearsonr(spatial_class, perm_bc)
            perm_rs.append(rp)
        perm_rs = np.array(perm_rs)
        p_val = (np.sum(np.abs(perm_rs) >= np.abs(r_obs)) + 1) / (len(perm_rs) + 1)

        correlogram_rows.append({
            "class_index": i,
            "distance_lower": float(lower),
            "distance_upper": float(upper),
            "distance_mid": float((lower + upper) / 2),
            "n_pairs": n_in_class,
            "mantel_r": float(r_obs),
            "mantel_p": float(p_val),
            "significant": float(p_val) < 0.05,
        })

    correlogram_df = pd.DataFrame(correlogram_rows)
    return {
        "correlogram": correlogram_df,
        "n_classes": int(len(correlogram_rows)),
        "n_permutations": n_permutations,
    }


def _plot_correlogram(correlogram_result: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Plotly Mantel correlogram figure."""
    df = correlogram_result["correlogram"]
    valid = df.dropna(subset=["mantel_r"])

    colors = ["#d62728" if sig else "#1f77b4" for sig in valid["significant"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=valid["distance_mid"],
        y=valid["mantel_r"],
        mode="lines+markers",
        marker=dict(size=12, color=colors, line=dict(width=1, color="black")),
        line=dict(color="#7f7f7f", width=1),
        name="Mantel r",
        hovertemplate="Mid-dist: %{x:.1f}<br>r: %{y:.3f}<br>Sig: %{customdata}<extra></extra>",
        customdata=["Yes" if s else "No" for s in valid["significant"]],
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

    fig.update_layout(
        title="Mantel Correlogram",
        xaxis_title="Distance Class Midpoint (cm)",
        yaxis_title="Mantel Correlation (r)",
        template="plotly_white",
        width=700,
        height=500,
        showlegend=False,
    )

    return fig.to_dict()


# ─────────────────────────────── Gradient Forest (Simplified)

def _gradient_forest_analysis(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: str,
) -> Dict[str, Any]:
    """Simplified gradient forest: use RF to predict taxa from site labels."""
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import LabelEncoder

    common = df.index.intersection(metadata_df.index)
    df_aligned = df.loc[common]
    meta = metadata_df.loc[common]

    # Features: taxa abundances; Target: site (encoded)
    X = df_aligned.values
    le = LabelEncoder()
    y = le.fit_transform(meta[site_column].astype(str))

    # Train RF regressor (site -> taxa is reversed in the prompt's description,
    # but we follow: "RandomForestRegressor 用 site 预测 taxa 丰度")
    # Actually the prompt says "用 site 预测 taxa 丰度", which means site predicts taxa.
    # This is unusual because site is categorical. We do one-vs-rest per taxon instead:
    # For each taxon, predict its abundance from site.
    feature_importance_list = []
    r2_scores = []

    # One-hot encode sites
    sites = meta[site_column].astype(str).values
    unique_sites = sorted(set(sites))
    site_onehot = np.zeros((len(common), len(unique_sites)))
    for i, s in enumerate(sites):
        if s in unique_sites:
            site_onehot[i, unique_sites.index(s)] = 1

    for taxon_idx, taxon in enumerate(df_aligned.columns):
        y_taxon = df_aligned.iloc[:, taxon_idx].values
        if y_taxon.std() == 0:
            continue
        try:
            rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
            rf.fit(site_onehot, y_taxon)
            r2 = rf.score(site_onehot, y_taxon)
            r2_scores.append(r2)
            # Average feature importance across site features
            avg_imp = float(rf.feature_importances_.mean())
            feature_importance_list.append({
                "taxon": str(taxon),
                "mean_importance": avg_imp,
                "r2": float(r2),
            })
        except Exception as e:
            logger.warning(f"RF failed for taxon {taxon}: {e}")
            continue

    imp_df = pd.DataFrame(feature_importance_list)
    if not imp_df.empty:
        imp_df = imp_df.sort_values("mean_importance", ascending=False)

    return {
        "gradient_importance": imp_df,
        "n_taxa": len(df_aligned.columns),
        "n_sites": len(unique_sites),
        "mean_r2": float(np.mean(r2_scores)) if r2_scores else None,
    }


def _plot_gradient_importance(gf_result: Dict[str, Any]) -> Dict[str, Any]:
    """Plotly bar chart of gradient forest feature importance."""
    imp_df = gf_result["gradient_importance"]
    if imp_df.empty:
        return go.Figure().update_layout(title="No gradient importance data").to_dict()

    top_n = min(30, len(imp_df))
    top = imp_df.head(top_n)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=top["taxon"],
        y=top["mean_importance"],
        marker_color="#9467bd",
        hovertemplate="%{x}<br>Importance: %{y:.4f}<extra></extra>",
    ))
    fig.update_layout(
        title="Gradient Forest: Top Taxa Importance",
        xaxis_title="Taxon",
        yaxis_title="Mean Feature Importance",
        template="plotly_white",
        xaxis_tickangle=-45,
        width=900,
        height=500,
    )
    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_spatial_gradient(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    site_column: str,
    spatial_distance_matrix: Optional[List[List[float]]] = None,
    method: str = "distance_decay",
) -> Dict[str, Any]:
    """Spatial gradient analysis across body sites.

    Args:
        df: Feature table (samples x taxa).
        metadata_df: Metadata DataFrame indexed by sample ID.
        site_column: Column in metadata defining body site / spatial location.
        spatial_distance_matrix: Optional pre-computed pairwise site distances.
        method: One of "distance_decay", "mantel_correlogram", "gradient_forest".

    Returns:
        Dict with:
            - decay_plot: Plotly JSON for distance decay.
            - correlogram_plot: Plotly JSON for Mantel correlogram.
            - gradient_importance: DataFrame of feature importances.
            - Additional statistics keys.
    """
    logger.info(f"Starting spatial_gradient analysis: method={method}, site_column={site_column}")

    common = df.index.intersection(metadata_df.index)
    if len(common) == 0:
        raise ValueError("No matching samples between data and metadata.")

    if site_column not in metadata_df.columns:
        raise ValueError(f"Site column '{site_column}' not found in metadata.")

    spatial_mat = np.array(spatial_distance_matrix) if spatial_distance_matrix is not None else None

    result: Dict[str, Any] = {
        "method": method,
        "site_column": site_column,
        "n_samples": int(len(common)),
    }

    if method == "distance_decay":
        dd = _distance_decay_analysis(df, metadata_df, site_column, spatial_mat)
        result["decay_plot"] = _plot_decay(dd)
        result["decay_statistics"] = {
            "spearman_r": dd["spearman_r"],
            "spearman_p": dd["spearman_p"],
            "n_pairs": dd["n_pairs"],
            "n_sites": dd["n_sites"],
            "best_fit": dd["best_fit"],
        }
        result["decay_data"] = _sanitize_json(dd["decay_data"])
        result["mean_by_distance"] = _sanitize_json(dd["mean_by_distance"])

    elif method == "mantel_correlogram":
        mc = _mantel_correlogram_analysis(df, metadata_df, site_column, spatial_mat)
        result["correlogram_plot"] = _plot_correlogram(mc)
        result["correlogram"] = _sanitize_json(mc["correlogram"])
        result["n_classes"] = mc["n_classes"]

    elif method == "gradient_forest":
        gf = _gradient_forest_analysis(df, metadata_df, site_column)
        result["gradient_importance"] = _sanitize_json(gf["gradient_importance"])
        result["gradient_plot"] = _plot_gradient_importance(gf)
        result["n_taxa"] = gf["n_taxa"]
        result["n_sites"] = gf["n_sites"]
        result["mean_r2"] = gf["mean_r2"]

    else:
        raise ValueError(f"Unknown method: {method}. Choose from distance_decay, mantel_correlogram, gradient_forest.")

    # Always provide the full suite of keys for frontend convenience
    if "decay_plot" not in result:
        result["decay_plot"] = None
    if "correlogram_plot" not in result:
        result["correlogram_plot"] = None
    if "gradient_importance" not in result:
        result["gradient_importance"] = None

    logger.info("Spatial gradient analysis complete")
    return result
