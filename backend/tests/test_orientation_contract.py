"""Tests for the feature-table orientation contract.

Regression cover for the defect where each analysis guessed the orientation on
its own: on one upload of a 261-samples x 44-genera table, alpha diversity
returned 261 rows while PCoA ordinated 44 genera and PERMANOVA failed with
"need at least 2 groups" -- all three reported HTTP 201 / status "completed".
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis_engine import run_alpha_diversity, run_beta_diversity, run_pcoa
from app.services.orientation import (
    OrientationError,
    assert_sample_alignment,
    resolve_feature_table,
)


@pytest.fixture
def features_x_samples():
    """Canonical orientation: 6 taxa (rows) x 10 samples (columns)."""
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        rng.poisson(15, size=(6, 10)).astype(float),
        index=[f"Genus_{i}" for i in range(6)],
        columns=[f"S{i:03d}" for i in range(10)],
    )


@pytest.fixture
def metadata():
    return pd.DataFrame(
        {"Visit": ["T1"] * 5 + ["T4"] * 5},
        index=[f"S{i:03d}" for i in range(10)],
    )


class TestResolveFeatureTable:
    def test_canonical_orientation_is_left_alone(self, features_x_samples, metadata):
        out, report = resolve_feature_table(features_x_samples, metadata)
        assert not report.transposed
        assert report.confidence == "determined"
        assert list(out.columns) == list(metadata.index)

    def test_samples_x_features_is_transposed(self, features_x_samples, metadata):
        """The layout of the project's own example data (samples as rows)."""
        out, report = resolve_feature_table(features_x_samples.T, metadata)
        assert report.transposed
        assert report.confidence == "determined"
        assert out.shape == features_x_samples.shape
        assert list(out.columns) == list(metadata.index)

    def test_both_orientations_give_identical_results(self, features_x_samples, metadata):
        """The whole point: orientation must not change the numbers."""
        a, _ = resolve_feature_table(features_x_samples, metadata)
        b, _ = resolve_feature_table(features_x_samples.T, metadata)
        pd.testing.assert_frame_equal(a, b)

    def test_no_metadata_assumes_convention_and_says_so(self, features_x_samples):
        out, report = resolve_feature_table(features_x_samples, None)
        assert not report.transposed
        assert report.confidence == "assumed"
        assert report.warnings, "an assumed orientation must be flagged to the caller"

    def test_no_overlap_raises_rather_than_guessing(self, features_x_samples):
        unrelated = pd.DataFrame({"Visit": ["T1", "T4"]}, index=["patient_a", "patient_b"])
        with pytest.raises(OrientationError, match="match any sample ID"):
            resolve_feature_table(features_x_samples, unrelated)

    def test_error_message_shows_both_label_sets(self, features_x_samples):
        unrelated = pd.DataFrame({"Visit": ["T1"]}, index=["patient_a"])
        with pytest.raises(OrientationError) as exc:
            resolve_feature_table(features_x_samples, unrelated)
        message = str(exc.value)
        assert "Genus_0" in message and "patient_a" in message

    def test_ambiguous_orientation_raises(self):
        """Square table whose axes match the metadata equally well."""
        ids = ["S0", "S1"]
        square = pd.DataFrame([[1.0, 2.0], [3.0, 4.0]], index=ids, columns=ids)
        metadata = pd.DataFrame({"g": ["a", "b"]}, index=ids)
        with pytest.raises(OrientationError, match="equally well"):
            resolve_feature_table(square, metadata)

    def test_partial_overlap_warns_about_dropped_samples(self, features_x_samples):
        partial = pd.DataFrame(
            {"Visit": ["T1"] * 6}, index=[f"S{i:03d}" for i in range(6)]
        )
        _, report = resolve_feature_table(features_x_samples, partial)
        assert report.matched_samples == 6
        assert any("no metadata row" in w for w in report.warnings)

    def test_empty_table_raises(self):
        with pytest.raises(OrientationError, match="empty"):
            resolve_feature_table(pd.DataFrame(), None)


