"""
Meta2bAnalyst - Correlation Analysis Module
Implements feature-to-feature and feature-to-metadata correlation analysis
with multiple testing correction (BH-FDR) and interactive Plotly visualization.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import pdist, squareform
from scipy.stats import pearsonr, spearmanr

logger = logging.getLogger(__name__)


# ─────────────────────────────── Core Computation


def _bh_fdr(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction.

    Args:
        pvalues: Array of p-values.

    Returns:
        Array of q-values (adjusted p-values).

    Note:
        The monotonicity (step-down) pass must run over p-values sorted
        ascending; applying it to unsorted values, as an earlier version did,
        produced q-values that depended on input row order.
    """
    from app.services.analysis_engine import adjust_pvalues
    return adjust_pvalues(pvalues, 'fdr_bh')


def compute_feature_correlation(
    df: pd.DataFrame,
    method: str = 'spearman',
    threshold: float = 0.3,
    fdr_threshold: float = 0.05,
) -> pd.DataFrame:
    """Compute pairwise feature-to-feature correlation matrix and return significant pairs.

    Args:
        df: Feature table (features x samples).
        method: 'spearman' (default, rank-based) or 'pearson' (parametric).
        threshold: Minimum absolute correlation for significance (default 0.3).
        fdr_threshold: Maximum q-value threshold (default 0.05).

    Returns:
        DataFrame with columns [feature_1, feature_2, correlation, pvalue, qvalue]
        filtered to significant pairs (|correlation| > threshold and q < fdr_threshold).
    """
    features = df.index.tolist()
    n_features = len(features)

    if n_features < 2:
        return pd.DataFrame(columns=['feature_1', 'feature_2', 'correlation', 'pvalue', 'qvalue'])

    # Filter zero-variance features
    var_mask = df.var(axis=1) > 0
    if not var_mask.all():
        df = df.loc[var_mask]
        features = df.index.tolist()
        n_features = len(features)
        logger.info(f"Removed {(~var_mask).sum()} zero-variance features from correlation analysis")

    if n_features < 2:
        return pd.DataFrame(columns=['feature_1', 'feature_2', 'correlation', 'pvalue', 'qvalue'])

    corr_func = spearmanr if method == 'spearman' else pearsonr
    data = df.values.astype(float)  # (features, samples)

    results = []
    pvalues = []

    for i in range(n_features):
        for j in range(i + 1, n_features):
            x, y = data[i], data[j]
            # Handle constant arrays
            if np.std(x) == 0 or np.std(y) == 0:
                results.append({
                    'feature_1': features[i],
                    'feature_2': features[j],
                    'correlation': 0.0,
                })
                pvalues.append(1.0)
                continue
            try:
                if method == 'spearman':
                    r, p = corr_func(x, y)
                else:
                    r, p = corr_func(x, y)
                results.append({
                    'feature_1': features[i],
                    'feature_2': features[j],
                    'correlation': float(r),
                })
                pvalues.append(float(p))
            except Exception as e:
                logger.warning(f"Correlation failed for {features[i]} vs {features[j]}: {e}")
                results.append({
                    'feature_1': features[i],
                    'feature_2': features[j],
                    'correlation': 0.0,
                })
                pvalues.append(1.0)

    qvalues = _bh_fdr(np.array(pvalues))

    result_df = pd.DataFrame(results)
    result_df['pvalue'] = pvalues
    result_df['qvalue'] = qvalues

    # Filter by threshold and FDR
    sig_mask = (result_df['correlation'].abs() > threshold) & (result_df['qvalue'] < fdr_threshold)
    result_df = result_df[sig_mask].sort_values('qvalue').reset_index(drop=True)

    # Format for display
    if len(result_df) > 0:
        result_df['correlation'] = result_df['correlation'].round(4)
        result_df['pvalue_display'] = result_df['pvalue'].apply(lambda x: f'{x:.2e}' if x < 0.001 else f'{x:.4f}')
        result_df['qvalue_display'] = result_df['qvalue'].apply(lambda x: f'{x:.2e}' if x < 0.001 else f'{x:.4f}')

    return result_df


