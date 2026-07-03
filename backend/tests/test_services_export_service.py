"""Tests for export_service.py module."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.export_service import export_data, export_plot, export_result


class TestExportData:
    """Test suite for data export functions."""

    def test_export_csv(self, sample_feature_table):
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
            source = f.name
        sample_feature_table.to_csv(source, sep="\t")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            target = f.name
        export_data(source, target, "csv")
        assert Path(target).exists()
        df = pd.read_csv(target, index_col=0)
        assert df.shape == sample_feature_table.shape
        Path(source).unlink()
        Path(target).unlink()

    def test_export_tsv(self, sample_feature_table):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            source = f.name
        sample_feature_table.to_csv(source)
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f:
            target = f.name
        export_data(source, target, "tsv")
        assert Path(target).exists()
        df = pd.read_csv(target, sep="\t", index_col=0)
        assert df.shape == sample_feature_table.shape
        Path(source).unlink()
        Path(target).unlink()

    def test_export_json(self, sample_feature_table):
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
            source = f.name
        sample_feature_table.to_csv(source, sep="\t")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            target = f.name
        export_data(source, target, "json")
        assert Path(target).exists()
        data = json.loads(Path(target).read_text())
        assert isinstance(data, list)
        Path(source).unlink()
        Path(target).unlink()

    def test_export_invalid_format(self, sample_feature_table):
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w") as f:
            source = f.name
        sample_feature_table.to_csv(source, sep="\t")
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            target = f.name
        with pytest.raises(ValueError, match="Unsupported export format"):
            export_data(source, target, "xyz")
        Path(source).unlink()
        Path(target).unlink()


class TestExportResult:
    """Test suite for result export functions."""

    def test_export_result_json(self):
        result = {"sample_diversity": {"S1": {"shannon": 1.5}}}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            target = f.name
        export_result(result, target, "json")
        assert Path(target).exists()
        data = json.loads(Path(target).read_text())
        assert "sample_diversity" in data
        Path(target).unlink()

    def test_export_result_csv(self):
        result = {"sample_diversity": {"S1": {"shannon": 1.5}, "S2": {"shannon": 2.0}}}
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            target = f.name
        export_result(result, target, "csv")
        assert Path(target).exists()
        df = pd.read_csv(target)
        assert "sample" in df.columns
        Path(target).unlink()

    def test_export_result_tsv(self):
        result = {"sample_diversity": {"S1": {"shannon": 1.5}}}
        with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f:
            target = f.name
        export_result(result, target, "tsv")
        assert Path(target).exists()
        Path(target).unlink()

    def test_export_result_html(self):
        result = {"sample_diversity": {"S1": {"shannon": 1.5}}}
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            target = f.name
        export_result(result, target, "html")
        assert Path(target).exists()
        content = Path(target).read_text()
        assert "<html>" in content
        Path(target).unlink()

    def test_export_result_none(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            target = f.name
        with pytest.raises(ValueError, match="No result data to export"):
            export_result(None, target, "json")
        Path(target).unlink()

    def test_export_result_unsupported_format(self):
        result = {"sample_diversity": {"S1": {"shannon": 1.5}}}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            target = f.name
        export_result(result, target, "unsupported")
        assert Path(target).exists()
        Path(target).unlink()


class TestExportPlot:
    """Test suite for plot export functions."""

    def test_export_plot_html(self):
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            target = f.name
        export_plot("sid", target, "html")
        assert Path(target).exists()
        content = Path(target).read_text()
        assert "<html>" in content
        Path(target).unlink()

    def test_export_plot_json_no_results(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            target = f.name
        export_plot("nonexistent-sid", target, "json")
        assert Path(target).exists()
        Path(target).unlink()