class TestAssertSampleAlignment:
    def test_accepts_aligned_data(self, features_x_samples, metadata):
        shared = assert_sample_alignment(features_x_samples, metadata, "Visit")
        assert len(shared) == 10

    def test_missing_metadata_raises(self, features_x_samples):
        with pytest.raises(OrientationError, match="metadata file"):
            assert_sample_alignment(features_x_samples, None, "Visit")

    def test_unknown_group_column_lists_alternatives(self, features_x_samples, metadata):
        with pytest.raises(OrientationError, match="Available columns"):
            assert_sample_alignment(features_x_samples, metadata, "Treatment")

    def test_single_level_group_column_raises(self, features_x_samples, metadata):
        one_level = metadata.assign(Visit="T1")
        with pytest.raises(OrientationError, match="at least 2 are needed"):
            assert_sample_alignment(features_x_samples, one_level, "Visit")

    def test_too_few_shared_samples_raises(self, features_x_samples):
        tiny = pd.DataFrame({"Visit": ["T1", "T4"]}, index=["S000", "S001"])
        with pytest.raises(OrientationError, match="at least 3 are required"):
            assert_sample_alignment(features_x_samples, tiny, "Visit")


class TestAnalysesAgreeOnOrientation:
    """Alpha, beta and PCoA must describe the same set of samples."""

    def test_all_report_the_same_samples(self, features_x_samples, metadata):
        params = {"group_column": "Visit"}

        alpha = run_alpha_diversity(features_x_samples, metadata, params)
        beta = run_beta_diversity(features_x_samples, metadata, params)
        pcoa = run_pcoa(features_x_samples, metadata, params)

        expected = set(metadata.index)
        assert set(alpha["sample_diversity"]) == expected
        assert set(beta["distance_matrix"]) == expected
        assert set(pcoa["coordinates"]) == expected

    def test_pcoa_labels_samples_not_taxa(self, features_x_samples, metadata):
        """The exact failure seen on the Huang dataset: 44 Genus_* points."""
        pcoa = run_pcoa(features_x_samples, metadata, {"group_column": "Visit"})
        assert not any(str(k).startswith("Genus_") for k in pcoa["coordinates"])
        assert len(pcoa["group_metadata"]) == len(metadata)


class TestServiceOrientationContracts:
    """Pin the orientation each service is called with.

    These services accept *either* orientation without complaining but compute
    something different for each, so a call-site regression would silently change
    the science rather than raise. WGCNA is the clearest case: given
    features x samples it builds modules of taxa (correct); given the transpose
    it builds "modules" of samples, which is meaningless.
    """

    @pytest.fixture
    def table(self):
        rng = np.random.default_rng(3)
        return pd.DataFrame(
            rng.poisson(20, size=(12, 40)).astype(float),
            index=[f"Genus_{i}" for i in range(12)],      # features
            columns=[f"S{i:03d}" for i in range(40)],     # samples
        )

    @pytest.fixture
    def meta(self, table):
        return pd.DataFrame(
            {"grp": ["a"] * 20 + ["b"] * 20}, index=table.columns
        )

    def test_wgcna_builds_modules_of_features(self, table, meta):
        from app.services.wgcna import run_wgcna

        result = run_wgcna(table, meta)
        # 12 features in, so the network has 12 nodes -- not 40.
        assert result["statistics"]["n_features"] == len(table.index)

    def test_aldex2_is_called_with_samples_as_rows(self, table, meta):
        """run_aldex2 documents samples x features; the route transposes for it."""
        from app.services.aldex2 import run_aldex2

        result = run_aldex2(table.T, meta, group_column="grp", test_method="welch")
        assert "results_table" in result

        with pytest.raises(ValueError, match="No matching sample IDs"):
            run_aldex2(table, meta, group_column="grp", test_method="welch")

    def test_enterotype_rejects_a_degenerate_metric(self, meta):
        """Jaccard on a table where every sample shares every feature is useless."""
        from app.services.enterotype import run_enterotype

        dense = pd.DataFrame(
            np.ones((40, 12)),
            index=meta.index,
            columns=[f"Genus_{i}" for i in range(12)],
        )
        with pytest.raises(ValueError, match="All pairwise distances are zero"):
            run_enterotype(dense, meta, n_clusters=3, distance_metric="jaccard")
