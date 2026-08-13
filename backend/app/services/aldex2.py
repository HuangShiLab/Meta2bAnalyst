"""
ALDEx2-style differential abundance analysis for microbiome data.

Implements:
- CLR (Centered Log-Ratio) transformation
- Welch's t-test or Mann-Whitney U test per feature
- Effect size estimation (median difference in CLR space)
- Volcano plot data generation

Uses only numpy, pandas, scipy, sklearn. No R required.
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Any, Optional


def _clr_transform(df: pd.DataFrame, pseudocount: float = 0.5) -> pd.DataFrame:
    """
    Compute Centered Log-Ratio (CLR) transformation.
    
    CLR(x) = log(x / g(x)) where g(x) is the geometric mean of the composition.
    
    Parameters
    ----------
    df : pd.DataFrame
        Feature table (samples x features) with raw counts or proportions.
    pseudocount : float, default=0.5
        Pseudocount to add before log transform (handles zeros).
    
    Returns
    -------
    pd.DataFrame
        CLR-transformed data with same shape as input.
    """
    # Add pseudocount to handle zeros
    df_pseudo = df + pseudocount
    
    # Compute geometric mean per sample (row)
    log_vals = np.log(df_pseudo)
    row_means = log_vals.mean(axis=1)
    
    # CLR = log(x) - mean(log(x))
    clr_vals = log_vals.subtract(row_means, axis=0)
    
    return clr_vals


def _welch_ttest(clr_df: pd.DataFrame, groups: pd.Series) -> tuple:
    """
    Run Welch's t-test per feature for two groups.
    
    Parameters
    ----------
    clr_df : pd.DataFrame
        CLR-transformed feature table (samples x features).
    groups : pd.Series
        Group labels for each sample (length = n_samples).
    
    Returns
    -------
    tuple : (effects, pvalues, group_means)
        effects : np.ndarray - difference of means (group1 - group2)
        pvalues : np.ndarray - p-values per feature
        group_means : dict - {group_label: mean CLR per feature}
    """
    unique_groups = groups.unique()
    if len(unique_groups) != 2:
        raise ValueError(f"Welch t-test requires exactly 2 groups, found {len(unique_groups)}: {unique_groups}")
    
    g1_mask = groups == unique_groups[0]
    g2_mask = groups == unique_groups[1]
    
    n_features = clr_df.shape[1]
    effects = np.zeros(n_features)
    pvalues = np.ones(n_features)
    
    group_means = {
        str(unique_groups[0]): np.zeros(n_features),
        str(unique_groups[1]): np.zeros(n_features)
    }
    
    for i, col in enumerate(clr_df.columns):
        x1 = clr_df.loc[g1_mask, col].dropna().values
        x2 = clr_df.loc[g2_mask, col].dropna().values
        
        if len(x1) < 2 or len(x2) < 2:
            continue
        
        # Welch's t-test (unequal variances)
        t_stat, pval = stats.ttest_ind(x1, x2, equal_var=False)
        
        effects[i] = np.mean(x1) - np.mean(x2)
        pvalues[i] = pval
        group_means[str(unique_groups[0])][i] = np.mean(x1)
        group_means[str(unique_groups[1])][i] = np.mean(x2)
    
    return effects, pvalues, group_means


def _mann_whitney_u(clr_df: pd.DataFrame, groups: pd.Series) -> tuple:
    """
    Run Mann-Whitney U test per feature for two groups.
    
    Parameters
    ----------
    clr_df : pd.DataFrame
        CLR-transformed feature table (samples x features).
    groups : pd.Series
        Group labels for each sample (length = n_samples).
    
    Returns
    -------
    tuple : (effects, pvalues, group_medians)
        effects : np.ndarray - median difference (group1 - group2)
        pvalues : np.ndarray - p-values per feature
        group_medians : dict - {group_label: median CLR per feature}
    """
    unique_groups = groups.unique()
    if len(unique_groups) != 2:
        raise ValueError(f"Mann-Whitney U requires exactly 2 groups, found {len(unique_groups)}: {unique_groups}")
    
    g1_mask = groups == unique_groups[0]
    g2_mask = groups == unique_groups[1]
    
    n_features = clr_df.shape[1]
    effects = np.zeros(n_features)
    pvalues = np.ones(n_features)
    
    group_medians = {
        str(unique_groups[0]): np.zeros(n_features),
        str(unique_groups[1]): np.zeros(n_features)
    }
    
    for i, col in enumerate(clr_df.columns):
        x1 = clr_df.loc[g1_mask, col].dropna().values
        x2 = clr_df.loc[g2_mask, col].dropna().values
        
        if len(x1) < 2 or len(x2) < 2:
            continue
        
        # Mann-Whitney U test
        u_stat, pval = stats.mannwhitneyu(x1, x2, alternative='two-sided')
        
        effects[i] = np.median(x1) - np.median(x2)
        pvalues[i] = pval
        group_medians[str(unique_groups[0])][i] = np.median(x1)
        group_medians[str(unique_groups[1])][i] = np.median(x2)
    
    return effects, pvalues, group_medians


def _kruskal_wallis(clr_df: pd.DataFrame, groups: pd.Series) -> tuple:
    """
    Run Kruskal-Wallis H-test per feature for >2 groups.
    
    Parameters
    ----------
    clr_df : pd.DataFrame
        CLR-transformed feature table (samples x features).
    groups : pd.Series
        Group labels for each sample.
    
    Returns
    -------
    tuple : (effects, pvalues, group_medians)
        effects : np.ndarray - max median difference across groups
        pvalues : np.ndarray - p-values per feature
        group_medians : dict - {group_label: median CLR per feature}
    """
    unique_groups = groups.unique()
    n_features = clr_df.shape[1]
    effects = np.zeros(n_features)
    pvalues = np.ones(n_features)
    
    group_medians = {str(g): np.zeros(n_features) for g in unique_groups}
    
    for i, col in enumerate(clr_df.columns):
        group_samples = []
        medians = []
        
        for g in unique_groups:
            samples = clr_df.loc[groups == g, col].dropna().values
            if len(samples) > 0:
                group_samples.append(samples)
                medians.append(np.median(samples))
                group_medians[str(g)][i] = np.median(samples)
        
        if len(group_samples) < 2:
            continue
        
        # Kruskal-Wallis H-test
        h_stat, pval = stats.kruskal(*group_samples)
        
        effects[i] = max(medians) - min(medians) if medians else 0
        pvalues[i] = pval
    
    return effects, pvalues, group_medians


def run_aldex2(
    df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    group_column: str,
    test_method: str = 'welch',
    pseudocount: float = 0.5,
    p_adjust_method: str = 'fdr_bh',
    effect_threshold: float = 1.0,
    alpha: float = 0.05
) -> Dict[str, Any]:
    """
    Run ALDEx2-style differential abundance analysis.
    
    Performs CLR transformation followed by differential testing per feature.
    Returns volcano plot data and summary statistics.
    
    Parameters
    ----------
    df : pd.DataFrame
        Feature abundance table (samples x features) with non-negative values.
    metadata_df : pd.DataFrame
        Sample metadata with sample IDs as index.
    group_column : str
        Column name in metadata_df containing group labels.
    test_method : str, default='welch'
        Statistical test to use: 'welch' (Welch's t-test), 'mannwhitney' (Mann-Whitney U),
        or 'kruskal' (Kruskal-Wallis for >2 groups).
    pseudocount : float, default=0.5
        Pseudocount added before CLR transform.
    p_adjust_method : str, default='fdr_bh'
        P-value correction method passed to statsmodels/stats.multitest.
    effect_threshold : float, default=1.0
        Threshold for |effect size| to call a feature "biologically significant".
    alpha : float, default=0.05
        Significance threshold for adjusted p-values.
    
    Returns
    -------
    dict
        {
            'plot_data': {
                'volcano': {
                    'x': list[float],           # effect sizes
                    'y': list[float],           # -log10(p-value)
                    'feature_ids': list[str],   # feature names
                    'significant': list[bool],  # whether feature passes thresholds
                    'group_labels': list[str]   # group assignments for coloring
                }
            },
            'statistics': {
                'n_features': int,
                'n_significant': int,           # significant by p-value + effect size
                'n_up': int,                    # enriched in group 1
                'n_down': int,                  # depleted in group 1
                'median_effect': float,
                'max_effect': float,
                'min_pvalue': float,
                'test_method': str,
                'groups': list[str],
                'effect_threshold': float,
                'alpha': float
            },
            'results_table': pd.DataFrame       # detailed per-feature results
        }
    """
    # Validate inputs
    if group_column not in metadata_df.columns:
        raise ValueError(f"Group column '{group_column}' not found in metadata. Columns: {list(metadata_df.columns)}")
    
    # Align samples
    common_samples = df.index.intersection(metadata_df.index)
    if len(common_samples) == 0:
        raise ValueError("No matching sample IDs between feature table and metadata.")
    
    df_aligned = df.loc[common_samples]
    groups = metadata_df.loc[common_samples, group_column]
    
    # Drop samples with missing group labels
    valid_mask = groups.notna()
    df_aligned = df_aligned.loc[valid_mask]
    groups = groups.loc[valid_mask]
    
    if len(groups) < 4:
        raise ValueError(f"Need at least 4 samples with valid group labels, found {len(groups)}.")
    
    unique_groups = groups.unique()
    n_groups = len(unique_groups)
    
    # Step 1: CLR transformation
    clr_df = _clr_transform(df_aligned, pseudocount=pseudocount)
    
    # Step 2: Differential test per feature
    test_method = test_method.lower()
    
    if n_groups == 2 and test_method in ('welch', 'ttest'):
        effects, pvalues, group_stats = _welch_ttest(clr_df, groups)
        test_used = 'welch'
    elif n_groups == 2 and test_method in ('mannwhitney', 'mwu', 'wilcoxon'):
        effects, pvalues, group_stats = _mann_whitney_u(clr_df, groups)
        test_used = 'mannwhitney'
    else:
        # Default to Kruskal-Wallis for >2 groups or when specified
        effects, pvalues, group_stats = _kruskal_wallis(clr_df, groups)
        test_used = 'kruskal'
    
    # Step 3: Multiple testing correction (Benjamini-Hochberg FDR)
    valid_p_mask = ~np.isnan(pvalues) & (pvalues >= 0) & (pvalues <= 1)
    pvalues_adj = np.ones_like(pvalues)
    
    if valid_p_mask.sum() > 0:
        try:
            from statsmodels.stats.multitest import multipletests
            _, pvals_corrected, _, _ = multipletests(
                pvalues[valid_p_mask], alpha=alpha, method=p_adjust_method
            )
            pvalues_adj[valid_p_mask] = pvals_corrected
        except ImportError:
            # Fallback: simple Bonferroni
            n_tests = valid_p_mask.sum()
            pvalues_adj[valid_p_mask] = np.minimum(pvalues[valid_p_mask] * n_tests, 1.0)
    
    # Step 4: Identify significant features
    # ALDEx2-style: significant if |effect| > threshold AND p-value < alpha
    significant = (np.abs(effects) > effect_threshold) & (pvalues_adj < alpha)
    
    feature_ids = list(clr_df.columns)
    
    # Build results table
    results_table = pd.DataFrame({
        'feature': feature_ids,
        'effect': effects,
        'pvalue': pvalues,
        'pvalue_adj': pvalues_adj,
        'significant': significant,
        'abs_effect': np.abs(effects)
    })
    
    # Add group-specific statistics
    for g_name, g_stats in group_stats.items():
        results_table[f'mean_CLR_{g_name}'] = g_stats
    
    results_table = results_table.sort_values('pvalue_adj')
    
    # Step 5: Build plot data
    # Volcano plot: x = effect size, y = -log10(p-value)
    # Cap extremely small p-values for visualization
    log_pvalues = -np.log10(np.maximum(pvalues_adj, 1e-300))
    
    # Determine direction (for 2 groups)
    if n_groups == 2:
        group_labels = [
            f"up_{unique_groups[0]}" if e > 0 else f"up_{unique_groups[1]}"
            if sig else "ns"
            for e, sig in zip(effects, significant)
        ]
        n_up = int(((effects > 0) & significant).sum())
        n_down = int(((effects < 0) & significant).sum())
    else:
        group_labels = ["sig" if s else "ns" for s in significant]
        n_up = int(significant.sum())
        n_down = 0
    
    plot_data = {
        'volcano': {
            'x': effects.tolist(),
            'y': log_pvalues.tolist(),
            'feature_ids': feature_ids,
            'significant': significant.tolist(),
            'group_labels': group_labels,
            'threshold_lines': {
                'effect': effect_threshold,
                'alpha': alpha,
                'neg_log_alpha': -np.log10(alpha)
            }
        }
    }
    
    # Summary statistics
    stats_summary = {
        'n_features': len(feature_ids),
        'n_significant': int(significant.sum()),
        'n_up': n_up,
        'n_down': n_down,
        'median_effect': float(np.median(np.abs(effects))),
        'max_effect': float(np.max(np.abs(effects))),
        'min_pvalue': float(np.min(pvalues_adj[pvalues_adj > 0])) if (pvalues_adj > 0).any() else 1.0,
        'test_method': test_used,
        'groups': [str(g) for g in unique_groups],
        'n_per_group': {str(g): int((groups == g).sum()) for g in unique_groups},
        'effect_threshold': effect_threshold,
        'alpha': alpha,
        'p_adjust_method': p_adjust_method
    }
    
    return {
        'plot_data': plot_data,
        'statistics': stats_summary,
        'results_table': results_table
    }


# Convenience function for API compatibility
def run_aldex2_analysis(df, metadata_df, group_column, **kwargs):
    """Alias for run_aldex2 for backward compatibility."""
    return run_aldex2(df, metadata_df, group_column, **kwargs)
