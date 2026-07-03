"""Tests for data_parser.py."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.data_parser import DataParser, detect_file_format, parse_data_file


class TestDataParser:
    """Test suite for DataParser class."""

    def test_parse_csv_tsv(self, temp_csv_file, sample_feature_table):
        """Test CSV parsing."""
        parser = DataParser()
        df = parser.parse_csv_tsv(temp_csv_file, sep=",")
        assert df.shape == sample_feature_table.shape
        assert list(df.index) == list(sample_feature_table.index)
        assert list(df.columns) == list(sample_feature_table.columns)

    def test_parse_tsv(self, temp_tsv_file, sample_feature_table):
        """Test TSV parsing."""
        parser = DataParser()
        df = parser.parse_csv_tsv(temp_tsv_file, sep="\t")
        assert df.shape == sample_feature_table.shape

    def test_parse_csv_with_name_header(self):
        """Test CSV/TSV with #NAME header prefix."""
        lines = ["#NAME"]
        lines += ["\tSample_01\tSample_02\tSample_03"]
        lines += ["Feature_01\t10\t20\t30"]
        lines += ["Feature_02\t5\t15\t25"]
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
            f.write("\n".join(lines))
            path = f.name
        parser = DataParser()
        df = parser.parse_csv_tsv(path, sep="\t")
        assert df.shape == (2, 3)
        assert list(df.columns) == ["Sample_01", "Sample_02", "Sample_03"]
        Path(path).unlink()

    def test_parse_biom(self, temp_biom_file):
        """Test BIOM JSON fallback parsing."""
        parser = DataParser()
        df, tax_df = parser.parse_biom(temp_biom_file)
        assert df.shape == (5, 5)
        assert tax_df is not None
        assert "taxonomy" in tax_df.columns

    def test_parse_mothur_shared(self, temp_mothur_shared_file):
        """Test Mothur shared file parsing."""
        parser = DataParser()
        df, tax_df = parser.parse_mothur(temp_mothur_shared_file)
        assert df.shape == (5, 5)
        assert tax_df is None

    def test_parse_mothur_with_taxonomy(self, temp_mothur_shared_file, temp_mothur_taxonomy_file):
        """Test Mothur shared + taxonomy parsing."""
        parser = DataParser()
        df, tax_df = parser.parse_mothur(temp_mothur_shared_file, temp_mothur_taxonomy_file)
        assert df.shape == (5, 5)
        assert tax_df is not None
        assert "taxonomy" in tax_df.columns

    def test_parse_2brad_m(self, temp_tsv_file, temp_metadata_file):
        """Test 2bRAD-M parsing."""
        parser = DataParser()
        result = parser.parse_2brad_m(temp_tsv_file, temp_metadata_file)
        assert "species" in result
        assert "metadata" in result
        assert "functional" in result
        assert result["functional"] is None
        assert result["species"].shape[0] == 20

    def test_parse_strain2bscan(self, temp_strain2bscan_file, sample_strain_data):
        """Test Strain2bScan parsing."""
        parser = DataParser()
        df = parser.parse_strain2bscan(temp_strain2bscan_file)
        assert set(df.columns) == {"sample_id", "species", "strain", "abundance"}
        assert len(df) == len(sample_strain_data)

    def test_parse_tag2bmap(self, sample_strain_data):
        """Test Tag2bMap parsing."""
        lines = ["sample\tspecies\tstrain\tani\tcov\tabundance"]
        for _, row in sample_strain_data.head(10).iterrows():
            lines.append(
                f"{row['sample_id']}\t{row['species']}\t{row['strain']}\t{row['ani']}\t{row['coverage']}\t{row['abundance']}"
            )
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
            f.write("\n".join(lines))
            path = f.name
        parser = DataParser()
        df = parser.parse_tag2bmap(path)
        assert set(df.columns) >= {"sample_id", "species", "strain", "ani", "coverage", "abundance"}
        assert len(df) == 10
        Path(path).unlink()

    def test_to_wide_format(self, sample_strain_data):
        """Test long-to-wide format conversion."""
        parser = DataParser()
        wide = parser.to_wide_format(
            sample_strain_data, sample_col="sample_id", feature_col="strain", value_col="abundance"
        )
        assert wide.shape[0] == sample_strain_data["sample_id"].nunique()
        assert wide.shape[1] == sample_strain_data["strain"].nunique()


class TestFileFormatDetection:
    """Test file format detection."""

    def test_detect_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        assert detect_file_format(Path(path)) == "csv"
        Path(path).unlink()

    def test_detect_tsv(self):
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f:
            path = f.name
        assert detect_file_format(Path(path)) == "tsv"
        Path(path).unlink()

    def test_detect_biom(self):
        with tempfile.NamedTemporaryFile(suffix=".biom", delete=False) as f:
            path = f.name
        assert detect_file_format(Path(path)) == "biom"
        Path(path).unlink()

    def test_detect_mothur_shared(self):
        with tempfile.NamedTemporaryFile(suffix=".shared", delete=False) as f:
            path = f.name
        assert detect_file_format(Path(path)) == "mothur_shared"
        Path(path).unlink()

    def test_detect_unknown(self):
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            path = f.name
        assert detect_file_format(Path(path)) == "unknown"
        Path(path).unlink()

    def test_detect_strain(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("sample_id\tspecies\tstrain\tani\t\n")
            path = f.name
        assert detect_file_format(Path(path)) == "strain"
        Path(path).unlink()


class TestParseDataFile:
    """Test the generic parse_data_file function."""

    def test_parse_csv(self, temp_csv_file, sample_feature_table):
        df, fmt = parse_data_file(Path(temp_csv_file))
        assert fmt == "csv"
        assert df.shape == sample_feature_table.shape

    def test_parse_tsv(self, temp_tsv_file, sample_feature_table):
        df, fmt = parse_data_file(Path(temp_tsv_file))
        assert fmt == "tsv"
        assert df.shape == sample_feature_table.shape
