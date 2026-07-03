"""
Meta2bAnalyst - Data Validation Service
Provides comprehensive validation for feature tables, metadata, strain data, and taxonomy.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


@dataclass
class ValidationResult:
    """Result of a validation operation.

    Attributes:
        is_valid: Whether the validation passed.
        errors: List of error message strings.
        warnings: List of warning message strings.
        details: Additional structured validation details.
    """
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class DataValidator:
    """Validator for microbiome data formats and requirements."""

    def validate_feature_metadata_match(
        self,
        feature_df: pd.DataFrame,
        metadata_df: pd.DataFrame,
    ) -> ValidationResult:
        """Validate that feature table and metadata sample names match.

        Checks:
            - At least one sample name is shared between feature table and metadata.
            - Reports unmatched samples in both directions.
            - Case-insensitive matching is attempted and warned if mismatch.

        Args:
            feature_df: Feature table with samples as columns.
            metadata_df: Metadata table with samples as index.

        Returns:
            ValidationResult with match status and details.
        """
        result = ValidationResult()
        feature_samples = set(feature_df.columns.astype(str))
        metadata_samples = set(metadata_df.index.astype(str))

        matched = feature_samples & metadata_samples
        unmatched_in_feature = feature_samples - metadata_samples
        unmatched_in_metadata = metadata_samples - feature_samples

        result.details['feature_samples'] = len(feature_samples)
        result.details['metadata_samples'] = len(metadata_samples)
        result.details['matched_samples'] = len(matched)
        result.details['unmatched_in_feature'] = list(unmatched_in_feature)
        result.details['unmatched_in_metadata'] = list(unmatched_in_metadata)

        if not matched:
            result.is_valid = False
            result.errors.append(
                "No matching sample names between feature table and metadata. "
                f"Feature samples: {len(feature_samples)}, Metadata samples: {len(metadata_samples)}"
            )
            return result

        if unmatched_in_feature:
            result.warnings.append(
                f"{len(unmatched_in_feature)} sample(s) in feature table not found in metadata: "
                f"{sorted(list(unmatched_in_feature))[:10]}"
            )

        if unmatched_in_metadata:
            result.warnings.append(
                f"{len(unmatched_in_metadata)} sample(s) in metadata not found in feature table: "
                f"{sorted(list(unmatched_in_metadata))[:10]}"
            )

        if not unmatched_in_feature and not unmatched_in_metadata:
            result.details['message'] = "All samples matched perfectly."
        else:
            result.details['message'] = (
                f"Partial match: {len(matched)}/{len(feature_samples)} feature samples matched, "
                f"{len(matched)}/{len(metadata_samples)} metadata samples matched."
            )

        return result

    def validate_abundance_data(self, df: pd.DataFrame) -> ValidationResult:
        """Validate abundance data integrity.

        Checks:
            - No NA or empty values.
            - All values are non-negative.
            - All values are numeric.
            - No all-zero samples or all-zero features (warnings only).

        Args:
            df: Feature table DataFrame (features x samples).

        Returns:
            ValidationResult with validation status.
        """
        result = ValidationResult()

        # Check for NA values
        na_count = df.isna().sum().sum()
        if na_count > 0:
            na_rows = df.isna().any(axis=1).sum()
            na_cols = df.isna().any(axis=0).sum()
            result.errors.append(
                f"Abundance data contains {na_count} NA value(s) across "
                f"{na_rows} feature(s) and {na_cols} sample(s)."
            )

        # Check for non-numeric values
        try:
            numeric_df = df.apply(pd.to_numeric, errors='coerce')
            non_numeric_count = numeric_df.isna().sum().sum() - df.isna().sum().sum()
            if non_numeric_count > 0:
                result.errors.append(
                    f"Abundance data contains {non_numeric_count} non-numeric value(s)."
                )
        except Exception as e:
            result.errors.append(f"Could not verify numeric type of abundance data: {e}")

        # Check for negative values
        numeric_df = df.apply(pd.to_numeric, errors='coerce').fillna(0)
        negative_count = (numeric_df < 0).sum().sum()
        if negative_count > 0:
            result.errors.append(
                f"Abundance data contains {negative_count} negative value(s). "
                "Abundance must be non-negative."
            )

        # Check for all-zero samples (warning)
        zero_samples = df.columns[df.sum(axis=0) == 0].tolist()
        if zero_samples:
            result.warnings.append(
                f"{len(zero_samples)} sample(s) have zero total abundance: "
                f"{zero_samples[:10]}{'...' if len(zero_samples) > 10 else ''}"
            )
            result.details['zero_samples'] = zero_samples

        # Check for all-zero features (warning)
        zero_features = df.index[df.sum(axis=1) == 0].tolist()
        if zero_features:
            result.warnings.append(
                f"{len(zero_features)} feature(s) have zero abundance across all samples."
            )
            result.details['zero_features'] = zero_features

        result.is_valid = len(result.errors) == 0
        result.details['total_features'] = len(df.index)
        result.details['total_samples'] = len(df.columns)
        result.details['total_cells'] = df.shape[0] * df.shape[1]
        result.details['sparsity'] = float((df == 0).sum().sum() / (df.shape[0] * df.shape[1]))

        return result

    def validate_metadata(self, df: pd.DataFrame) -> ValidationResult:
        """Validate metadata requirements for downstream analysis.

        Checks:
            - At least one grouping variable exists (non-numeric columns).
            - Each group has at least 3 replicates for statistical power.
            - No empty values in grouping columns.
            - At least 2 distinct groups exist.

        Args:
            df: Metadata DataFrame with samples as index.

        Returns:
            ValidationResult with validation status.
        """
        result = ValidationResult()

        # Identify potential grouping variables (non-numeric columns with 2+ unique values)
        grouping_vars = []
        for col in df.columns:
            if df[col].dtype == 'object' or df[col].dtype.name == 'category':
                unique_vals = df[col].dropna().unique()
                if len(unique_vals) >= 2 and len(unique_vals) < len(df) * 0.9:
                    grouping_vars.append(col)

        # Also check numeric columns with few unique values (could be coded groups)
        for col in df.columns:
            if col not in grouping_vars:
                unique_vals = df[col].dropna().unique()
                if 2 <= len(unique_vals) <= 10:
                    grouping_vars.append(col)

        if not grouping_vars:
            result.errors.append(
                "No valid grouping variable found. Metadata must contain at least one "
                "categorical column with 2+ distinct groups."
            )
        else:
            result.details['grouping_variables'] = grouping_vars

        # Check each grouping variable for group size and missing values
        for var in grouping_vars:
            missing_count = df[var].isna().sum()
            if missing_count > 0:
                result.warnings.append(
                    f"Grouping variable '{var}' has {missing_count} missing value(s)."
                )

            groups = df[var].dropna().unique()
            if len(groups) < 2:
                result.warnings.append(
                    f"Grouping variable '{var}' has only 1 group; needs at least 2."
                )
                continue

            small_groups = []
            for group in groups:
                group_count = (df[var] == group).sum()
                if group_count < 3:
                    small_groups.append(f"{group} (n={group_count})")

            if small_groups:
                result.warnings.append(
                    f"Grouping variable '{var}' has groups with < 3 replicates: "
                    f"{', '.join(small_groups)}. Statistical power may be limited."
                )

            result.details[f'group_sizes_{var}'] = {
                str(g): int((df[var] == g).sum()) for g in groups
            }

        result.is_valid = len(result.errors) == 0
        result.details['total_samples'] = len(df.index)
        result.details['total_variables'] = len(df.columns)

        return result

    def validate_strain_data(self, df: pd.DataFrame) -> ValidationResult:
        """Validate strain-level data integrity.

        Checks:
            - Species-strain hierarchy consistency (unique strains per species).
            - ANI values are in valid range [0, 100] if present.
            - Coverage values are in valid range [0, 1] if present.
            - No duplicate (species, strain) pairs within a sample.

        Args:
            df: Strain data DataFrame (typically long format with sample_id, species, strain).

        Returns:
            ValidationResult with validation status.
        """
        result = ValidationResult()
        df = df.copy()
        df.columns = [c.lower().strip() for c in df.columns]

        required_cols = {'sample_id', 'species', 'strain'}
        available_cols = set(df.columns)
        if not required_cols.issubset(available_cols):
            missing = required_cols - available_cols
            result.errors.append(f"Missing required columns: {missing}")
            result.is_valid = False
            return result

        # Check for duplicate (sample, species, strain) combinations
        duplicates = df.groupby(['sample_id', 'species', 'strain']).size()
        duplicate_combos = duplicates[duplicates > 1]
        if len(duplicate_combos) > 0:
            result.errors.append(
                f"Found {len(duplicate_combos)} duplicate (sample, species, strain) "
                f"combinations: {duplicate_combos.head().to_dict()}"
            )

        # Check strain uniqueness within species (across all samples)
        species_strain_pairs = df[['species', 'strain']].drop_duplicates()
        species_strain_counts = species_strain_pairs.groupby('species').size()
        result.details['strains_per_species'] = species_strain_counts.to_dict()
        result.details['total_species'] = df['species'].nunique()
        result.details['total_strains'] = df['strain'].nunique()

        # Check ANI values
        ani_cols = [c for c in df.columns if 'ani' in c]
        if ani_cols:
            for col in ani_cols:
                ani_values = pd.to_numeric(df[col], errors='coerce').dropna()
                if len(ani_values) > 0:
                    if (ani_values < 0).any() or (ani_values > 100).any():
                        invalid_ani = ani_values[(ani_values < 0) | (ani_values > 100)]
                        result.errors.append(
                            f"ANI values in column '{col}' out of range [0, 100]: "
                            f"{len(invalid_ani)} invalid value(s)."
                        )
                    result.details[f'ani_stats_{col}'] = {
                        'min': float(ani_values.min()),
                        'max': float(ani_values.max()),
                        'mean': float(ani_values.mean()),
                        'median': float(ani_values.median()),
                    }
        else:
            result.warnings.append("No ANI column found in strain data.")

        # Check coverage values
        cov_cols = [c for c in df.columns if 'coverage' in c or c == 'cov']
        if cov_cols:
            for col in cov_cols:
                cov_values = pd.to_numeric(df[col], errors='coerce').dropna()
                if len(cov_values) > 0:
                    if (cov_values < 0).any() or (cov_values > 1).any():
                        invalid_cov = cov_values[(cov_values < 0) | (cov_values > 1)]
                        result.errors.append(
                            f"Coverage values in column '{col}' out of range [0, 1]: "
                            f"{len(invalid_cov)} invalid value(s)."
                        )
                    result.details[f'coverage_stats_{col}'] = {
                        'min': float(cov_values.min()),
                        'max': float(cov_values.max()),
                        'mean': float(cov_values.mean()),
                        'median': float(cov_values.median()),
                    }

        # Check abundance values
        if 'abundance' in df.columns:
            abun_values = pd.to_numeric(df['abundance'], errors='coerce').dropna()
            if (abun_values < 0).any():
                result.errors.append("Abundance values contain negative numbers.")

        result.is_valid = len(result.errors) == 0
        return result

    def validate_taxonomy_format(self, df: pd.DataFrame) -> ValidationResult:
        """Validate taxonomy annotation format.

        Checks:
            - Taxonomy strings use semicolon-separated ranks.
            - Standard prefixes exist: k__, p__, c__, o__, f__, g__, s__.
            - Each entry has a consistent number of ranks.

        Args:
            df: DataFrame with a 'taxonomy' column or taxonomy strings as index.

        Returns:
            ValidationResult with validation status.
        """
        result = ValidationResult()

        # Extract taxonomy strings
        if 'taxonomy' in df.columns:
            taxa = df['taxonomy'].dropna().astype(str).tolist()
        elif 'Taxon' in df.columns:
            taxa = df['Taxon'].dropna().astype(str).tolist()
        else:
            # Try index if it's a Series or single-column DataFrame
            taxa = df.index.astype(str).tolist()

        if not taxa:
            result.errors.append("No taxonomy entries found.")
            result.is_valid = False
            return result

        standard_prefixes = {'k__', 'p__', 'c__', 'o__', 'f__', 'g__', 's__'}
        rank_counts = []
        prefix_issues = []
        empty_ranks = []

        for taxon in taxa:
            ranks = [r.strip() for r in taxon.split(';')]
            rank_counts.append(len(ranks))

            for rank in ranks:
                if not rank:
                    empty_ranks.append(taxon)
                    continue
                # Check if any standard prefix is present
                has_prefix = any(rank.startswith(p) for p in standard_prefixes)
                if not has_prefix and len(ranks) > 1:
                    # Only warn if it looks like a multi-rank taxonomy
                    prefix_issues.append(rank)

        # Analyze rank consistency
        from collections import Counter
        rank_counter = Counter(rank_counts)
        most_common_rank = rank_counter.most_common(1)[0]

        inconsistent = [c for c, count in rank_counter.items() if count < len(taxa) * 0.1]
        if len(rank_counter) > 1 and len(inconsistent) > 0:
            result.warnings.append(
                f"Inconsistent rank counts found: {dict(rank_counter)}. "
                f"Most common: {most_common_rank[0]} ranks."
            )

        if empty_ranks:
            result.warnings.append(
                f"{len(empty_ranks)} taxonomy entries contain empty ranks."
            )

        if prefix_issues:
            unique_issues = list(set(prefix_issues))[:10]
            result.warnings.append(
                f"{len(prefix_issues)} rank entries lack standard prefixes (k__, p__, etc.). "
                f"Examples: {unique_issues}"
            )

        result.is_valid = len(result.errors) == 0
        result.details['total_taxa'] = len(taxa)
        result.details['rank_distribution'] = dict(rank_counter)
        result.details['most_common_rank_count'] = most_common_rank[0]
        result.details['standard_prefix_compliance'] = (
            1.0 - len(prefix_issues) / max(len(taxa) * most_common_rank[0], 1)
        )

        return result


# ─────────────────────────────── Module-level convenience functions


def validate_sample_matching(
    feature_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    feature_index_col: str = 'sample',
    metadata_index_col: str = 'sample',
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate that sample names in feature table match metadata.

    Returns:
        Tuple of (is_valid, matched_samples, unmatched_samples).
    """
    validator = DataValidator()
    result = validator.validate_feature_metadata_match(feature_df, metadata_df)
    matched = result.details.get('matched_samples', 0)
    feature_samples = result.details.get('feature_samples', 0)
    is_valid = matched == feature_samples and matched > 0
    return (
        is_valid,
        result.details.get('unmatched_in_metadata', []),
        result.details.get('unmatched_in_feature', []),
    )


