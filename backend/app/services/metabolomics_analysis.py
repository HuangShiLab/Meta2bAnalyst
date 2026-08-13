"""
Metabolomics Statistical Analysis Module
=======================================
Provides PCA, alpha diversity, and marker discovery (differential metabolite analysis)
for metabolomics data using Day 0 as the reference comparison group.

Metrics:
  - PCA: principal component analysis on standardized metabolite intensities
  - Alpha diversity: metabolite richness, Shannon, Simpson, Pielou evenness
  - Marker discovery: fold-change, t-test/Wilcoxon, volcano plots vs Day 0 (T4)
"""
import logging
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import pdist, squareform
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ─────────────────────────────── Helpers


def _center_log_ratio(df: pd.DataFrame, eps: float = 1e-6) -> pd.DataFrame:
    """Apply centered log-ratio transformation (for compositional metabolomics)."""
    df_pos = df.replace(0, eps)
    log_df = np.log(df_pos)
    return log_df.subtract(log_df.mean(axis=1), axis=0)


def _richness(x):
    """Metabolite richness: count of metabolites with non-zero intensity."""
    return np.sum(x > 0)


def _shannon(x):
    """Shannon diversity on proportional intensities."""
    p = x[x > 0] / x[x > 0].sum()
    return -np.sum(p * np.log(p))


def _simpson(x):
    """Simpson diversity (1 - D)."""
    p = x[x > 0] / x[x > 0].sum()
    return 1 - np.sum(p ** 2)


def _pielou(x):
    """Pielou evenness = Shannon / ln(richness)."""
    rich = np.sum(x > 0)
    if rich <= 1:
        return 0.0
    shan = _shannon(x)
    return shan / np.log(rich)


def _inverse_simpson(x):
    """Inverse Simpson diversity."""
    p = x[x > 0] / x[x > 0].sum()
    return 1.0 / np.sum(p ** 2)


# ─────────────────────────────── PCA


def run_metabolomics_pca(df: pd.DataFrame,
                         metadata_df: Optional[pd.DataFrame] = None,
                         group_column: Optional[str] = None,
                         n_components: int = 10,
                         transformation: str = 'zscore') -> Dict[str, Any]:
    """
    PCA on metabolite intensities.

    Parameters
    ----------
    df : DataFrame, samples × metabolites (or metabolites × samples).
         If index looks like metabolite names, transpose.
    metadata_df : optional sample metadata
    group_column : metadata column for coloring
    n_components : number of PCs to retain
    transformation : 'zscore', 'log', 'clr', or 'none'

    Returns
    -------
    dict with keys 'pca_df', 'explained_variance_ratio', 'loadings',
    'cumulative_variance', 'n_components', 'transformation', 'plot_data'
    """
    # Standard format: samples as rows, metabolites as columns
    # No auto-transpose to avoid confusion with metadata indexing
    pass

    X = df.values.astype(float)

    if transformation == 'zscore':
        X = StandardScaler().fit_transform(X)
    elif transformation == 'log':
        X = np.log1p(X)
        X = StandardScaler().fit_transform(X)
    elif transformation == 'clr':
        X = _center_log_ratio(pd.DataFrame(X, index=df.index, columns=df.columns)).values
    # 'none' → raw

    n_components = min(n_components, min(X.shape) - 1, X.shape[1])
    pca = PCA(n_components=n_components)
    scores = pca.fit_transform(X)

    evr = pca.explained_variance_ratio_.tolist()
    cumvar = np.cumsum(evr).tolist()
    loadings = pd.DataFrame(
        pca.components_.T,
        index=df.columns,
        columns=[f'PC{i+1}' for i in range(n_components)]
    )

    pca_df = pd.DataFrame(
        scores,
        index=df.index,
        columns=[f'PC{i+1}' for i in range(n_components)]
    )

    # Build Plotly scatter data
    plot_data = None
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        common = pca_df.index.intersection(metadata_df.index)
        groups = metadata_df.loc[common, group_column]
        traces = []
        for grp in groups.unique():
            mask = groups == grp
            traces.append({
                'x': pca_df.loc[mask, 'PC1'].tolist(),
                'y': pca_df.loc[mask, 'PC2'].tolist(),
                'mode': 'markers',
                'name': str(grp),
                'text': mask[mask].index.tolist(),
                'marker': {'size': 10, 'opacity': 0.8},
            })
        plot_data = {
            'data': traces,
            'layout': {
                'title': f'Metabolome PCA (PC1={evr[0]*100:.1f}%, PC2={evr[1]*100:.1f}%)',
                'xaxis': {'title': f'PC1 ({evr[0]*100:.1f}%)'},
                'yaxis': {'title': f'PC2 ({evr[1]*100:.1f}%)'},
                'hovermode': 'closest',
            }
        }

    return {
        'pca_df': pca_df.to_dict(),
        'explained_variance_ratio': evr,
        'cumulative_variance': cumvar,
        'loadings': loadings.to_dict(),
        'n_components': n_components,
        'transformation': transformation,
        'plot_data': plot_data,
    }


