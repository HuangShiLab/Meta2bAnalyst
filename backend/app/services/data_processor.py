"""
Meta2bAnalyst - Data Processing Service (Filtering, Normalization, Transformation)
Implements standard microbiome data preprocessing pipelines.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class DataProcessor:
    """Processor for microbiome data filtering, normalization, and transformation."""

    def remove_constant_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove features that have the same value across all samples.

        Args:
            df: Feature table (features x samples).

        Returns:
            Filtered DataFrame with constant features removed.
        """
        # Check variance along rows (features)
        variances = df.var(axis=1, skipna=True)
        constant_mask = variances == 0
        constant_count = constant_mask.sum()

        if constant_count > 0:
            logger.info(
                f"Removing {constant_count} constant features (zero variance)"
            )
            return df.loc[~constant_mask].copy()
        return df.copy()

    def remove_singletons(
        self,
        df: pd.DataFrame,
        mode: str = 'one_sample',
    ) -> pd.DataFrame:
        """Remove singleton features from the feature table.

        Singletons are features with very low occurrence:
            - 'one_sample': features present in only one sample.
            - 'one_total': features with total read count of 1 across all samples.

        Args:
            df: Feature table (features x samples).
            mode: Removal mode ('one_sample' or 'one_total').

        Returns:
            Filtered DataFrame with singletons removed.

        Raises:
            ValueError: If mode is not recognized.
        """
        if mode == 'one_sample':
            # Features present in only one sample (non-zero in exactly 1 sample)
            presence = (df > 0).sum(axis=1)
            singleton_mask = presence == 1
            removed = singleton_mask.sum()
            logger.info(f"Removing {removed} singletons (present in only 1 sample)")
            return df.loc[~singleton_mask].copy()

        elif mode == 'one_total':
            # Features with total count of 1
            total_counts = df.sum(axis=1)
            singleton_mask = total_counts == 1
            removed = singleton_mask.sum()
            logger.info(f"Removing {removed} singletons (total count = 1)")
            return df.loc[~singleton_mask].copy()

        else:
            raise ValueError(f"Unknown singleton removal mode: {mode}. Use 'one_sample' or 'one_total'.")

    def apply_low_count_filter(
        self,
        df: pd.DataFrame,
        min_count: int = 4,
        method: str = 'prevalence',
        threshold: float = 0.2,
    ) -> Tuple[pd.DataFrame, dict]:
        """Apply low-count filtering to remove rare features.

        Methods:
            - 'prevalence': Keep features present in at least `threshold` fraction
              of samples with count >= `min_count`.
            - 'mean': Keep features with average count >= `min_count`.
            - 'median': Keep features with median count >= `min_count`.

        Args:
            df: Feature table (features x samples).
            min_count: Minimum count threshold.
            method: Filtering method ('prevalence', 'mean', or 'median').
            threshold: For prevalence method, minimum fraction of samples.

        Returns:
            Tuple of (filtered DataFrame, filtering statistics dict).
        """
        original_count = len(df)
        stats_dict = {
            'original_features': original_count,
            'method': method,
            'min_count': min_count,
            'threshold': threshold,
        }

        if method == 'prevalence':
            min_samples = max(1, int(np.ceil(threshold * len(df.columns))))
            prevalence = (df >= min_count).sum(axis=1)
            keep_mask = prevalence >= min_samples
            stats_dict['min_samples_required'] = min_samples

        elif method == 'mean':
            means = df.mean(axis=1)
            keep_mask = means >= min_count

        elif method == 'median':
            medians = df.median(axis=1)
            keep_mask = medians >= min_count

        else:
            raise ValueError(f"Unknown low-count filter method: {method}")

        filtered_df = df.loc[keep_mask].copy()
        removed_count = original_count - len(filtered_df)

        stats_dict['filtered_features'] = len(filtered_df)
        stats_dict['removed_features'] = removed_count
        stats_dict['removal_rate'] = removed_count / original_count if original_count > 0 else 0.0

        logger.info(
            f"Low-count filter ({method}): removed {removed_count}/{original_count} features "
            f"({stats_dict['removal_rate']:.1%})"
        )
        return filtered_df, stats_dict

    def apply_variance_filter(
        self,
        df: pd.DataFrame,
        percentage: float = 0.1,
        method: str = 'iqr',
    ) -> Tuple[pd.DataFrame, dict]:
        """Remove low-variance features.

        Removes the bottom `percentage` of features by variance metric.

        Methods:
            - 'iqr': Interquartile range (Q3 - Q1).
            - 'sd': Standard deviation.
            - 'cv': Coefficient of variation (sd / mean).

        Args:
            df: Feature table (features x samples).
            percentage: Fraction of lowest-variance features to remove (0.0-1.0).
            method: Variance metric ('iqr', 'sd', or 'cv').

        Returns:
            Tuple of (filtered DataFrame, filtering statistics dict).
        """
        original_count = len(df)
        stats_dict = {
            'original_features': original_count,
            'method': method,
            'percentage': percentage,
        }

        if method == 'iqr':
            q1 = df.quantile(0.25, axis=1)
            q3 = df.quantile(0.75, axis=1)
            variance_metric = q3 - q1
        elif method == 'sd':
            variance_metric = df.std(axis=1, skipna=True)
        elif method == 'cv':
            means = df.mean(axis=1).replace(0, np.nan)
            stds = df.std(axis=1, skipna=True)
            variance_metric = stds / means
            variance_metric = variance_metric.fillna(0)
        else:
            raise ValueError(f"Unknown variance filter method: {method}")

        # Determine threshold (remove bottom percentage)
        threshold = variance_metric.quantile(percentage)
        keep_mask = variance_metric >= threshold

        # If threshold removes everything, keep at least one feature
        if keep_mask.sum() == 0:
            keep_mask = variance_metric >= variance_metric.min()
            logger.warning("Variance filter threshold removed all features; keeping all.")

        filtered_df = df.loc[keep_mask].copy()
        removed_count = original_count - len(filtered_df)

        stats_dict['filtered_features'] = len(filtered_df)
        stats_dict['removed_features'] = removed_count
        stats_dict['removal_rate'] = removed_count / original_count if original_count > 0 else 0.0
        stats_dict['variance_threshold'] = float(threshold)

        logger.info(
            f"Variance filter ({method}): removed {removed_count}/{original_count} features "
            f"({stats_dict['removal_rate']:.1%})"
        )
        return filtered_df, stats_dict

    def rarefy(
        self,
        df: pd.DataFrame,
        depth: Optional[int] = None,
    ) -> pd.DataFrame:
        """Rarefy (subsample) each sample to a specified depth without replacement.

        Uses scipy.stats.rv_discrete for random subsampling.

        Args:
            df: Feature table (features x samples) with count data.
            depth: Target rarefaction depth. If None, uses the minimum sample depth.

        Returns:
            Rarefied DataFrame with the same shape.

        Raises:
            ValueError: If any sample has insufficient depth.
        """
        sample_depths = df.sum(axis=0)

        if depth is None:
            depth = int(sample_depths.min())
            logger.info(f"Using minimum sample depth as rarefaction depth: {depth}")
        else:
            depth = int(depth)

        # Check for samples with insufficient depth
        insufficient = sample_depths[sample_depths < depth]
        if len(insufficient) > 0:
            raise ValueError(
                f"Samples with insufficient depth for rarefaction to {depth}: "
                f"{insufficient.to_dict()}"
            )

        rarefied = pd.DataFrame(0, index=df.index, columns=df.columns, dtype=int)

        for col in df.columns:
            sample = df[col]
            total = int(sample.sum())
            if total == 0:
                continue

            # Get non-zero features and their proportions
            nonzero = sample[sample > 0]
            if len(nonzero) == 0:
                continue

            # Use scipy.stats.rv_discrete for multinomial sampling
            values = np.arange(len(nonzero))
            probs = nonzero.values / total
            rv = stats.rv_discrete(values=(values, probs))

            # Draw `depth` samples
            draws = rv.rvs(size=depth)
            counts = np.bincount(draws, minlength=len(nonzero))

            # Assign back to rarefied DataFrame
            rarefied.loc[nonzero.index, col] = counts

        logger.info(f"Rarefaction complete: all samples subsampled to depth={depth}")
        return rarefied

    def normalize_tss(self, df: pd.DataFrame) -> pd.DataFrame:
        """Total Sum Scaling (TSS) normalization.

        Scales each sample so that the total sum of counts equals 1.0
        (relative abundance / proportions).

        Args:
            df: Feature table (features x samples).

        Returns:
            Normalized DataFrame where each column sums to 1.0.
        """
        col_sums = df.sum(axis=0)
        # Avoid division by zero
        col_sums = col_sums.replace(0, np.nan)
        normalized = df.div(col_sums, axis=1).fillna(0)
        return normalized

    def normalize_css(self, df: pd.DataFrame, p: float = 0.5) -> pd.DataFrame:
        """Cumulative Sum Scaling (CSS) normalization.

        Reference: Paulson et al., Nature Methods 2013.
        CSS finds the quantile at which the cumulative sum of counts reaches
        a fixed percentile, then uses the median of these quantiles across
        samples as a scaling factor.

        Args:
            df: Feature table (features x samples) with count data.
            p: Quantile for cumulative sum (default 0.5 = median).

        Returns:
            CSS-normalized DataFrame.
        """
        # Calculate cumulative sums for each sample (sorted descending)
        sorted_df = df.apply(lambda x: x.sort_values(ascending=False).values, axis=0, result_type='expand')
        sorted_df.index = range(len(sorted_df))
        cumsum_df = sorted_df.cumsum(axis=0)

        # Find the quantile position for each sample
        total_counts = df.sum(axis=0)
        quantile_targets = total_counts * p

        # Find the count value at which cumulative sum reaches the target quantile
        quantile_values = pd.Series(index=df.columns, dtype=float)
        for col in df.columns:
            target = quantile_targets[col]
            cumsum = cumsum_df[col].values
            # Find first index where cumsum >= target
            idx = np.searchsorted(cumsum, target, side='left')
            if idx < len(sorted_df):
                quantile_values[col] = sorted_df.iloc[idx, col]
            else:
                quantile_values[col] = sorted_df.iloc[-1, col] if len(sorted_df) > 0 else 1.0

        # Replace zero quantiles with a small value to avoid division by zero
        quantile_values = quantile_values.replace(0, np.nan).fillna(1e-10)

        # Use median of quantiles as reference scaling factor
        scaling_factor = quantile_values.median()

        # Normalize: divide each sample by its quantile, multiply by scaling factor
        normalized = df.div(quantile_values, axis=1) * scaling_factor
        normalized = normalized.fillna(0)

        logger.info(f"CSS normalization: scaling_factor={scaling_factor:.4f}")
        return normalized

    def normalize_uq(self, df: pd.DataFrame) -> pd.DataFrame:
        """Upper Quantile Scaling normalization.

        Scales each sample by its upper quantile (75th percentile of non-zero values).

        Args:
            df: Feature table (features x samples).

        Returns:
            Upper-quantile normalized DataFrame.
        """
        # Calculate upper quantile (75th percentile of non-zero values per sample)
        def upper_quantile(x):
            nonzero = x[x > 0]
            if len(nonzero) == 0:
                return 1.0
            return nonzero.quantile(0.75)

        uq = df.apply(upper_quantile, axis=0)
        uq = uq.replace(0, np.nan).fillna(1.0)

        # Use median of upper quantiles as reference
        scaling_factor = uq.median()
        normalized = df.div(uq, axis=1) * scaling_factor
        normalized = normalized.fillna(0)

        logger.info(f"UQ normalization: scaling_factor={scaling_factor:.4f}")
        return normalized

    def transform_clr(self, df: pd.DataFrame) -> pd.DataFrame:
        """Centered Log-Ratio (CLR) transformation.

        Handles zero values by adding a pseudo-count (0.5 * minimum non-zero value).

        Args:
            df: Feature table (features x samples).

        Returns:
            CLR-transformed DataFrame.
        """
        # Add pseudo-count to handle zeros
        min_nonzero = df[df > 0].min().min()
        if pd.isna(min_nonzero) or min_nonzero == 0:
            min_nonzero = 1e-10
        pseudocount = 0.5 * min_nonzero

        df_pseudo = df + pseudocount

        # Calculate geometric mean per sample
        log_df = np.log(df_pseudo)
        gm = log_df.mean(axis=0)

        # CLR = log(x) - mean(log(x))
        clr = log_df.sub(gm, axis=1)

        logger.info(f"CLR transformation: pseudo-count={pseudocount:.6f}")
        return clr

    def transform_rle(self, df: pd.DataFrame) -> pd.DataFrame:
        """Relative Log Expression (RLE) transformation.

        Reference: Anders & Huber, Genome Biology 2010 (DESeq normalization).
        Computes size factors as the median of ratios to a reference sample
        (geometric mean across samples), then divides by size factors.

        Args:
            df: Feature table (features x samples).

        Returns:
            RLE-normalized DataFrame.
        """
        # Add small pseudo-count to avoid zeros
        min_nonzero = df[df > 0].min().min()
        if pd.isna(min_nonzero) or min_nonzero == 0:
            min_nonzero = 1e-10
        df_pseudo = df + 0.5 * min_nonzero

        # Calculate geometric mean across samples for each feature
        log_df = np.log(df_pseudo)
        ref = log_df.mean(axis=1)
        ref = np.exp(ref)

        # Calculate ratio of each sample to reference, then median ratio = size factor
        ratios = df_pseudo.div(ref, axis=0)
        size_factors = ratios.median(axis=0)
        size_factors = size_factors.replace(0, np.nan).fillna(1.0)

        # Normalize by size factors
        normalized = df_pseudo.div(size_factors, axis=1)
        normalized = normalized.fillna(0)

        logger.info(f"RLE normalization: size_factors median={size_factors.median():.4f}")
        return normalized

    def transform_tmm(self, df: pd.DataFrame) -> pd.DataFrame:
        """Trimmed Mean of M-values (TMM) normalization.

        Reference: Robinson & Oshlack, Genome Biology 2010 (edgeR).
        Simplified implementation that computes scaling factors based on
        library size ratios to a reference sample.

        Args:
            df: Feature table (features x samples).

        Returns:
            TMM-normalized DataFrame.
        """
        # Add pseudo-count
        min_nonzero = df[df > 0].min().min()
        if pd.isna(min_nonzero) or min_nonzero == 0:
            min_nonzero = 1e-10
        df_pseudo = df + 0.5 * min_nonzero

        # Select reference sample (sample with library size closest to median)
        lib_sizes = df_pseudo.sum(axis=0)
        median_lib = lib_sizes.median()
        ref_sample = (lib_sizes - median_lib).abs().idxmin()

        ref_counts = df_pseudo[ref_sample]

        scaling_factors = pd.Series(index=df.columns, dtype=float)
        for col in df.columns:
            if col == ref_sample:
                scaling_factors[col] = 1.0
                continue

            sample_counts = df_pseudo[col]

            # Calculate M and A values for each feature
            # M = log2(sample / ref), A = 0.5 * log2(sample * ref)
            m_values = np.log2(sample_counts / ref_counts.replace(0, np.nan))
            a_values = 0.5 * np.log2(sample_counts * ref_counts.replace(0, np.nan))

            # Remove NaN and Inf values
            valid_mask = m_values.notna() & a_values.notna() & np.isfinite(m_values) & np.isfinite(a_values)
            m_valid = m_values[valid_mask]
            a_valid = a_values[valid_mask]

            if len(m_valid) == 0:
                scaling_factors[col] = 1.0
                continue

            # Trim extreme M values (30% from each end) and A values (top/bottom 5%)
            m_trim_lower = m_valid.quantile(0.3)
            m_trim_upper = m_valid.quantile(0.7)
            a_trim_lower = a_valid.quantile(0.05)
            a_trim_upper = a_valid.quantile(0.95)

            trim_mask = (
                (m_valid >= m_trim_lower) & (m_valid <= m_trim_upper) &
                (a_valid >= a_trim_lower) & (a_valid <= a_trim_upper)
            )
            m_trimmed = m_valid[trim_mask]

            if len(m_trimmed) == 0:
                scaling_factors[col] = 1.0
                continue

            # Scaling factor = 2^median(M)
            sf = 2 ** m_trimmed.median()
            scaling_factors[col] = sf

        # Normalize by scaling factors (relative to reference)
        scaling_factors = scaling_factors.replace(0, np.nan).fillna(1.0)
        normalized = df_pseudo.div(scaling_factors, axis=1)
        normalized = normalized.fillna(0)

        logger.info(
            f"TMM normalization: reference={ref_sample}, "
            f"sf_range=[{scaling_factors.min():.4f}, {scaling_factors.max():.4f}]"
        )
        return normalized