def compute_feature_metadata_correlation(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    method: str = 'spearman',
    threshold: float = 0.3,
    fdr_threshold: float = 0.05,
) -> pd.DataFrame:
    """Compute feature-to-metadata correlations for numeric metadata columns.

    Args:
        df: Feature table (features x samples).
        metadata_df: Metadata DataFrame (samples x metadata variables).
        method: 'spearman' (default) or 'pearson'.
        threshold: Minimum absolute correlation for significance (default 0.3).
        fdr_threshold: Maximum q-value threshold (default 0.05).

    Returns:
        DataFrame with columns [feature, metadata_var, correlation, pvalue, qvalue]
        filtered to significant associations.
    """
    # Identify numeric metadata columns
    numeric_cols = metadata_df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        logger.warning("No numeric metadata columns found for correlation analysis")
        return pd.DataFrame(columns=['feature', 'metadata_var', 'correlation', 'pvalue', 'qvalue'])

    # Intersect samples
    common_samples = df.columns.intersection(metadata_df.index)
    if len(common_samples) == 0:
        logger.warning("No common samples between feature table and metadata")
        return pd.DataFrame(columns=['feature', 'metadata_var', 'correlation', 'pvalue', 'qvalue'])

    df_sub = df[common_samples]
    meta_sub = metadata_df.loc[common_samples, numeric_cols]

    corr_func = spearmanr if method == 'spearman' else pearsonr

    results = []
    pvalues = []

    for feature in df_sub.index:
        x = df_sub.loc[feature].values.astype(float)
        for meta_var in numeric_cols:
            y = meta_sub[meta_var].values.astype(float)
            # Drop NaNs pairwise
            mask = ~(np.isnan(x) | np.isnan(y))
            x_clean, y_clean = x[mask], y[mask]

            if len(x_clean) < 3 or np.std(x_clean) == 0 or np.std(y_clean) == 0:
                results.append({
                    'feature': feature,
                    'metadata_var': meta_var,
                    'correlation': 0.0,
                })
                pvalues.append(1.0)
                continue

            try:
                r, p = corr_func(x_clean, y_clean)
                results.append({
                    'feature': feature,
                    'metadata_var': meta_var,
                    'correlation': float(r),
                })
                pvalues.append(float(p))
            except Exception as e:
                logger.warning(f"Correlation failed for {feature} vs {meta_var}: {e}")
                results.append({
                    'feature': feature,
                    'metadata_var': meta_var,
                    'correlation': 0.0,
                })
                pvalues.append(1.0)

    qvalues = _bh_fdr(np.array(pvalues))

    result_df = pd.DataFrame(results)
    result_df['pvalue'] = pvalues
    result_df['qvalue'] = qvalues

    # Filter
    sig_mask = (result_df['correlation'].abs() > threshold) & (result_df['qvalue'] < fdr_threshold)
    result_df = result_df[sig_mask].sort_values('qvalue').reset_index(drop=True)

    if len(result_df) > 0:
        result_df['correlation'] = result_df['correlation'].round(4)
        result_df['pvalue_display'] = result_df['pvalue'].apply(lambda x: f'{x:.2e}' if x < 0.001 else f'{x:.4f}')
        result_df['qvalue_display'] = result_df['qvalue'].apply(lambda x: f'{x:.2e}' if x < 0.001 else f'{x:.4f}')

    return result_df


# ─────────────────────────────── Hierarchical Clustering


