"""Golden-value tests: every statistic must match a reference implementation.

The pre-existing unit tests only asserted that results were the right *shape*
(``assert 'chao1' in result.columns``, ``assert (chao1 >= 0).all()``). Those
pass just as happily when Chao1 returns 4.5e10 or when ANOSIM's R is off by a
factor of 200, which is exactly what was happening. These tests pin the numbers
against scikit-bio / statsmodels instead, so a regression in the formulas fails
the suite rather than sailing through it.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis_engine import (
    AnalysisEngine,
    adjust_pvalues,
    resolve_comparison_groups,
)

skbio = pytest.importorskip("skbio", reason="scikit-bio is the reference implementation")
from skbio.diversity.alpha import ace as sk_ace  # noqa: E402
from skbio.diversity.alpha import chao1 as sk_chao1  # noqa: E402
from skbio.diversity.alpha import pielou_e as sk_pielou  # noqa: E402
from skbio.diversity.alpha import shannon as sk_shannon  # noqa: E402
from skbio.stats.distance import DistanceMatrix  # noqa: E402
from skbio.stats.distance import anosim as sk_anosim  # noqa: E402
from skbio.stats.distance import permanova as sk_permanova  # noqa: E402
from statsmodels.stats.multitest import multipletests  # noqa: E402

TOL = 1e-9


def _as_reference_dm(dm) -> DistanceMatrix:
    """Wrap a distance-matrix DataFrame for scikit-bio.

    scikit-bio's Cython kernels require a C-contiguous array. Under pandas 3
    ``DataFrame.values`` can hand back a non-contiguous view, which surfaces as
    "ValueError: ndarray is not C-contiguous" from permanova_f_stat_sW_cy. Only
    the tests hit this -- application code builds its skbio inputs from
    ``squareform()`` output, which is already contiguous.
    """
    return DistanceMatrix(np.ascontiguousarray(dm.values), ids=[str(i) for i in dm.index])


@pytest.fixture
def engine():
    return AnalysisEngine()


@pytest.fixture
def separated_data():
    """40 taxa x 30 samples with two groups that separate perfectly."""
    rng = np.random.default_rng(0)
    counts = rng.poisson(20, size=(40, 30)).astype(float)
    counts[:5, 15:] *= 8
    df = pd.DataFrame(
        counts,
        index=[f"taxon{i}" for i in range(40)],
        columns=[f"S{i}" for i in range(30)],
    )
    groups = np.array(["A"] * 15 + ["B"] * 15)
    metadata = pd.DataFrame({"grp": groups}, index=df.columns)
    return df, metadata, groups


class TestBetaStatisticsAgainstScikitBio:
    def test_anosim_r_matches_skbio(self, engine, separated_data):
        """R must be ~1 for perfectly separated groups.

        The denominator used to be built from the number of pairwise distances
        instead of the number of samples, reporting R = 0.0046 here.
        """
        df, metadata, groups = separated_data
        dm = engine.beta_diversity(df, "braycurtis")

        ours = engine.anosim(dm, metadata, "grp", n_permutations=99)
        ref = sk_anosim(_as_reference_dm(dm), groups, permutations=99)

        assert ours["r_statistic"] == pytest.approx(ref["test statistic"], abs=TOL)
        assert ours["r_statistic"] > 0.9

    def test_permanova_pseudo_f_matches_skbio(self, engine, separated_data):
        df, metadata, groups = separated_data
        dm = engine.beta_diversity(df, "braycurtis")

        ours = engine.permanova(dm, metadata, "grp", n_permutations=99)
        ref = sk_permanova(_as_reference_dm(dm), groups, permutations=99)

        assert ours["pseudo_f"] == pytest.approx(ref["test statistic"], abs=TOL)

    def test_permanova_reports_r_squared(self, engine, separated_data):
        """R^2 = SSB/SST is the effect size normally reported alongside p."""
        df, metadata, _ = separated_data
        dm = engine.beta_diversity(df, "braycurtis")
        result = engine.permanova(dm, metadata, "grp", n_permutations=99)

        assert 0.0 <= result["r_squared"] <= 1.0
        assert result["r_squared"] == pytest.approx(result["ssb"] / result["sst"], abs=TOL)

    @pytest.mark.parametrize("method", ["permanova", "anosim"])
    def test_permutation_tests_are_reproducible(self, engine, separated_data, method):
        """A seeded RNG means the same input yields the same p-value."""
        df, metadata, _ = separated_data
        dm = engine.beta_diversity(df, "braycurtis")
        run = getattr(engine, method)

        first = run(dm, metadata, "grp", n_permutations=99)
        second = run(dm, metadata, "grp", n_permutations=99)
        assert first["pvalue"] == second["pvalue"]

    def test_nmds_stress_describes_the_returned_embedding(self, engine, separated_data):
        """Reported stress-1 must be re-derivable from the coordinates returned.

        The value used to be derived from ``sklearn.manifold.MDS.stress_``, whose
        meaning changed between scikit-learn 1.6 (raw sum of squares) and 1.9
        (already normalised). The same data therefore reported 0.087 on one
        install and 0.008 on another, and neither matched the embedding's actual
        stress-1. Recomputing it here keeps the number honest on any version.
        """
        from scipy.spatial.distance import pdist, squareform
        from sklearn.isotonic import IsotonicRegression

        df, _, _ = separated_data
        dm = engine.beta_diversity(df, "braycurtis")
        result = engine.nmds(dm, n_components=2)

        d_fit = pdist(result["coordinates"].values)
        d_obs = squareform(dm.values, checks=False)
        disparities = IsotonicRegression().fit_transform(d_obs, d_fit)
        expected = np.sqrt(np.sum((d_fit - disparities) ** 2) / np.sum(d_fit ** 2))

        assert result["stress_type"] == "kruskal_stress_1"
        assert result["stress"] == pytest.approx(expected, abs=1e-12)
        assert 0.0 <= result["stress"] <= 1.0

    def test_jaccard_is_presence_absence(self, engine, separated_data):
        """Jaccard must ignore abundance and look only at which taxa are present."""
        df, _, _ = separated_data

        identical_presence = engine.beta_diversity(df, "jaccard")
        off_diagonal = identical_presence.values[np.triu_indices(len(df.columns), k=1)]
        assert off_diagonal.max() == pytest.approx(0.0, abs=TOL)

        # Drop half the taxa from the first 15 samples -> distance of exactly 0.5.
        modified = df.copy()
        modified.iloc[20:, :15] = 0
        dm = engine.beta_diversity(modified, "jaccard")
        assert dm.iloc[0, 20] == pytest.approx(0.5, abs=TOL)

    def test_pcoa_survives_a_degenerate_distance_matrix(self, engine):
        """All-zero distances must not produce a 0-column ordination.

        Jaccard on a table where every sample carries every feature gives an
        all-zero distance matrix, hence no positive eigenvalues. The frame used
        to come back with zero columns and every downstream plot then died with
        KeyError('PC1') as an opaque 500.
        """
        flat = pd.DataFrame(
            np.ones((10, 6)),
            index=[f"t{i}" for i in range(10)],
            columns=[f"S{i}" for i in range(6)],
        )
        dm = engine.beta_diversity(flat, "jaccard")
        assert not (dm.values > 0).any(), "fixture should be degenerate"

        result = engine.pcoa(dm)
        assert list(result["samples"].columns[:2]) == ["PC1", "PC2"]
        assert result["degenerate"] is True
        assert "no information" in result["warning"]

        metadata = pd.DataFrame({"g": list("aaabbb")}, index=flat.columns)
        engine.plotly_pcoa_scatter(result, metadata, "g")  # must not raise

    def test_pcoa_unchanged_for_normal_data(self, engine, separated_data):
        """The degenerate-case padding must not perturb ordinary results."""
        df, _, _ = separated_data
        result = engine.pcoa(engine.beta_diversity(df, "braycurtis"))
        assert "degenerate" not in result
        assert result["samples"].shape[0] == len(df.columns)
        assert result["variance_explained"][0] > 0

    def test_misaligned_metadata_raises(self, engine, separated_data):
        """A transposed table shares no labels with the metadata: fail, don't guess."""
        df, metadata, _ = separated_data
        dm = engine.beta_diversity(df.T, "braycurtis")

        with pytest.raises(ValueError, match="transposed"):
            engine.permanova(dm, metadata, "grp", n_permutations=9)

    def test_single_group_raises(self, engine, separated_data):
        df, metadata, _ = separated_data
        dm = engine.beta_diversity(df, "braycurtis")
        one_group = metadata.assign(grp="A")

        with pytest.raises(ValueError, match="at least 2 groups"):
            engine.permanova(dm, one_group, "grp", n_permutations=9)


