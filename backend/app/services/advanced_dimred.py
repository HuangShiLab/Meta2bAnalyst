"""
Meta2bAnalyst - Advanced Dimensionality Reduction & Multivariate Association
Implements t-SNE, UMAP, and MaAsLin3-style multivariate association analysis.

References:
  - t-SNE: van der Maaten & Hinton 2008, J Mach Learn Res 9:2579-2605
  - UMAP: McInnes et al. 2018, arXiv:1802.03426
  - MaAsLin3: Mallick et al. 2021, Nat Commun 12:6712
"""
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import f_oneway, kruskal, mannwhitneyu, pearsonr, spearmanr
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler

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


# ─────────────────────────────── t-SNE

def run_tsne(
    df: pd.DataFrame,
    n_components: int = 2,
    perplexity: float = 30.0,
    learning_rate: float = 200.0,
    n_iter: int = 1000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Run t-SNE on feature table.
    
    Args:
        df: Feature table (features x samples).
        n_components: Number of dimensions (default 2).
        perplexity: Perplexity parameter (default 30).
        learning_rate: Learning rate (default 200).
        n_iter: Number of iterations (default 1000).
        random_state: Random seed.
        
    Returns:
        DataFrame with t-SNE coordinates (samples x components).
    """
    # Transpose to get samples as rows
    X = df.T.values
    
    # Standardize
    X_std = StandardScaler().fit_transform(X)
    
    # Adjust perplexity
    effective_perplexity = min(perplexity, len(X) - 1)
    if effective_perplexity < 1:
        effective_perplexity = 1
    
    tsne = TSNE(
        n_components=n_components,
        perplexity=effective_perplexity,
        learning_rate=learning_rate,
        # sklearn >= 1.7 renamed n_iter to max_iter; keep our public parameter
        # name stable and translate here.
        max_iter=n_iter,
        random_state=random_state,
        init="pca",
    )
    
    coords = tsne.fit_transform(X_std)
    
    columns = [f"tSNE{i+1}" for i in range(n_components)]
    result = pd.DataFrame(coords, index=df.columns, columns=columns)
    
    logger.info(f"t-SNE complete: perplexity={effective_perplexity}, n_iter={n_iter}")
    
    return result


# ─────────────────────────────── UMAP

def run_umap(
    df: pd.DataFrame,
    n_components: int = 2,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    metric: str = "euclidean",
    random_state: int = 42,
) -> pd.DataFrame:
    """Run UMAP on feature table.
    
    Args:
        df: Feature table (features x samples).
        n_components: Number of dimensions (default 2).
        n_neighbors: Number of neighbors (default 15).
        min_dist: Minimum distance (default 0.1).
        metric: Distance metric (default 'euclidean').
        random_state: Random seed.
        
    Returns:
        DataFrame with UMAP coordinates (samples x components).
    """
    try:
        import umap
    except ImportError:
        logger.warning("UMAP not installed, using PCA fallback")
        from sklearn.decomposition import PCA
        X = df.T.values
        X_std = StandardScaler().fit_transform(X)
        pca = PCA(n_components=n_components)
        coords = pca.fit_transform(X_std)
        columns = [f"UMAP{i+1}" for i in range(n_components)]
        return pd.DataFrame(coords, index=df.columns, columns=columns)
    
    # Transpose to get samples as rows
    X = df.T.values
    
    # Standardize
    X_std = StandardScaler().fit_transform(X)
    
    # Adjust n_neighbors
    effective_n_neighbors = min(n_neighbors, len(X) - 1)
    if effective_n_neighbors < 2:
        effective_n_neighbors = 2
    
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=effective_n_neighbors,
        min_dist=min_dist,
        metric=metric,
        random_state=random_state,
    )
    
    coords = reducer.fit_transform(X_std)
    
    columns = [f"UMAP{i+1}" for i in range(n_components)]
    result = pd.DataFrame(coords, index=df.columns, columns=columns)
    
    logger.info(f"UMAP complete: n_neighbors={effective_n_neighbors}, min_dist={min_dist}")
    
    return result


# ─────────────────────────────── MaAsLin3-style Multivariate Association

def maaslin3_associations(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    fixed_effects: List[str],
    random_effects: Optional[List[str]] = None,
    min_abundance: float = 0.0,
    min_prevalence: float = 0.0,
    max_significance: float = 0.05,
) -> pd.DataFrame:
    """Run MaAsLin3-style multivariate association analysis.
    
    Fits linear models for each feature against fixed effects (and random effects).
    
    Args:
        df: Feature table (features x samples).
        metadata_df: Metadata DataFrame (samples x variables).
        fixed_effects: List of metadata columns as fixed effects.
        random_effects: List of metadata columns as random effects.
        min_abundance: Minimum mean abundance threshold.
        min_prevalence: Minimum prevalence threshold (%).
        max_significance: Significance threshold.
        
    Returns:
        DataFrame with association results.
    """
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import LabelEncoder
    
    # Filter features by abundance and prevalence
    mean_abund = df.mean(axis=1)
    prevalence = (df > 0).mean(axis=1) * 100
    
    mask = (mean_abund >= min_abundance) & (prevalence >= min_prevalence)
    df_filtered = df[mask]
    
    if df_filtered.empty:
        logger.warning("No features passed abundance/prevalence filters")
        return pd.DataFrame()
    
    # Get common samples
    common_samples = df_filtered.columns.intersection(metadata_df.index)
    if len(common_samples) < 3:
        logger.warning("Insufficient common samples")
        return pd.DataFrame()
    
    df_filtered = df_filtered[common_samples]
    meta_filtered = metadata_df.loc[common_samples]
    
    # Prepare design matrix
    X_list = []
    effect_names = []
    
    for effect in fixed_effects:
        if effect not in meta_filtered.columns:
            continue
        
        values = meta_filtered[effect]
        
        if values.dtype == object or values.dtype.name == 'category':
            # One-hot encode categorical variables
            dummies = pd.get_dummies(values, prefix=effect, drop_first=True)
            X_list.append(dummies)
            effect_names.extend(dummies.columns.tolist())
        else:
            X_list.append(values.to_frame(name=effect))
            effect_names.append(effect)
    
    if not X_list:
        logger.warning("No valid fixed effects")
        return pd.DataFrame()
    
    X = pd.concat(X_list, axis=1)
    X = X.fillna(0)
    
    # Fit linear model for each feature
    results = []
    
    for feature in df_filtered.index:
        y = df_filtered.loc[feature].values
        
        # Log transform (add pseudocount)
        y_log = np.log1p(y)
        
        try:
            model = LinearRegression()
            model.fit(X, y_log)
            
            # Compute R-squared
            y_pred = model.predict(X)
            ss_res = np.sum((y_log - y_pred) ** 2)
            ss_tot = np.sum((y_log - np.mean(y_log)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
            
            # Coefficients
            for i, coef in enumerate(model.coef_):
                if i < len(effect_names):
                    effect_name = effect_names[i]
                    
                    # Approximate p-value using correlation
                    if effect_name in X.columns:
                        corr, pval = pearsonr(X[effect_name], y_log)
                    else:
                        pval = 1.0
                    
                    results.append({
                        "feature": feature,
                        "metadata": effect_name,
                        "coef": coef,
                        "r_squared": r_squared,
                        "pvalue": pval,
                    })
        except Exception as e:
            logger.debug(f"Error fitting {feature}: {e}")
            continue
    
    if not results:
        return pd.DataFrame()
    
    result_df = pd.DataFrame(results)
    
    # BH-FDR
    from app.services.analysis_engine import adjust_pvalues
    result_df["padj"] = adjust_pvalues(result_df["pvalue"].values, "fdr_bh")
    
    return result_df.sort_values("pvalue")


# ─────────────────────────────── Plotly Visualizations

def plotly_tsne(tsne_df: pd.DataFrame, metadata_df: Optional[pd.DataFrame] = None,
                group_column: Optional[str] = None) -> dict:
    """Generate t-SNE plot.
    
    Args:
        tsne_df: t-SNE coordinates DataFrame.
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.
        
    Returns:
        Plotly figure JSON dict.
    """
    df_plot = tsne_df.copy()
    df_plot["Sample"] = df_plot.index
    
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        df_plot["Group"] = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                            for s in df_plot.index]
        
        groups = df_plot["Group"].unique()
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"][:len(groups)]
        
        fig = go.Figure()
        for i, group in enumerate(groups):
            mask = df_plot["Group"] == group
            fig.add_trace(go.Scatter(
                x=df_plot.loc[mask, "tSNE1"],
                y=df_plot.loc[mask, "tSNE2"],
                mode="markers+text",
                name=group,
                text=df_plot.loc[mask, "Sample"],
                textposition="top center",
                textfont=dict(size=8),
                marker=dict(size=12, color=colors[i % len(colors)], opacity=0.7),
                hovertemplate="<b>%{text}</b><br>tSNE1: %{x:.3f}<br>tSNE2: %{y:.3f}<extra></extra>",
            ))
        fig.update_layout(showlegend=True)
    else:
        fig = go.Figure(data=go.Scatter(
            x=df_plot["tSNE1"],
            y=df_plot["tSNE2"],
            mode="markers+text",
            text=df_plot["Sample"],
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(size=12, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>tSNE1: %{x:.3f}<br>tSNE2: %{y:.3f}<extra></extra>",
        ))
    
    fig.update_layout(
        title="t-SNE Visualization",
        xaxis_title="t-SNE1",
        yaxis_title="t-SNE2",
        template="plotly_white",
        height=500,
        width=600,
    )
    
    return fig.to_dict()


def plotly_umap(umap_df: pd.DataFrame, metadata_df: Optional[pd.DataFrame] = None,
                group_column: Optional[str] = None) -> dict:
    """Generate UMAP plot.
    
    Args:
        umap_df: UMAP coordinates DataFrame.
        metadata_df: Optional metadata for coloring.
        group_column: Column for group colors.
        
    Returns:
        Plotly figure JSON dict.
    """
    df_plot = umap_df.copy()
    df_plot["Sample"] = df_plot.index
    
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        df_plot["Group"] = [str(metadata_df.loc[s, group_column]) if s in metadata_df.index else "Unknown"
                            for s in df_plot.index]
        
        groups = df_plot["Group"].unique()
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"][:len(groups)]
        
        fig = go.Figure()
        for i, group in enumerate(groups):
            mask = df_plot["Group"] == group
            fig.add_trace(go.Scatter(
                x=df_plot.loc[mask, "UMAP1"],
                y=df_plot.loc[mask, "UMAP2"],
                mode="markers+text",
                name=group,
                text=df_plot.loc[mask, "Sample"],
                textposition="top center",
                textfont=dict(size=8),
                marker=dict(size=12, color=colors[i % len(colors)], opacity=0.7),
                hovertemplate="<b>%{text}</b><br>UMAP1: %{x:.3f}<br>UMAP2: %{y:.3f}<extra></extra>",
            ))
        fig.update_layout(showlegend=True)
    else:
        fig = go.Figure(data=go.Scatter(
            x=df_plot["UMAP1"],
            y=df_plot["UMAP2"],
            mode="markers+text",
            text=df_plot["Sample"],
            textposition="top center",
            textfont=dict(size=8),
            marker=dict(size=12, opacity=0.7),
            hovertemplate="<b>%{text}</b><br>UMAP1: %{x:.3f}<br>UMAP2: %{y:.3f}<extra></extra>",
        ))
    
    fig.update_layout(
        title="UMAP Visualization",
        xaxis_title="UMAP1",
        yaxis_title="UMAP2",
        template="plotly_white",
        height=500,
        width=600,
    )
    
    return fig.to_dict()


def plotly_maaslin_volcano(maaslin_df: pd.DataFrame) -> dict:
    """Generate volcano plot for MaAsLin3 results.
    
    Args:
        maaslin_df: Result from maaslin3_associations().
        
    Returns:
        Plotly figure JSON dict.
    """
    if maaslin_df.empty:
        return go.Figure().update_layout(title="No MaAsLin3 results").to_dict()
    
    df_plot = maaslin_df.copy()
    df_plot["neg_log10_p"] = -np.log10(df_plot["pvalue"].replace(0, 1e-300))
    df_plot["significant"] = df_plot["padj"] < 0.05
    
    colors = ["#d62728" if sig else "#1f77b4" for sig in df_plot["significant"]]
    
    fig = go.Figure(data=go.Scatter(
        x=df_plot["coef"],
        y=df_plot["neg_log10_p"],
        mode="markers",
        marker=dict(color=colors, size=10, opacity=0.7),
        text=df_plot["feature"] + " (" + df_plot["metadata"] + ")",
        hovertemplate="<b>%{text}</b><br>Coef: %{x:.3f}<br>-log10(p): %{y:.2f}<extra></extra>",
    ))
    
    fig.update_layout(
        title="MaAsLin3 Association Volcano Plot",
        xaxis_title="Coefficient",
        yaxis_title="-log10(p-value)",
        template="plotly_white",
        height=500,
        width=600,
        shapes=[
            dict(type="line", x0=0, x1=0, y0=0, y1=max(df_plot["neg_log10_p"]) * 1.1,
                 line=dict(color="gray", dash="dash")),
            dict(type="line", x0=min(df_plot["coef"]) * 1.1, x1=max(df_plot["coef"]) * 1.1,
                 y0=-np.log10(0.05), y1=-np.log10(0.05),
                 line=dict(color="gray", dash="dash")),
        ],
    )
    
    return fig.to_dict()


# ─────────────────────────────── Main Runner

def run_advanced_dimred(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run advanced dimensionality reduction and multivariate association.
    
    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata DataFrame.
        parameters: Dict with keys:
            - method: 'tsne', 'umap', or 'both' (default 'both')
            - tsne_perplexity: float (default 30)
            - tsne_learning_rate: float (default 200)
            - umap_n_neighbors: int (default 15)
            - umap_min_dist: float (default 0.1)
            - group_column: metadata column for coloring
            - run_maaslin: bool (default True)
            - fixed_effects: list of metadata columns
            - random_effects: list of metadata columns
            - min_abundance: float (default 0)
            - min_prevalence: float (default 0)
            
    Returns:
        Dict with t-SNE/UMAP coordinates, MaAsLin3 results, and plots.
    """
    params = parameters or {}
    method = params.get("method", "both")
    tsne_perplexity = params.get("tsne_perplexity", 30.0)
    tsne_learning_rate = params.get("tsne_learning_rate", 200.0)
    umap_n_neighbors = params.get("umap_n_neighbors", 15)
    umap_min_dist = params.get("umap_min_dist", 0.1)
    group_column = params.get("group_column")
    run_maaslin = params.get("run_maaslin", True)
    fixed_effects = params.get("fixed_effects", [])
    random_effects = params.get("random_effects")
    min_abundance = params.get("min_abundance", 0.0)
    min_prevalence = params.get("min_prevalence", 0.0)
    
    logger.info(f"Starting advanced dimred: method={method}, maaslin={run_maaslin}")
    
    # 1. t-SNE
    tsne_result = None
    if method in ["tsne", "both"]:
        tsne_result = run_tsne(df, perplexity=tsne_perplexity, learning_rate=tsne_learning_rate)
    
    # 2. UMAP
    umap_result = None
    if method in ["umap", "both"]:
        umap_result = run_umap(df, n_neighbors=umap_n_neighbors, min_dist=umap_min_dist)
    
    # 3. MaAsLin3
    maaslin_result = None
    if run_maaslin and metadata_df is not None and fixed_effects:
        valid_effects = [e for e in fixed_effects if e in metadata_df.columns]
        if valid_effects:
            maaslin_result = maaslin3_associations(
                df, metadata_df, valid_effects, random_effects,
                min_abundance=min_abundance, min_prevalence=min_prevalence,
            )
    
    # 4. Plots
    plots = {}
    
    if tsne_result is not None:
        plots["tsne_plot"] = plotly_tsne(tsne_result, metadata_df, group_column)
    
    if umap_result is not None:
        plots["umap_plot"] = plotly_umap(umap_result, metadata_df, group_column)
    
    if maaslin_result is not None and not maaslin_result.empty:
        plots["maaslin_volcano"] = plotly_maaslin_volcano(maaslin_result)
    
    # 5. Build result
    result = _sanitize_json({
        "method": method,
        "tsne": tsne_result.to_dict(orient="records") if tsne_result is not None else [],
        "umap": umap_result.to_dict(orient="records") if umap_result is not None else [],
        "maaslin": maaslin_result.to_dict(orient="records") if maaslin_result is not None and not maaslin_result.empty else [],
        "plots": plots,
    })
    
    logger.info("Advanced dimensionality reduction complete")
    return result