def hierarchical_clustering_order(corr_matrix: pd.DataFrame) -> List[str]:
    """Return feature order from hierarchical clustering on correlation distance.

    Args:
        corr_matrix: Square correlation matrix DataFrame.

    Returns:
        List of feature names in clustered order.
    """
    if len(corr_matrix) <= 1:
        return corr_matrix.index.tolist()

    # Convert correlation to distance
    dist = 1 - corr_matrix.abs().values
    np.fill_diagonal(dist, 0)
    # Ensure valid distance matrix
    dist = np.clip(dist, 0, 1)

    # Condense and cluster
    try:
        cond_dist = squareform(dist, checks=False)
        Z = linkage(cond_dist, method='average')
        order = leaves_list(Z)
        return [corr_matrix.index[i] for i in order]
    except Exception as e:
        logger.warning(f"Hierarchical clustering failed: {e}, returning original order")
        return corr_matrix.index.tolist()


# ─────────────────────────────── Plotly Visualization


def plotly_correlation_heatmap(
    cor_df: pd.DataFrame,
    width: int = 800,
    height: int = 700,
) -> dict:
    """Generate a Plotly heatmap from a significant correlation pair DataFrame.

    Args:
        cor_df: DataFrame with columns [feature_1, feature_2, correlation, ...].
        width: Plot width in pixels.
        height: Plot height in pixels.

    Returns:
        Plotly figure JSON dict.
    """
    if cor_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title='Correlation Heatmap (No significant correlations)',
            width=width,
            height=height,
        )
        return fig.to_dict()

    # Determine unique features involved
    features = sorted(set(cor_df['feature_1']) | set(cor_df['feature_2']))
    n = len(features)
    feat_idx = {f: i for i, f in enumerate(features)}

    # Build symmetric matrix
    mat = np.zeros((n, n))
    for _, row in cor_df.iterrows():
        i, j = feat_idx[row['feature_1']], feat_idx[row['feature_2']]
        mat[i, j] = row['correlation']
        mat[j, i] = row['correlation']

    corr_matrix = pd.DataFrame(mat, index=features, columns=features)

    # Cluster features for better visualization
    ordered_features = hierarchical_clustering_order(corr_matrix)
    corr_matrix = corr_matrix.loc[ordered_features, ordered_features]

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=[str(f) for f in corr_matrix.columns],
        y=[str(f) for f in corr_matrix.index],
        colorscale='RdBu_r',
        zmid=0,
        zmin=-1,
        zmax=1,
        colorbar=dict(title='Correlation'),
        hoverongaps=False,
        hovertemplate=(
            '<b>%{y}</b> vs <b>%{x}</b><br>'
            'Correlation: %{z:.3f}<extra></extra>'
        ),
    ))

    fig.update_layout(
        title='Feature Correlation Heatmap (Significant Pairs)',
        width=width,
        height=height,
        xaxis=dict(tickangle=-45, automargin=True),
        yaxis=dict(automargin=True),
        margin=dict(l=100, r=50, t=80, b=100),
    )
    return fig.to_dict()


def plotly_feature_metadata_scatter(
    feature_values: pd.Series,
    metadata_values: pd.Series,
    feature_name: str,
    metadata_name: str,
    width: int = 600,
    height: int = 500,
) -> dict:
    """Generate a scatter plot with a linear trend line for feature vs metadata.

    Args:
        feature_values: Series of feature abundances (samples).
        metadata_values: Series of metadata values (samples).
        feature_name: Name of the feature.
        metadata_name: Name of the metadata variable.
        width: Plot width in pixels.
        height: Plot height in pixels.

    Returns:
        Plotly figure JSON dict.
    """
    # Align and drop NaNs
    df_plot = pd.DataFrame({
        'feature': feature_values,
        'metadata': metadata_values,
    }).dropna()

    if len(df_plot) < 3:
        fig = go.Figure()
        fig.update_layout(
            title=f'{feature_name} vs {metadata_name} (insufficient data)',
            width=width,
            height=height,
        )
        return fig.to_dict()

    x = df_plot['metadata'].values
    y = df_plot['feature'].values

    # Fit linear trend
    coeffs = np.polyfit(x, y, 1)
    trend_y = np.polyval(coeffs, x)

    # Pearson r for display
    try:
        r, p = pearsonr(x, y)
        title_text = f'{feature_name} vs {metadata_name}<br><sub>r={r:.3f}, p={p:.3g}</sub>'
    except Exception:
        title_text = f'{feature_name} vs {metadata_name}'

    fig = go.Figure()

    # Scatter points
    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode='markers',
        marker=dict(size=10, color='#2563eb', opacity=0.7, line=dict(width=1, color='#1e3a8a')),
        name='Samples',
        text=[str(s) for s in df_plot.index],
        hovertemplate='<b>%{text}</b><br>%{metadata_name}: %{x:.3f}<br>%{feature_name}: %{y:.3f}<extra></extra>',
    ))

    # Trend line
    fig.add_trace(go.Scatter(
        x=x,
        y=trend_y,
        mode='lines',
        line=dict(color='#dc2626', width=2, dash='dash'),
        name='Trend',
        hoverinfo='skip',
    ))

    fig.update_layout(
        title=title_text,
        xaxis_title=metadata_name,
        yaxis_title=feature_name,
        width=width,
        height=height,
        showlegend=False,
        margin=dict(l=60, r=40, t=80, b=60),
    )
    return fig.to_dict()