class TestAlphaDiversityAgainstScikitBio:
    @pytest.fixture
    def samples(self):
        """Three columns exercising the interesting edge cases."""
        df = pd.DataFrame(
            0, index=[f"t{i}" for i in range(12)], columns=["A", "B", "C"], dtype=float
        )
        df.loc[["t0", "t1", "t2"], "A"] = 1        # rare taxa are all singletons
        df.loc["t3", "A"] = 50
        df.loc[["t0", "t1"], "B"] = 1              # singletons and doubletons
        df.loc[["t2", "t3"], "B"] = 2
        df.loc["t4", "B"] = 30
        df.loc[["t0", "t1", "t2"], "C"] = [3, 5, 7]  # rare, none singleton
        df.loc["t5", "C"] = 40
        return df

    @pytest.mark.parametrize("column", ["A", "B", "C"])
    def test_shannon_matches_skbio(self, engine, samples, column):
        ours = engine._calculate_shannon(samples)[column]
        ref = sk_shannon(samples[column].values.astype(int), base=np.e)
        assert ours == pytest.approx(ref, abs=1e-9)

    @pytest.mark.parametrize("column", ["A", "B", "C"])
    def test_chao1_matches_skbio(self, engine, samples, column):
        ours = engine._calculate_chao1(samples)[column]
        ref = sk_chao1(samples[column].values.astype(int))
        assert ours == pytest.approx(ref, abs=1e-9)

    def test_chao1_finite_without_doubletons(self, engine, samples):
        """Sample A has 3 singletons and no doubletons.

        The old formula S_obs + F1^2 / (2*(F2 + 1e-10)) returned 4.5e10 here.
        """
        value = engine._calculate_chao1(samples)["A"]
        assert value == pytest.approx(7.0, abs=1e-9)
        assert value < 100

    @pytest.mark.parametrize("column", ["B", "C"])
    def test_ace_matches_skbio(self, engine, samples, column):
        ours = engine._calculate_ace(samples)[column]
        ref = sk_ace(samples[column].values.astype(int))
        assert ours == pytest.approx(ref, abs=1e-9)

    def test_ace_undefined_is_nan_not_a_number(self, engine, samples):
        """Coverage is 0 when every rare taxon is a singleton; skbio raises."""
        with pytest.raises(ValueError):
            sk_ace(samples["A"].values.astype(int))
        assert np.isnan(engine._calculate_ace(samples)["A"])

    @pytest.mark.parametrize("column", ["A", "B", "C"])
    def test_pielou_matches_skbio(self, engine, samples, column):
        ours = engine._calculate_pielou(samples)[column]
        ref = sk_pielou(samples[column].values.astype(int))
        assert ours == pytest.approx(ref, abs=1e-9)

    def test_pielou_undefined_for_single_taxon(self, engine):
        """ln(richness) is 0 at richness 1; the old +1e-10 guard returned +inf."""
        single = pd.DataFrame({"S0": [10] + [0] * 9}, index=[f"t{i}" for i in range(10)])
        assert np.isnan(engine._calculate_pielou(single)["S0"])


