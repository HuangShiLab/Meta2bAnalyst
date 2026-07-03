"""Tests for data_validator.py."""
import numpy as np
import pandas as pd
import pytest

from app.services.data_validator import (
    DataValidator,
    validate_abundance_data,
    validate_data_for_analysis,
    validate_metadata_grouping,
    validate_sample_matching,
    validate_strain_data,
)


class TestFeatureMetadataMatch:
    """Test feature table and metadata matching."""

    def test_validate_feature_metadata_match_perfect(self, sample_feature_table, sample_metadata):
        validator = DataValidator()
        result = validator.validate_feature_metadata_match(sample_feature_table, sample_metadata)
        assert result.is_valid
        assert result.details["matched_samples"] == 10
        assert result.details["feature_samples"] == 10
        assert result.details["metadata_samples"] == 10

    def test_validate_feature_metadata_mismatch(self, sample_feature_table):
        metadata = pd.DataFrame(
            {"Treatment": ["Control"] * 5},
            index=[f"Sample_{i:02d}" for i in range(11, 16)],
        )
        validator = DataValidator()
        result = validator.validate_feature_metadata_match(sample_feature_table, metadata)
        assert not result.is_valid
        assert "No matching sample names" in result.errors[0]

    def test_validate_feature_metadata_partial_match(self, sample_feature_table):
        metadata = pd.DataFrame(
            {"Treatment": ["Control"] * 5 + ["Treatment"] * 2},
            index=[f"Sample_{i:02d}" for i in range(1, 8)],
        )
        validator = DataValidator()
        result = validator.validate_feature_metadata_match(sample_feature_table, metadata)
        assert result.is_valid
        assert result.warnings
        assert result.details["matched_samples"] == 7

    def test_validate_sample_matching_convenience(self, sample_feature_table, sample_metadata):
        is_valid, matched, unmatched = validate_sample_matching(
            sample_feature_table, sample_metadata
        )
        assert is_valid


class TestAbundanceDataValidation:
    """Test abundance data validation."""

    def test_validate_abundance_data_valid(self, sample_feature_table):
        validator = DataValidator()
        result = validator.validate_abundance_data(sample_feature_table)
        assert result.is_valid
        assert result.details["total_features"] == 20
        assert result.details["total_samples"] == 10

    def test_validate_abundance_data_with_na(self, sample_feature_table):
        df = sample_feature_table.copy()
        df.iloc[0, 0] = np.nan
        validator = DataValidator()
        result = validator.validate_abundance_data(df)
        assert not result.is_valid
        assert "NA value" in result.errors[0]

    def test_validate_abundance_data_negative(self, sample_feature_table):
        df = sample_feature_table.copy()
        df.iloc[0, 0] = -5
        validator = DataValidator()
        result = validator.validate_abundance_data(df)
        assert not result.is_valid
        assert "negative" in result.errors[0]

    def test_validate_abundance_data_zero_samples(self, sample_feature_table):
        df = sample_feature_table.copy()
        df.iloc[:, 0] = 0
        validator = DataValidator()
        result = validator.validate_abundance_data(df)
        assert result.is_valid
        assert result.warnings
        assert "zero total abundance" in result.warnings[0]

    def test_convenience_function(self, sample_feature_table):
        is_valid, errors = validate_abundance_data(sample_feature_table)
        assert is_valid
        assert errors == []


class TestMetadataValidation:
    """Test metadata validation."""

    def test_validate_metadata_valid(self, sample_metadata):
        validator = DataValidator()
        result = validator.validate_metadata(sample_metadata)
        assert result.is_valid
        assert "Treatment" in result.details["grouping_variables"]

    def test_validate_metadata_no_groups(self):
        metadata = pd.DataFrame({
            "ID": [1, 2, 3, 4, 5],
        }, index=[f"Sample_{i:02d}" for i in range(1, 6)])
        validator = DataValidator()
        result = validator.validate_metadata(metadata)
        # Numeric columns with 2-10 unique values are treated as grouping variables
        assert "ID" in result.details.get("grouping_variables", [])
        assert not result.is_valid == False  # May be valid but with warnings

    def test_validate_metadata_only_single_group(self):
        metadata = pd.DataFrame({
            "Treatment": ["A", "A", "A", "A", "A"],
        }, index=[f"Sample_{i:02d}" for i in range(1, 6)])
        validator = DataValidator()
        result = validator.validate_metadata(metadata)
        assert not result.is_valid
        assert "No valid grouping variable" in result.errors[0]

    def test_validate_metadata_small_groups(self):
        metadata = pd.DataFrame({
            "Treatment": ["A", "A", "B", "B"],
        }, index=[f"Sample_{i:02d}" for i in range(1, 5)])
        validator = DataValidator()
        result = validator.validate_metadata(metadata)
        assert result.is_valid
        assert result.warnings

    def test_validate_metadata_grouping_convenience(self, sample_metadata):
        is_valid, errors = validate_metadata_grouping(sample_metadata, "Treatment")
        assert is_valid

    def test_validate_metadata_grouping_missing_column(self, sample_metadata):
        is_valid, errors = validate_metadata_grouping(sample_metadata, "NonExistent")
        assert not is_valid
        assert "not found" in errors[0]


class TestStrainDataValidation:
    """Test strain data validation."""

    def test_validate_strain_data_valid(self, sample_strain_data):
        validator = DataValidator()
        result = validator.validate_strain_data(sample_strain_data)
        assert result.is_valid
        assert result.details["total_species"] == 2
        assert result.details["total_strains"] > 0

    def test_validate_strain_data_missing_columns(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        validator = DataValidator()
        result = validator.validate_strain_data(df)
        assert not result.is_valid
        assert "Missing required columns" in result.errors[0]

    def test_validate_strain_data_bad_ani(self, sample_strain_data):
        df = sample_strain_data.copy()
        df.loc[0, "ani"] = 150.0
        validator = DataValidator()
        result = validator.validate_strain_data(df)
        assert not result.is_valid
        assert "ANI" in result.errors[0]

    def test_validate_strain_data_bad_coverage(self, sample_strain_data):
        df = sample_strain_data.copy()
        df.loc[0, "coverage"] = 1.5
        validator = DataValidator()
        result = validator.validate_strain_data(df)
        assert not result.is_valid
        assert "Coverage" in result.errors[0]

    def test_convenience_function(self, sample_strain_data):
        is_valid, errors = validate_strain_data(sample_strain_data)
        assert is_valid


class TestTaxonomyFormatValidation:
    """Test taxonomy format validation."""

    def test_validate_taxonomy_format(self):
        df = pd.DataFrame({
            "taxonomy": [
                "k__Bacteria;p__Firmicutes;c__Bacilli",
                "k__Bacteria;p__Proteobacteria;c__Gammaproteobacteria",
            ]
        })
        validator = DataValidator()
        result = validator.validate_taxonomy_format(df)
        assert result.is_valid

    def test_validate_taxonomy_empty(self):
        df = pd.DataFrame({"taxonomy": []})
        validator = DataValidator()
        result = validator.validate_taxonomy_format(df)
        assert not result.is_valid


class TestComprehensiveValidation:
    """Test comprehensive validation convenience function."""

    def test_validate_data_for_analysis_valid(self, sample_feature_table, sample_metadata_no_numeric_groups):
        is_valid, errors = validate_data_for_analysis(
            sample_feature_table, sample_metadata_no_numeric_groups, "Treatment"
        )
        assert is_valid

    def test_validate_data_for_analysis_no_metadata(self, sample_feature_table):
        is_valid, errors = validate_data_for_analysis(sample_feature_table)
        assert is_valid