# ─────────────────────────────── High-level Runner


def run_correlation_analysis(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run complete correlation analysis pipeline.

    Args:
        df: Feature table (features x samples).
        metadata_df: Optional metadata DataFrame (samples x metadata).
        parameters: Dict with keys:
            - method: 'spearman' or 'pearson' (default 'spearman')
            - target: 'feature', 'metadata', or 'both' (default 'both')
            - threshold: absolute correlation threshold (default 0.3)
            - fdr_threshold: q-value threshold (default 0.05)

    Returns:
        Dictionary with correlation results and Plotly figures.
    """
    params = parameters or {}
    method = params.get('method', 'spearman')
    target = params.get('target', 'both')
    threshold = params.get('threshold', 0.3)
    fdr_threshold = params.get('fdr_threshold', 0.05)

    result = {
        'method': method,
        'threshold': threshold,
        'fdr_threshold': fdr_threshold,
        'target': target,
    }

    # Feature-to-feature correlation
    if target in ('feature', 'both'):
        ff_df = compute_feature_correlation(df, method=method, threshold=threshold, fdr_threshold=fdr_threshold)
        result['feature_correlation'] = {
            'significant_pairs': ff_df.to_dict(orient='records') if not ff_df.empty else [],
            'n_significant': len(ff_df),
        }
        if not ff_df.empty:
            result['feature_correlation']['plot_data'] = plotly_correlation_heatmap(ff_df)
        else:
            result['feature_correlation']['plot_data'] = plotly_correlation_heatmap(ff_df)

    # Feature-to-metadata correlation
    if target in ('metadata', 'both'):
        if metadata_df is not None:
            fm_df = compute_feature_metadata_correlation(
                df, metadata_df, method=method, threshold=threshold, fdr_threshold=fdr_threshold
            )
            result['metadata_correlation'] = {
                'significant_associations': fm_df.to_dict(orient='records') if not fm_df.empty else [],
                'n_significant': len(fm_df),
            }
            # Generate top scatter plots (up to 5)
            scatter_plots = []
            if not fm_df.empty:
                top_associations = fm_df.head(5)
                for _, row in top_associations.iterrows():
                    feature_name = row['feature']
                    meta_name = row['metadata_var']
                    if feature_name in df.index and meta_name in metadata_df.columns:
                        scatter = plotly_feature_metadata_scatter(
                            df.loc[feature_name],
                            metadata_df[meta_name],
                            feature_name,
                            meta_name,
                        )
                        scatter_plots.append({
                            'feature': feature_name,
                            'metadata_var': meta_name,
                            'correlation': row['correlation'],
                            'plot_data': scatter,
                        })
            result['metadata_correlation']['scatter_plots'] = scatter_plots
        else:
            result['metadata_correlation'] = {
                'significant_associations': [],
                'n_significant': 0,
                'scatter_plots': [],
                'warning': 'No metadata provided for feature-to-metadata correlation',
            }

    return result
