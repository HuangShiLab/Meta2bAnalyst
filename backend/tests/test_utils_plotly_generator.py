"""Tests for plotly_generator.py utility module."""
import numpy as np
import pandas as pd
import pytest

from app.utils.plotly_generator import (
    create_bar_chart,
    create_box_plot,
    create_heatmap_plot,
    create_pcoa_plot,
    create_scatter_plot,
    create_volcano_plot,
    plot_to_json,
)


class TestPlotlyGenerator:
    """Test suite for Plotly figure generators."""

    def test_create_bar_chart(self):
        df = pd.DataFrame({"x": ["A", "B", "C"], "y": [10, 20, 30]})
        fig = create_bar_chart(df, "x", "y", title="Test Bar")
        assert "data" in fig
        assert "layout" in fig
        assert fig["layout"]["title"] == "Test Bar"

    def test_create_bar_chart_with_color(self):
        df = pd.DataFrame({"x": ["A", "B", "C"], "y": [10, 20, 30], "group": ["G1", "G1", "G2"]})
        fig = create_bar_chart(df, "x", "y", color_column="group")
        assert len(fig["data"]) == 2

    def test_create_scatter_plot(self):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        fig = create_scatter_plot(df, "x", "y", title="Test Scatter")
        assert fig["data"][0]["type"] == "scatter"

    def test_create_scatter_plot_with_color_and_size(self):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6], "group": ["A", "A", "B"], "size": [10, 20, 30]})
        fig = create_scatter_plot(df, "x", "y", color_column="group", size_column="size")
        assert len(fig["data"]) == 2

    def test_create_pcoa_plot_with_groups(self):
        coords = {"S1": [1, 2, 3], "S2": [4, 5, 6], "S3": [7, 8, 9]}
        groups = {"S1": "A", "S2": "A", "S3": "B"}
        fig = create_pcoa_plot(coords, [50.0, 30.0, 20.0], group_metadata=groups)
        assert "data" in fig
        assert len(fig["data"]) >= 2

    def test_create_pcoa_plot_without_groups(self):
        coords = {"S1": [1, 2], "S2": [3, 4]}
        fig = create_pcoa_plot(coords, [50.0, 50.0])
        assert "data" in fig
        assert fig["data"][0]["type"] == "scatter"

    def test_create_pcoa_plot_3d(self):
        coords = {"S1": [1, 2, 3], "S2": [4, 5, 6]}
        fig = create_pcoa_plot(coords, [50.0, 30.0, 20.0])
        assert fig["data"][0]["type"] == "scatter3d"

    def test_create_heatmap_plot(self):
        matrix = pd.DataFrame(np.random.rand(5, 5))
        fig = create_heatmap_plot(matrix, ["f1", "f2", "f3", "f4", "f5"], ["s1", "s2", "s3", "s4", "s5"])
        assert fig["data"][0]["type"] == "heatmap"

    def test_create_box_plot(self):
        df = pd.DataFrame({"value": [1, 2, 3, 4, 5, 6], "group": ["A", "A", "A", "B", "B", "B"]})
        fig = create_box_plot(df, "value", "group")
        assert len(fig["data"]) == 2

    def test_create_volcano_plot(self):
        df = pd.DataFrame({
            "log2_fold_change": [-2, -1, 0, 1, 2],
            "pvalue": [0.001, 0.01, 0.5, 0.01, 0.001],
            "feature": ["A", "B", "C", "D", "E"],
        })
        fig = create_volcano_plot(df, "log2_fold_change", "pvalue")
        assert fig["data"][0]["type"] == "scatter"
        assert "shapes" in fig["layout"]

    def test_plot_to_json(self):
        fig = {"data": [], "layout": {"title": "Test"}}
        json_str = plot_to_json(fig)
        assert "Test" in json_str
