"""
Meta2bAnalyst - Data Processing Service (Filtering, Normalization, Transformation)
"""
import logging
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy.stats import gmean

logger = logging.getLogger(__name__)


def filter_data(
    df: pd.DataFrame,
    min_samples: int = 1,
    min_abundance: float = 0.0,
    max_features: Optional[int] = None,
    sample_filter: Optional[List[str]] = None,
    feature_filter: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Filter data based on various criteria.

    Args:
        df: Feature table (features x samples)
        min_samples: Minimum number of samples a feature must be present in
        min_abundance: Minimum abundance threshold
        max_features: Maximum number of top features to keep (by mean abundance)
        sample_filter: List of sample names to keep
        feature_filter: List of feature names to keep

    Returns:
        Filtered DataFrame
    """
    filtered = df.copy()
    
    # Filter by sample names
    if sample_filter is not None:
        valid_samples = [s for s in sample_filter if s in filtered.columns]
        filtered = filtered[valid_samples]
        logger.info(f"Filtered to {len(valid_samples)} samples")
    
    # Filter by feature names
    if feature_filter is not None:
        valid_features = [f for f in feature_filter if f in filtered.index]
        filtered = filtered.loc[valid_features]
        logger.info(f"Filtered to {len(valid_features)} features")
    
    # Filter by minimum abundance (presence in at least min_samples)
    if min_abundance > 0 or min_samples > 1:
        presence = (filtered > min_abundance).sum(axis=1)
        filtered = filtered[presence >= min_samples]
        logger.info(f"After abundance filter: {len(filtered)} features")
    
    # Keep top features by mean abundance
    if max_features is not None and len(filtered) > max_features:
        mean_abundance = filtered.mean(axis=1).sort_values(ascending=False)
        top_features = mean_abundance.head(max_features).index.tolist()
        filtered = filtered.loc[top_features]
        logger.info(f"Kept top {max_features} features by mean abundance")
    
    return filtered


def normalize_relative_abundance(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize to relative abundance (sum to 1 per sample)."""
    return df.div(df.sum(axis=0), axis=1).fillna(0)


def normalize_tss(df: pd.DataFrame) -> pd.DataFrame:
    """Total Sum Scaling (TSS) - same as relative abundance."""
    return normalize_relative_abundance(df)


def normalize_css(df: pd.DataFrame, p: float = 0.5) -> pd.DataFrame:
    """
    Cumulative Sum Scaling (CSS) normalization.
    Reference: Paulson et al., Nature Methods 2013.
    """
    # Calculate cumulative sums for each sample
    cumsum_df = df.apply(lambda x: x.sort_values(ascending=False).cumsum(), axis=0)
    
    # Find quantile for each sample
    quantiles = cumsum_df.quantile(p, axis=0)
    
    # Use median of quantiles as scaling factor
    scaling_factor = quantiles.median()
    
    # Normalize
    normalized = df.div(quantiles, axis=1) * scaling_factor
    return normalized.fillna(0)


def normalize_tmm(df: pd.DataFrame, reference_sample: Optional[int] = None) -> pd.DataFrame:
    """
    Trimmed Mean of M-values (TMM) normalization.
    Simplified implementation.
    """
    # Select reference sample (median library size)
    if reference_sample is None:
        lib_sizes = df.sum(axis=0)
        reference_sample = lib_sizes.median()
    
    # Calculate scaling factors (simplified)
    lib_sizes = df.sum(axis=0)
    scaling_factors = lib_sizes / reference_sample
    
    normalized = df.div(scaling_factors, axis=1)
    return normalized.fillna(0)


def normalize_rarefaction(df: pd.DataFrame, target_depth: Optional[int] = None) -> pd.DataFrame:
    """
    Rarefaction normalization.
    Subsample each sample to the target depth without replacement.
    """
    if target_depth is None:
        target_depth = int(df.sum(axis=0).min())
    
    normalized = pd.DataFrame(0, index=df.index, columns=df.columns, dtype=float)
    
    for col in df.columns:
        sample = df[col]
        total = sample.sum()
        if total == 0:
            continue
        
        # Proportional subsampling
        if total <= target_depth:
            normalized[col] = sample
        else:
            # Calculate probabilities
            probs = sample / total
            # Expected counts after rarefaction
            normalized[col] = (probs * target_depth).round().astype(int)
    
    return normalized


def log_transform(df: pd.DataFrame, method: str = "log10") -> pd.DataFrame:
    """Apply log transformation to data."""
    # Add pseudocount to avoid log(0)
    pseudocount = 1e-10
    df_pseudo = df + pseudocount
    
    if method == "log10":
        return np.log10(df_pseudo)
    elif method == "log2":
        return np.log2(df_pseudo)
    elif method == "ln" or method == "log":
        return np.log(df_pseudo)
    elif method == "clr":
        # Centered log-ratio
        geometric_means = gmean(df_pseudo, axis=0)
        return np.log(df_pseudo.div(geometric_means, axis=1))
    else:
        raise ValueError(f"Unknown log transform method: {method}")


def normalize_data(
    df: pd.DataFrame,
    method: str = "relative",
    target_depth: Optional[int] = None,
    log_transform: bool = False,
    log_method: str = "log10",
) -> pd.DataFrame:
    """
    Normalize data using the specified method.

    Args:
        df: Feature table (features x samples)
        method: Normalization method (relative, css, tmm, tss, rarefaction, none)
        target_depth: Target depth for rarefaction
        log_transform: Whether to apply log transformation after normalization
        log_method: Log transformation method (log10, log2, ln, clr)

    Returns:
        Normalized DataFrame
    """
    logger.info(f"Normalizing data with method={method}, log_transform={log_transform}")
    
    if method == "relative":
        normalized = normalize_relative_abundance(df)
    elif method == "tss":
        normalized = normalize_tss(df)
    elif method == "css":
        normalized = normalize_css(df)
    elif method == "tmm":
        normalized = normalize_tmm(df)
    elif method == "rarefaction":
        normalized = normalize_rarefaction(df, target_depth)
    elif method == "none":
        normalized = df.copy()
    else:
        raise ValueError(f"Unknown normalization method: {method}")
    
    if log_transform:
        normalized = log_transform(normalized, method=log_method)
    
    logger.info(f"Normalization complete: shape={normalized.shape}")
    return normalized
