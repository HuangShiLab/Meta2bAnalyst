"""
Meta2bAnalyst - Data Validation Service
"""
import logging
from typing import List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_sample_matching(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    feature_index_col: str = "sample",
    metadata_index_col: str = "sample",
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate that sample names in feature table match metadata.

    Returns:
        Tuple of (is_valid, matched_samples, unmatched_samples)
    """
    feature_samples = set(feature_df.columns)
    metadata_samples = set(metadata_df.index)
    
    matched = feature_samples & metadata_samples
    unmatched_in_feature = feature_samples - metadata_samples
    unmatched_in_metadata = metadata_samples - feature_samples
    
    all_unmatched = list(unmatched_in_feature) + list(unmatched_in_metadata)
    
    is_valid = len(unmatched_in_feature) == 0 and len(unmatched_in_metadata) == 0
    
    if not is_valid:
        logger.warning(f"Sample mismatch: {len(unmatched_in_feature)} in feature table not in metadata, {len(unmatched_in_metadata)} in metadata not in feature table")
    
    return is_valid, list(matched), all_unmatched


def validate_abundance_data(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validate abundance data:
    - No negative values
    - No NA values (or warn about them)
    - At least one non-zero value per sample

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Check for negative values
    if (df < 0).any().any():
        errors.append("Abundance data contains negative values")
    
    # Check for NA values
    na_count = df.isna().sum().sum()
    if na_count > 0:
        errors.append(f"Abundance data contains {na_count} NA values")
    
    # Check for all-zero samples
    zero_samples = df.columns[df.sum(axis=0) == 0].tolist()
    if zero_samples:
        errors.append(f"Samples with zero total abundance: {zero_samples}")
    
    # Check for all-zero features
    zero_features = df.index[df.sum(axis=1) == 0].tolist()
    if zero_features:
        errors.append(f"Features with zero total abundance across all samples: {len(zero_features)}")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_metadata_grouping(
    metadata_df: pd.DataFrame,
    group_column: str,
    min_groups: int = 2,
    min_samples_per_group: int = 2,
) -> Tuple[bool, List[str]]:
    """
    Validate metadata has sufficient grouping for analysis.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    if group_column not in metadata_df.columns:
        errors.append(f"Group column '{group_column}' not found in metadata")
        return False, errors
    
    groups = metadata_df[group_column].dropna().unique()
    if len(groups) < min_groups:
        errors.append(f"Need at least {min_groups} groups, found {len(groups)}: {groups}")
    
    for group in groups:
        group_count = (metadata_df[group_column] == group).sum()
        if group_count < min_samples_per_group:
            errors.append(f"Group '{group}' has only {group_count} samples (minimum {min_samples_per_group})")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_strain_data(
    strain_df: pd.DataFrame,
    species_df: Optional[pd.DataFrame] = None,
    min_ani: float = 95.0,
    max_ani: float = 100.0,
) -> Tuple[bool, List[str]]:
    """
    Validate strain-level data.

    Checks:
    - ANI values are within valid range (0-100)
    - Coverage values are within valid range (0-1)
    - Species-strain consistency (if species_df provided)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Check for ANI column
    ani_cols = [col for col in strain_df.columns if "ani" in col.lower()]
    if not ani_cols:
        errors.append("No ANI column found in strain data")
    else:
        for col in ani_cols:
            if (strain_df[col] < 0).any() or (strain_df[col] > 100).any():
                errors.append(f"ANI values in column '{col}' are outside [0, 100] range")
            if (strain_df[col] < min_ani).any():
                low_ani_count = (strain_df[col] < min_ani).sum()
                errors.append(f"{low_ani_count} strain entries have ANI < {min_ani}%")
    
    # Check for coverage column
    cov_cols = [col for col in strain_df.columns if "coverage" in col.lower() or "cov" in col.lower()]
    if cov_cols:
        for col in cov_cols:
            if (strain_df[col] < 0).any() or (strain_df[col] > 1).any():
                errors.append(f"Coverage values in column '{col}' are outside [0, 1] range")
    
    # Species-strain consistency check (if species data provided)
    if species_df is not None:
        strain_species = set(strain_df.index.get_level_values(0)) if isinstance(strain_df.index, pd.MultiIndex) else set()
        species_names = set(species_df.index)
        
        unmatched = strain_species - species_names
        if unmatched:
            errors.append(f"Strain species not found in species data: {unmatched}")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_data_for_analysis(
    feature_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """
    Comprehensive validation before running analysis.

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []
    
    # Validate abundance data
    abundance_valid, abundance_errors = validate_abundance_data(feature_df)
    errors.extend(abundance_errors)
    
    # Validate metadata if provided
    if metadata_df is not None:
        # Check sample matching
        match_valid, matched, unmatched = validate_sample_matching(feature_df, metadata_df)
        if not match_valid:
            errors.append(f"Sample mismatch: {len(unmatched)} samples do not match between feature table and metadata")
        
        # Check grouping if specified
        if group_column:
            group_valid, group_errors = validate_metadata_grouping(metadata_df, group_column)
            errors.extend(group_errors)
    
    is_valid = len(errors) == 0
    return is_valid, errors