class TestMultipleTestingCorrection:
    def test_matches_statsmodels_on_unsorted_input(self):
        pvalues = np.array([0.9, 0.001, 0.04, 0.03, 0.5, 0.002])
        expected = multipletests(pvalues, method="fdr_bh")[1]
        assert np.allclose(adjust_pvalues(pvalues), expected)

    def test_adjusted_values_are_monotone_in_p(self):
        """BH q-values must be non-decreasing once sorted by raw p."""
        rng = np.random.default_rng(7)
        pvalues = rng.random(200)
        adjusted = adjust_pvalues(pvalues)
        ordered = adjusted[np.argsort(pvalues)]
        assert np.all(np.diff(ordered) >= -1e-12)

    def test_row_order_does_not_change_results(self):
        pvalues = np.array([0.9, 0.001, 0.04, 0.03, 0.5, 0.002])
        shuffled_order = np.array([3, 0, 5, 1, 4, 2])
        direct = adjust_pvalues(pvalues)[shuffled_order]
        reordered = adjust_pvalues(pvalues[shuffled_order])
        assert np.allclose(direct, reordered)

    def test_bonferroni_supported(self):
        pvalues = np.array([0.01, 0.02, 0.03])
        expected = multipletests(pvalues, method="bonferroni")[1]
        assert np.allclose(adjust_pvalues(pvalues, "bonferroni"), expected)

    def test_empty_input(self):
        assert adjust_pvalues(np.array([])).size == 0