# ─────────────────────────────── Module-level convenience functions


def filter_data(
    df: pd.DataFrame,
    min_samples: int = 1,
    min_abundance: float = 0.0,
    max_features: Optional[int] = None,
    sample_filter: Optional[List[str]] = None,
    feature_filter: Optional[List[str]] = None,
    variance_remove_ratio: float = 0.0,
    variance_based: str = "iqr",
    abundance_method: str = "prevalence",
) -> pd.DataFrame:
    """
    Filter data based on various criteria.

    Args:
        df: Feature table (features x samples).
        min_samples: Minimum number of samples a feature must be present in.
        min_abundance: Minimum abundance threshold.
        max_features: Maximum number of top features to keep (by mean abundance).
        sample_filter: List of sample names to keep.
        feature_filter: List of feature names to keep.
        variance_remove_ratio: Remove this fraction (0-0.9) of features with the
            lowest dispersion. 0 disables the low-variance filter.
        variance_based: Dispersion measure for the low-variance filter:
            'iqr' (inter-quartile range), 'sd' (standard deviation), or
            'cv' (coefficient of variation).
        abundance_method: How the low-count filter is applied:
            'prevalence' (default): keep features exceeding min_abundance in at
                least min_samples samples;
            'mean': keep features whose mean abundance >= min_abundance;
            'median': keep features whose median abundance >= min_abundance.

    Returns:
        Filtered DataFrame.
    """
    processor = DataProcessor()
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

    # Filter by abundance
    if abundance_method == "mean":
        if min_abundance > 0:
            filtered = filtered[filtered.mean(axis=1) >= min_abundance]
            logger.info(f"After mean-abundance filter (>= {min_abundance}): {len(filtered)} features")
    elif abundance_method == "median":
        if min_abundance > 0:
            filtered = filtered[filtered.median(axis=1) >= min_abundance]
            logger.info(f"After median-abundance filter (>= {min_abundance}): {len(filtered)} features")
    elif min_abundance > 0 or min_samples > 1:
        # prevalence: present above min_abundance in at least min_samples samples
        presence = (filtered > min_abundance).sum(axis=1)
        filtered = filtered[presence >= min_samples]
        logger.info(f"After prevalence filter: {len(filtered)} features")

    # Remove low-dispersion features (they carry little discriminative signal)
    if variance_remove_ratio > 0 and len(filtered) > 1:
        ratio = min(variance_remove_ratio, 0.9)
        if variance_based == "sd":
            dispersion = filtered.std(axis=1)
        elif variance_based == "cv":
            mean = filtered.mean(axis=1)
            dispersion = filtered.std(axis=1) / mean.replace(0, np.nan)
            dispersion = dispersion.fillna(0.0)
        else:  # iqr
            dispersion = filtered.quantile(0.75, axis=1) - filtered.quantile(0.25, axis=1)
        n_keep = max(1, int(round(len(filtered) * (1 - ratio))))
        keep = dispersion.sort_values(ascending=False).head(n_keep).index
        filtered = filtered.loc[keep]
        logger.info(f"After {variance_based} low-variance filter ({ratio:.0%} removed): {len(filtered)} features")

    # Keep top features by mean abundance
    if max_features is not None and len(filtered) > max_features:
        mean_abundance = filtered.mean(axis=1).sort_values(ascending=False)
        top_features = mean_abundance.head(max_features).index.tolist()
        filtered = filtered.loc[top_features]
        logger.info(f"Kept top {max_features} features by mean abundance")

    return filtered


