"""Tests for strain_analyzer.py."""
import numpy as np
import pandas as pd
import pytest

from app.services.strain_analyzer import (
    StrainAnalyzer,
    run_ani_matrix,
    run_strain_pcoa,
    run_strain_profile,
)


class TestStrainRichness:
    """Test strain richness calculation."""

    def test_strain_richness(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_richness(sample_strain_data)
        assert 'sample_id' in result.columns
        assert 'strain_richness' in result.columns
        assert len(result) == sample_strain_data['sample_id'].nunique()
        assert (result['strain_richness'] > 0).all()

    def test_strain_richness_by_species(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_richness(sample_strain_data, species='Escherichia_coli')
        assert 'sample_id' in result.columns
        assert len(result) <= sample_strain_data['sample_id'].nunique()

    def test_strain_richness_empty(self):
        analyzer = StrainAnalyzer()
        df = pd.DataFrame(columns=['sample_id', 'species', 'strain', 'abundance'])
        result = analyzer.strain_richness(df)
        assert result.empty


class TestStrainAlphaDiversity:
    """Test strain-level alpha diversity."""

    def test_strain_shannon(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_alpha_diversity(sample_strain_data, metric='shannon')
        assert 'sample_id' in result.columns
        assert 'shannon_diversity' in result.columns
        assert len(result) == sample_strain_data['sample_id'].nunique()

    def test_strain_simpson(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_alpha_diversity(sample_strain_data, metric='simpson')
        assert 'simpson_diversity' in result.columns

    def test_strain_observed(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_alpha_diversity(sample_strain_data, metric='observed')
        assert 'observed_diversity' in result.columns

    def test_strain_alpha_empty(self):
        analyzer = StrainAnalyzer()
        df = pd.DataFrame(columns=['sample_id', 'species', 'strain', 'abundance'])
        result = analyzer.strain_alpha_diversity(df, metric='shannon')
        assert result.empty


class TestStrainBetaDiversity:
    """Test strain-level beta diversity."""

    def test_strain_beta_braycurtis(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        dist = analyzer.strain_beta_diversity(sample_strain_data, distance='braycurtis')
        assert dist.shape[0] == sample_strain_data['sample_id'].nunique()
        assert dist.shape[1] == sample_strain_data['sample_id'].nunique()

    def test_strain_beta_jaccard(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        dist = analyzer.strain_beta_diversity(sample_strain_data, distance='jaccard')
        assert dist.shape[0] == sample_strain_data['sample_id'].nunique()

    def test_strain_beta_euclidean(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        dist = analyzer.strain_beta_diversity(sample_strain_data, distance='euclidean')
        assert dist.shape[0] == sample_strain_data['sample_id'].nunique()

    def test_strain_beta_by_species(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        dist = analyzer.strain_beta_diversity(
            sample_strain_data, distance='braycurtis', species='Escherichia_coli'
        )
        # May be smaller than all samples if not all have this species
        assert dist.shape[0] <= sample_strain_data['sample_id'].nunique()

    def test_strain_beta_empty(self):
        analyzer = StrainAnalyzer()
        df = pd.DataFrame(columns=['sample_id', 'species', 'strain', 'abundance'])
        dist = analyzer.strain_beta_diversity(df, distance='braycurtis')
        assert dist.empty


class TestStrainDifferential:
    """Test strain differential abundance."""

    def test_strain_differential(self, sample_strain_data, sample_metadata):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_differential(
            sample_strain_data, sample_metadata, 'Treatment'
        )
        assert 'strain' in result.columns
        assert 'log2FC' in result.columns
        assert 'pvalue' in result.columns
        assert 'padj' in result.columns

    def test_strain_differential_not_two_groups(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        metadata = pd.DataFrame({
            'Group': ['A'] * 10
        }, index=[f'Sample_{i:02d}' for i in range(1, 11)])
        with pytest.raises(ValueError, match='requires exactly 2 groups'):
            analyzer.strain_differential(sample_strain_data, metadata, 'Group')


class TestDominanceIndex:
    """Test strain dominance index."""

    def test_strain_dominance_index(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        result = analyzer.strain_dominance_index(sample_strain_data)
        assert 'sample_id' in result.columns
        assert 'species' in result.columns
        assert 'max_strain' in result.columns
        assert 'dominance_index' in result.columns
        assert (result['dominance_index'] >= 0).all() and (result['dominance_index'] <= 1).all()

    def test_strain_dominance_index_no_species(self):
        analyzer = StrainAnalyzer()
        df = pd.DataFrame({'strain': ['A'], 'abundance': [1]})
        result = analyzer.strain_dominance_index(df)
        assert result.empty


class TestReplacementScore:
    """Test strain replacement score."""

    def test_strain_replacement_score(self, sample_strain_data, sample_metadata):
        analyzer = StrainAnalyzer()
        score = analyzer.strain_replacement_score(
            sample_strain_data, sample_metadata, 'Treatment', 'Control', 'Treatment'
        )
        assert 0.0 <= score <= 1.0

    def test_strain_replacement_score_no_strains(self, sample_metadata):
        analyzer = StrainAnalyzer()
        df = pd.DataFrame(columns=['sample_id', 'species', 'strain', 'abundance'])
        score = analyzer.strain_replacement_score(df, sample_metadata, 'Treatment', 'Control', 'Treatment')
        assert score == 0.0


class TestPlotlyGenerators:
    """Test strain Plotly generators."""

    def test_plotly_strain_composition(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        plot = analyzer.plotly_strain_composition(sample_strain_data, 'Escherichia_coli')
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_strain_heatmap(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        plot = analyzer.plotly_strain_heatmap(sample_strain_data)
        assert 'data' in plot
        assert 'layout' in plot

    def test_plotly_strain_heatmap_by_species(self, sample_strain_data):
        analyzer = StrainAnalyzer()
        plot = analyzer.plotly_strain_heatmap(sample_strain_data, species='Escherichia_coli')
        assert 'data' in plot


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_run_strain_profile(self, sample_strain_data):
        result, count = run_strain_profile(sample_strain_data, 'Escherichia_coli')
        assert 'strain_profile' in result
        assert count > 0

    def test_run_ani_matrix(self, sample_strain_data):
        result = run_ani_matrix(sample_strain_data, 'Escherichia_coli')
        assert 'ani_matrix' in result
        assert 'distance_matrix' in result
        assert 'strains' in result

    def test_run_strain_pcoa(self, sample_strain_data):
        result = run_strain_pcoa(sample_strain_data, 'Escherichia_coli')
        assert 'coordinates' in result
        assert 'eigenvalues' in result