class TestRandomForest:
    def test_runs_with_string_labels(self, engine, separated_data):
        """confusion_matrix used to be given string labels for encoded integers."""
        df, metadata, _ = separated_data
        result = engine.random_forest(df, metadata, "grp", n_estimators=25)

        assert result["confusion_matrix"]["labels"] == ["A", "B"]
        matrix = np.array(result["confusion_matrix"]["matrix"])
        assert matrix.shape == (2, 2)
        assert matrix.sum() > 0

    def test_cv_folds_bounded_by_smallest_class(self, engine, separated_data):
        """Folds follow the smallest class size, not the number of classes."""
        df, metadata, _ = separated_data
        result = engine.random_forest(df, metadata, "grp", n_estimators=25)
        assert result["cv_folds"] == 5

    def test_rejects_transposed_table(self, engine, separated_data):
        df, metadata, _ = separated_data
        with pytest.raises(ValueError, match="transposed"):
            engine.random_forest(df.T, metadata, "grp", n_estimators=10)


class TestComparisonGroupResolution:
    @pytest.fixture
    def metadata(self):
        return pd.DataFrame(
            {"Visit": ["T4", "T5", "T6", "T4", "T5", "T6"]},
            index=[f"S{i}" for i in range(6)],
        )

    def test_explicit_pair_is_honoured(self, metadata):
        assert resolve_comparison_groups(metadata, "Visit", ["T5", "T6"]) == ("T5", "T6")

    def test_reference_group_defines_direction(self, metadata):
        assert resolve_comparison_groups(metadata, "Visit", ["T4", "T6"], "T6") == ("T6", "T4")

    def test_single_group_with_reference(self, metadata):
        assert resolve_comparison_groups(metadata, "Visit", ["T6"], "T4") == ("T4", "T6")

    def test_more_than_two_groups_requires_a_choice(self, metadata):
        """Silently comparing the first two of seven timepoints is not acceptable."""
        with pytest.raises(ValueError, match="pairwise testing needs exactly 2"):
            resolve_comparison_groups(metadata, "Visit", None, None)

    def test_unknown_group_is_rejected(self, metadata):
        with pytest.raises(ValueError, match="not present in metadata column"):
            resolve_comparison_groups(metadata, "Visit", ["T4", "T99"])

    def test_two_group_column_is_order_independent(self):
        """Fold-change direction must not depend on metadata row order."""
        forward = pd.DataFrame({"g": ["ctrl", "case"]}, index=["S0", "S1"])
        reverse = pd.DataFrame({"g": ["case", "ctrl"]}, index=["S0", "S1"])
        assert resolve_comparison_groups(forward, "g") == resolve_comparison_groups(reverse, "g")