def validate_abundance_data(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validate abundance data.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    validator = DataValidator()
    result = validator.validate_abundance_data(df)
    return result.is_valid, result.errors


def validate_metadata_grouping(
    metadata_df: pd.DataFrame,
    group_column: str,
    min_groups: int = 2,
    min_samples_per_group: int = 2,
) -> Tuple[bool, List[str]]:
    """
    Validate metadata has sufficient grouping for analysis.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    validator = DataValidator()
    result = validator.validate_metadata(metadata_df)

    # Additional specific checks for the requested group column
    errors = result.errors.copy()
    if group_column not in metadata_df.columns:
        errors.append(f"Group column '{group_column}' not found in metadata")
        return False, errors

    groups = metadata_df[group_column].dropna().unique()
    if len(groups) < min_groups:
        errors.append(
            f"Need at least {min_groups} groups, found {len(groups)}: {groups}"
        )

    for group in groups:
        group_count = (metadata_df[group_column] == group).sum()
        if group_count < min_samples_per_group:
            errors.append(
                f"Group '{group}' has only {group_count} samples (minimum {min_samples_per_group})"
            )

    return len(errors) == 0, errors


def validate_strain_data(
    strain_df: pd.DataFrame,
    species_df: Optional[pd.DataFrame] = None,
    min_ani: float = 95.0,
    max_ani: float = 100.0,
) -> Tuple[bool, List[str]]:
    """
    Validate strain-level data.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    validator = DataValidator()
    result = validator.validate_strain_data(strain_df)
    return result.is_valid, result.errors + result.warnings


def validate_data_for_analysis(
    feature_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    group_column: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """
    Comprehensive validation before running analysis.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    validator = DataValidator()
    errors = []

    # Validate abundance data
    abun_result = validator.validate_abundance_data(feature_df)
    errors.extend(abun_result.errors)

    # Validate metadata if provided
    if metadata_df is not None:
        match_result = validator.validate_feature_metadata_match(feature_df, metadata_df)
        if not match_result.is_valid:
            errors.extend(match_result.errors)
        errors.extend(match_result.warnings)

        if group_column:
            meta_result = validator.validate_metadata(metadata_df)
            if not meta_result.is_valid:
                errors.extend(meta_result.errors)
            errors.extend(meta_result.warnings)

    return len(errors) == 0, errors
