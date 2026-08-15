"""Tests for analysis_engine.py."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis_engine import AnalysisEngine, run_alpha_diversity, run_beta_diversity


class TestAlphaDiversity:
    """Test alpha diversity calculations."""

    def test_alpha_shannon(self, sample_feature_table):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['shannon'])
        assert 'shannon' in result.columns
        assert len(result) == len(sample_feature_table.columns)
        assert (result['shannon'] >= 0).all()

    def test_alpha_simpson(self, sample_feature_table):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['simpson'])
        assert 'simpson' in result.columns
        assert (result['simpson'] >= 0).all() and (result['simpson'] <= 1).all()

    def test_alpha_chao1(self, sample_feature_table):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['chao1'])
        assert 'chao1' in result.columns
        assert (result['chao1'] >= 0).all()

    def test_alpha_ace(self, sample_feature_table):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['ace'])
        assert 'ace' in result.columns
        assert (result['ace'] >= 0).all()

    def test_alpha_observed(self, sample_feature_table):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['observed'])
        assert 'observed' in result.columns
        assert (result['observed'] >= 0).all()

    def test_alpha_pielou(self, sample_feature_table):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['pielou'])
        assert 'pielou' in result.columns

    def test_alpha_all_six(self, sample_feature_table):
        engine = AnalysisEngine()
        metrics = ['shannon', 'simpson', 'chao1', 'ace', 'observed', 'pielou']
        result = engine.alpha_diversity(sample_feature_table, metrics=metrics)
        assert list(result.columns) == metrics
        assert len(result) == 10

    def test_alpha_unknown_metric(self, sample_feature_table, caplog):
        engine = AnalysisEngine()
        result = engine.alpha_diversity(sample_feature_table, metrics=['unknown'])
        assert 'unknown' not in result.columns

    def test_convenience_function(self, sample_feature_table, sample_metadata):
        result = run_alpha_diversity(
            sample_feature_table, sample_metadata,
            parameters={'indices': ['shannon', 'observed'], 'group_column': 'Treatment'}
        )
        assert 'sample_diversity' in result
        assert 'group_statistics' in result


class TestBetaDiversity:
    """Test beta diversity calculations."""

    def test_beta_braycurtis(self, sample_feature_table):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        assert dist.shape == (10, 10)
        assert (dist >= 0).all().all()
        np.testing.assert_almost_equal(np.diag(dist.values), np.zeros(10), decimal=5)

    def test_beta_jaccard(self, sample_feature_table):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='jaccard')
        assert dist.shape == (10, 10)
        assert (dist >= 0).all().all()

    def test_beta_euclidean(self, sample_feature_table):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='euclidean')
        assert dist.shape == (10, 10)

    def test_beta_manhattan(self, sample_feature_table):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='manhattan')
        assert dist.shape == (10, 10)

    def test_convenience_function(self, sample_feature_table, sample_metadata):
        result = run_beta_diversity(
            sample_feature_table, sample_metadata,
            parameters={'metric': 'braycurtis', 'group_column': 'Treatment'}
        )
        assert 'distance_matrix' in result


class TestPCoA:
    """Test PCoA ordination."""

    def test_pcoa(self, sample_feature_table):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        pcoa = engine.pcoa(dist)
        assert 'eigenvalues' in pcoa
        assert 'samples' in pcoa
        assert 'variance_explained' in pcoa
        assert len(pcoa['eigenvalues']) > 0
        assert pcoa['samples'].shape[0] == 10


class TestNMDS:
    """Test NMDS ordination."""

    def test_nmds(self, sample_feature_table):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        nmds = engine.nmds(dist, n_components=2)
        assert 'coordinates' in nmds
        assert 'stress' in nmds
        assert nmds['coordinates'].shape == (10, 2)
        assert nmds['stress'] >= 0


class TestDifferentialAnalysis:
    """Test differential abundance analysis."""

    def test_differential_ttest(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        result = engine.differential_ttest(
            sample_feature_table, sample_metadata, 'Treatment', 'Control', 'Treatment'
        )
        assert 'feature' in result.columns
        assert 'log2FC' in result.columns
        assert 'pvalue' in result.columns
        assert 'padj' in result.columns

    def test_differential_wilcoxon(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        result = engine.differential_wilcoxon(
            sample_feature_table, sample_metadata, 'Treatment', 'Control', 'Treatment'
        )
        assert 'feature' in result.columns
        assert 'pvalue' in result.columns
        assert 'padj' in result.columns

    def test_differential_anova(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        result = engine.differential_anova(sample_feature_table, sample_metadata, 'Treatment')
        assert 'feature' in result.columns
        assert 'pvalue' in result.columns


class TestPERMANOVA:
    """Test PERMANOVA."""

    def test_permanova(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        result = engine.permanova(dist, sample_metadata, 'Treatment', n_permutations=99)
        assert 'pseudo_f' in result
        assert 'pvalue' in result
        assert 'n_permutations' in result

    def test_permanova_single_group(self, sample_feature_table, sample_metadata):
        """A single group is a failure, not a result.

        This used to return ``{'error': ...}``, which every endpoint then saved
        and reported as ``status='completed'`` with HTTP 201.
        """
        import pytest

        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        meta = sample_metadata.copy()
        meta['Treatment'] = 'A'
        with pytest.raises(ValueError, match='at least 2 groups'):
            engine.permanova(dist, meta, 'Treatment', n_permutations=99)


class TestANOSIM:
    """Test ANOSIM."""

    def test_anosim(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        result = engine.anosim(dist, sample_metadata, 'Treatment', n_permutations=99)
        assert 'r_statistic' in result
        assert 'pvalue' in result
        assert 'n_permutations' in result

    def test_anosim_single_group(self, sample_feature_table, sample_metadata):
        """See test_permanova_single_group: failures must raise."""
        import pytest

        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        meta = sample_metadata.copy()
        meta['Treatment'] = 'A'
        with pytest.raises(ValueError, match='at least 2 groups'):
            engine.anosim(dist, meta, 'Treatment', n_permutations=99)


class TestRandomForest:
    """Test Random Forest classification."""

    def test_random_forest(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        result = engine.random_forest(
            sample_feature_table, sample_metadata, 'Treatment', n_estimators=50
        )
        assert 'accuracy' in result
        assert 'feature_importance' in result
        assert 'cv_mean_accuracy' in result
        assert len(result['feature_importance']) > 0


class TestPlotlyGenerators:
    """Test Plotly chart generation."""

    def test_plotly_alpha_boxplot(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        alpha = engine.alpha_diversity(sample_feature_table, metrics=['shannon'])
        plot = engine.plotly_alpha_boxplot(alpha, sample_metadata, 'Treatment', 'shannon')
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_pcoa_scatter(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        dist = engine.beta_diversity(sample_feature_table, distance='braycurtis')
        pcoa = engine.pcoa(dist)
        plot = engine.plotly_pcoa_scatter(pcoa, sample_metadata, 'Treatment')
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_heatmap(self, sample_feature_table):
        engine = AnalysisEngine()
        plot = engine.plotly_heatmap(sample_feature_table)
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_stacked_bar(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        plot = engine.plotly_stacked_bar(sample_feature_table, sample_metadata, 'Treatment')
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_volcano(self, sample_feature_table, sample_metadata):
        engine = AnalysisEngine()
        diff = engine.differential_ttest(
            sample_feature_table, sample_metadata, 'Treatment', 'Control', 'Treatment'
        )
        plot = engine.plotly_volcano(diff)
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_library_size(self, sample_feature_table):
        engine = AnalysisEngine()
        plot = engine.plotly_library_size(sample_feature_table)
        assert 'data' in plot
        assert 'layout' in plot