# ─────────────────────────────── Alpha Diversity (Metabolomics)


def run_metabolomics_alpha_diversity(df: pd.DataFrame,
                                      metadata_df: Optional[pd.DataFrame] = None,
                                      group_column: Optional[str] = None,
                                      metrics: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Compute alpha-diversity metrics for metabolite profiles.

    Treats each metabolite as an analogue of an OTU/ASV.
    """
    if metrics is None:
        metrics = ['richness', 'shannon', 'simpson', 'pielou', 'inverse_simpson']

    # Standard format: samples as rows, metabolites as columns
    # No auto-transpose to avoid confusion with metadata indexing
    pass

    results = {}
    for m in metrics:
        if m == 'richness':
            vals = df.apply(_richness, axis=1)
        elif m == 'shannon':
            vals = df.apply(_shannon, axis=1)
        elif m == 'simpson':
            vals = df.apply(_simpson, axis=1)
        elif m == 'pielou':
            vals = df.apply(_pielou, axis=1)
        elif m == 'inverse_simpson':
            vals = df.apply(_inverse_simpson, axis=1)
        else:
            continue
        results[m] = vals.to_dict()

    # Plotly boxplot data
    plot_data = None
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        common = df.index.intersection(metadata_df.index)
        groups = metadata_df.loc[common, group_column]
        traces = []
        for metric in metrics[:3]:  # first 3 for plot
            for grp in groups.unique():
                mask = groups == grp
                vals = [results[metric][s] for s in mask[mask].index]
                traces.append({
                    'y': vals,
                    'type': 'box',
                    'name': f'{grp}',
                    'x': [str(grp)] * len(vals),
                })
        plot_data = {
            'data': traces,
            'layout': {'title': 'Metabolome Alpha Diversity by Group',
                       'yaxis': {'title': 'Diversity Index'},
                       'boxmode': 'group'}
        }

    return {
        'metrics': metrics,
        'alpha_diversity': results,
        'summary': {m: {'mean': float(np.mean(list(results[m].values()))),
                        'std': float(np.std(list(results[m].values()))),
                        'median': float(np.median(list(results[m].values()))),
                        'min': float(np.min(list(results[m].values()))),
                        'max': float(np.max(list(results[m].values())))}
                    for m in metrics},
        'plot_data': plot_data,
    }


# ─────────────────────────────── Marker Discovery (vs Day 0)


def run_metabolomics_marker_discovery(df: pd.DataFrame,
                                      metadata_df: pd.DataFrame,
                                      group_column: str = 'Visit',
                                      reference_group: str = 'T4',
                                      test_method: str = 'welch',
                                      pvalue_threshold: float = 0.05,
                                      fc_threshold: float = 1.5,
                                      transformation: str = 'log1p') -> Dict[str, Any]:
    """
    Differential metabolite analysis comparing each non-reference group
    to the reference group (e.g., Day 0 / T4).

    Parameters
    ----------
    df : metabolite intensity matrix, samples × metabolites
    metadata_df : sample metadata with group_column
    group_column : metadata grouping variable (e.g. 'Visit')
    reference_group : reference level (e.g. 'T4' for Day 0)
    test_method : 'welch', 'mannwhitney', or 'ttest'
    pvalue_threshold : significance threshold
    fc_threshold : fold-change threshold (absolute)
    transformation : 'log1p', 'log', 'none'

    Returns
    -------
    dict with per-group comparison results, volcano data, and top markers.
    """
    # Standard format: samples as rows, metabolites as columns
    # No auto-transpose to avoid confusion with metadata indexing
    pass
    X = df.values.astype(float)

    if transformation == 'log1p':
        X = np.log1p(X)
    elif transformation == 'log':
        X = np.log(X + 1e-6)
    elif transformation == 'zscore':
        X = StandardScaler().fit_transform(X)
    elif transformation == 'clr':
        X = _center_log_ratio(df).values
        X = np.log1p(X)
    elif transformation == 'log':
        X = np.log(X + 1e-6)
    elif transformation == 'zscore':
        X = StandardScaler().fit_transform(X)

    common = df.index.intersection(metadata_df.index)
    groups = metadata_df.loc[common, group_column]

    if reference_group not in groups.values:
        raise ValueError(f"Reference group '{reference_group}' not found in {group_column}. "
                         f"Available: {groups.unique().tolist()}")

    ref_mask = groups == reference_group
    ref_samples = df.index[ref_mask]

    all_results = []
    group_results = {}

    for grp in groups.unique():
        if str(grp) == str(reference_group):
            continue

        grp_mask = groups == grp
        grp_samples = df.index[grp_mask]

        if len(grp_samples) < 2 or len(ref_samples) < 2:
            logger.warning(f"Skipping {grp} vs {reference_group}: insufficient samples")
            continue

        grp_X = X[grp_mask[common].values]
        ref_X = X[ref_mask[common].values]

        pvals = []
        fc = []
        mean_ref = []
        mean_grp = []

        for j in range(X.shape[1]):
            g = grp_X[:, j]
            r = ref_X[:, j]

            # Fold change (grp / ref) on original scale
            m_g = np.mean(df.iloc[grp_mask[common].values, j])
            m_r = np.mean(df.iloc[ref_mask[common].values, j])
            fc_val = m_g / (m_r + 1e-9)
            fc.append(fc_val)
            mean_ref.append(m_r)
            mean_grp.append(m_g)

            if test_method == 'welch':
                _, p = stats.ttest_ind(g, r, equal_var=False)
            elif test_method == 'ttest':
                _, p = stats.ttest_ind(g, r, equal_var=True)
            elif test_method == 'mannwhitney':
                try:
                    _, p = stats.mannwhitneyu(g, r, alternative='two-sided')
                except ValueError:
                    p = 1.0
            else:
                p = 1.0

            pvals.append(p)

        # BH FDR correction
        from statsmodels.stats.multitest import multipletests
        _, pvals_adj, _, _ = multipletests(pvals, method='fdr_bh')

        res_df = pd.DataFrame({
            'metabolite': df.columns,
            'mean_ref': mean_ref,
            'mean_group': mean_grp,
            'fold_change': fc,
            'log2_fc': np.log2(fc),
            'pvalue': pvals,
            'padj': pvals_adj,
        })

        res_df['significant'] = (res_df['padj'] < pvalue_threshold) & (abs(res_df['log2_fc']) > np.log2(fc_threshold))
        res_df['direction'] = res_df['log2_fc'].apply(lambda x: 'up' if x > 0 else 'down')

        group_results[grp] = {
            'n_ref': int(ref_mask.sum()),
            'n_group': int(grp_mask.sum()),
            'n_significant': int(res_df['significant'].sum()),
            'n_up': int((res_df['significant'] & (res_df['direction'] == 'up')).sum()),
            'n_down': int((res_df['significant'] & (res_df['direction'] == 'down')).sum()),
            'results': res_df.to_dict(orient='records'),
            'top_markers': res_df[res_df['significant']].sort_values('padj').head(20).to_dict(orient='records'),
        }

        all_results.append(res_df.assign(comparison=f'{grp}_vs_{reference_group}'))

    # Combined volcano plot data
    volcano_plot = None
    if all_results:
        combined = pd.concat(all_results)
        traces = []
        for grp in combined['comparison'].unique():
            sub = combined[combined['comparison'] == grp]
            sig = sub[sub['significant']]
            ns = sub[~sub['significant']]
            traces.append({
                'x': ns['log2_fc'].tolist(),
                'y': [-np.log10(p + 1e-300) for p in ns['pvalue'].tolist()],
                'mode': 'markers',
                'name': f'{grp} (NS)',
                'marker': {'color': 'grey', 'size': 6, 'opacity': 0.5},
                'text': ns['metabolite'].tolist(),
            })
            traces.append({
                'x': sig['log2_fc'].tolist(),
                'y': [-np.log10(p + 1e-300) for p in sig['pvalue'].tolist()],
                'mode': 'markers',
                'name': f'{grp} (sig)',
                'marker': {'color': 'red', 'size': 10, 'opacity': 0.8},
                'text': sig['metabolite'].tolist(),
            })
        volcano_plot = {
            'data': traces,
            'layout': {
                'title': f'Metabolite Marker Discovery vs {reference_group}',
                'xaxis': {'title': 'log2(Fold Change)'},
                'yaxis': {'title': '-log10(p-value)'},
                'shapes': [
                    {'type': 'line', 'x0': -np.log2(fc_threshold), 'x1': -np.log2(fc_threshold),
                     'y0': 0, 'y1': 1, 'yref': 'paper', 'line': {'dash': 'dash', 'color': 'blue'}},
                    {'type': 'line', 'x0': np.log2(fc_threshold), 'x1': np.log2(fc_threshold),
                     'y0': 0, 'y1': 1, 'yref': 'paper', 'line': {'dash': 'dash', 'color': 'blue'}},
                    {'type': 'line', 'x0': -1, 'x1': 1, 'xref': 'paper',
                     'y0': -np.log10(pvalue_threshold), 'y1': -np.log10(pvalue_threshold),
                     'line': {'dash': 'dash', 'color': 'blue'}},
                ]
            }
        }

    return {
        'reference_group': reference_group,
        'group_column': group_column,
        'test_method': test_method,
        'transformation': transformation,
        'pvalue_threshold': pvalue_threshold,
        'fc_threshold': fc_threshold,
        'comparisons': group_results,
        'volcano_plot': volcano_plot,
        'summary': {grp: {
            'n_significant': group_results[grp]['n_significant'],
            'n_up': group_results[grp]['n_up'],
            'n_down': group_results[grp]['n_down'],
        } for grp in group_results},
    }


# ─────────────────────────────── Entry point


def run_metabolomics_analysis(df: pd.DataFrame,
                              metadata_df: Optional[pd.DataFrame] = None,
                              parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Unified metabolomics analysis entry point.

    Parameters
    ----------
    parameters keys:
        - analysis_type : 'pca', 'alpha_diversity', 'marker_discovery', or 'all'
        - group_column : metadata grouping column
        - reference_group : reference level for marker discovery (default 'T4')
        - n_components : PCA components (default 10)
        - transformation : 'zscore', 'log1p', 'clr', 'log', 'none'
        - test_method : 'welch', 'ttest', 'mannwhitney'
        - pvalue_threshold : 0.05
        - fc_threshold : 1.5
    """
    params = parameters or {}
    analysis_type = params.get('analysis_type', 'all')
    group_column = params.get('group_column', None)
    reference_group = params.get('reference_group', 'T4')

    results = {}

    if analysis_type in ('pca', 'all'):
        results['pca'] = run_metabolomics_pca(
            df, metadata_df, group_column,
            n_components=params.get('n_components', 10),
            transformation=params.get('transformation', 'zscore')
        )

    if analysis_type in ('alpha_diversity', 'all'):
        results['alpha_diversity'] = run_metabolomics_alpha_diversity(
            df, metadata_df, group_column,
            metrics=params.get('alpha_metrics', ['richness', 'shannon', 'simpson', 'pielou', 'inverse_simpson'])
        )

    if analysis_type in ('marker_discovery', 'all'):
        if metadata_df is not None and group_column and group_column in metadata_df.columns:
            results['marker_discovery'] = run_metabolomics_marker_discovery(
                df, metadata_df,
                group_column=group_column,
                reference_group=reference_group,
                test_method=params.get('test_method', 'welch'),
                pvalue_threshold=params.get('pvalue_threshold', 0.05),
                fc_threshold=params.get('fc_threshold', 1.5),
                transformation=params.get('transformation', 'log1p')
            )
        else:
            results['marker_discovery'] = {'error': 'metadata and group_column required for marker discovery'}

    return results