def normalize_relative_abundance(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize to relative abundance (sum to 1 per sample)."""
    processor = DataProcessor()
    return processor.normalize_tss(df)


def normalize_tss(df: pd.DataFrame) -> pd.DataFrame:
    """Total Sum Scaling (TSS) - same as relative abundance."""
    processor = DataProcessor()
    return processor.normalize_tss(df)


def normalize_css(df: pd.DataFrame, p: float = 0.5) -> pd.DataFrame:
    """Cumulative Sum Scaling (CSS) normalization."""
    processor = DataProcessor()
    return processor.normalize_css(df, p=p)


def normalize_uq(df: pd.DataFrame) -> pd.DataFrame:
    """Upper Quantile Scaling normalization."""
    processor = DataProcessor()
    return processor.normalize_uq(df)


def normalize_rarefaction(df: pd.DataFrame, target_depth: Optional[int] = None) -> pd.DataFrame:
    """Rarefaction normalization."""
    processor = DataProcessor()
    return processor.rarefy(df, depth=target_depth)


def log_transform(df: pd.DataFrame, method: str = "log10") -> pd.DataFrame:
    """Apply log transformation to data."""
    pseudocount = 1e-10
    df_pseudo = df + pseudocount

    if method == "log10":
        return np.log10(df_pseudo)
    elif method == "log2":
        return np.log2(df_pseudo)
    elif method in ("ln", "log"):
        return np.log(df_pseudo)
    elif method == "clr":
        processor = DataProcessor()
        return processor.transform_clr(df)
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
        df: Feature table (features x samples).
        method: Normalization method (relative, css, tmm, tss, rarefaction, none, clr, rle, uq).
        target_depth: Target depth for rarefaction.
        log_transform: Whether to apply log transformation after normalization.
        log_method: Log transformation method (log10, log2, ln, clr).

    Returns:
        Normalized DataFrame.
    """
    processor = DataProcessor()
    logger.info(f"Normalizing data with method={method}, log_transform={log_transform}")

    if method == "relative":
        normalized = processor.normalize_tss(df)
    elif method == "tss":
        normalized = processor.normalize_tss(df)
    elif method == "css":
        normalized = processor.normalize_css(df)
    elif method == "tmm":
        normalized = processor.transform_tmm(df)
    elif method == "rle":
        normalized = processor.transform_rle(df)
    elif method == "uq":
        normalized = processor.normalize_uq(df)
    elif method == "rarefaction":
        normalized = processor.rarefy(df, depth=target_depth)
    elif method == "clr":
        normalized = processor.transform_clr(df)
    elif method == "none":
        normalized = df.copy()
    else:
        raise ValueError(f"Unknown normalization method: {method}")

    if log_transform and method not in ("clr",):
        normalized = log_transform(normalized, method=log_method)

    logger.info(f"Normalization complete: shape={normalized.shape}")
    return normalized
