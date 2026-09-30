"""Regression tests for defects found by re-checking platform statistics
against reference implementations (thesis Chapter 5, Table 5.3).

Each test pins behaviour to an independent reference (scikit-bio, SciPy) or to
a constructed case whose correct answer is known, rather than to the shape of
the output.
"""
import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.spatial import procrustes as sp_procrustes
from scipy.spatial.distance import pdist, squareform

skbio = pytest.importorskip("skbio")
from skbio import DistanceMatrix  # noqa: E402
from skbio.stats.distance import mantel as sk_mantel  # noqa: E402

from app.services.analysis_engine import AnalysisEngine  # noqa: E402
from app.services.cross_omics import (  # noqa: E402
    mantel_test,
    procrustes_analysis,
    run_cross_omics_analysis,
    run_mantel,
    run_procrustes,
)
from app.services.paired_differential_test import run_paired_differential_test  # noqa: E402
from app.services.study_design import detect_subject_column, detect_time_column  # noqa: E402


def _tables(n_samples=40, seed=0, coupling=0.6):
    """Two feature tables (features x samples) sharing a latent gradient."""
    rng = np.random.default_rng(seed)
    latent = rng.normal(size=n_samples)
    mb = rng.poisson(np.exp(2 + np.outer(rng.normal(size=25), latent) * 0.4)).astype(float) + 1
    met = np.outer(rng.normal(size=30), latent) * coupling + rng.normal(size=(30, n_samples)) + 10
    cols = [f"S{i}" for i in range(n_samples)]
    return (pd.DataFrame(mb, index=[f"t{i}" for i in range(25)], columns=cols),
            pd.DataFrame(met, index=[f"m{i}" for i in range(30)], columns=cols))


# ─────────────────────────────── Mantel

class TestMantel:
    def test_matches_scikit_bio(self):
        mb, met = _tables()
        d1 = squareform(pdist(mb.T, "braycurtis"))
        d2 = squareform(pdist(met.T, "braycurtis"))
        ours = mantel_test(d1, d2, n_permutations=199, random_seed=3)
        ids = [str(i) for i in range(len(d1))]
        r, p, _ = sk_mantel(DistanceMatrix(d1, ids), DistanceMatrix(d2, ids), permutations=199, seed=3)
        assert ours["correlation"] == pytest.approx(r, abs=1e-12)
        assert ours["p_value"] == pytest.approx(p, abs=1e-12)

    def test_flattened_vectors_are_rejected(self):
        """Permuting individual distances is invalid; the old API accepted it."""
        with pytest.raises(ValueError, match="square distance matrices"):
            mantel_test(np.arange(10.0), np.arange(10.0))

    def test_null_uses_sample_labels(self):
        """With sample-level structure (per-sample scale), shuffling distances
        gives a null ~4-5x too narrow; label permutation does not."""
        rng = np.random.default_rng(0)
        n = 40
        X = rng.normal(size=(n, 10)) * rng.lognormal(0, 1, size=(n, 1))
        Y = rng.normal(size=(n, 10)) * rng.lognormal(0, 1, size=(n, 1))
        d1, d2 = squareform(pdist(X)), squareform(pdist(Y))
        iu = np.triu_indices(n, 1)
        perm_rng = np.random.default_rng(1)
        label_null, elem_null = [], []
        for _ in range(300):
            pm = perm_rng.permutation(n)
            label_null.append(stats.pearsonr(d1[iu], d2[np.ix_(pm, pm)][iu])[0])
            elem_null.append(stats.pearsonr(d1[iu], d2[iu][perm_rng.permutation(len(iu[0]))])[0])
        assert np.std(label_null) > 2.5 * np.std(elem_null)
        mb, met = _tables()
        res = run_mantel(mb, met, n_permutations=99)
        assert res["permutation_scheme"].startswith("sample labels")


# ─────────────────────────────── Procrustes

class TestProcrustes:
    def test_matches_scipy_and_is_bounded(self):
        rng = np.random.default_rng(0)
        X, Y = rng.normal(size=(50, 2)), rng.normal(size=(50, 2))
        ours = procrustes_analysis(X, Y, n_permutations=0)
        _, _, disparity = sp_procrustes(X, Y)
        assert ours["m2"] == pytest.approx(disparity, abs=1e-12)
        assert 0.0 <= ours["m2"] <= 1.0
        assert ours["procrustes_r"] == pytest.approx(np.sqrt(1 - disparity), abs=1e-12)

    def test_rotated_scaled_copy_fits_perfectly(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(30, 2))
        theta = 0.7
        R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        ours = procrustes_analysis(X, 3.0 * X @ R + 5.0, n_permutations=99)
        assert ours["m2"] == pytest.approx(0.0, abs=1e-10)
        assert ours["pvalue"] == pytest.approx(1 / 100)

    def test_unrelated_configurations_are_not_significant(self):
        rng = np.random.default_rng(2)
        ours = procrustes_analysis(rng.normal(size=(40, 2)), rng.normal(size=(40, 2)), n_permutations=199)
        assert ours["m2"] > 0.8
        assert ours["pvalue"] > 0.05

    def test_pcoa_option_really_uses_bray_curtis_pcoa(self):
        mb, met = _tables()
        res = run_procrustes(mb, met, method="pcoa", n_permutations=0)
        assert res["ordination"]["table_1"] == "PCoA of braycurtis distances"
        assert res["ordination"]["table_2"] == "PCA of z-scored features"
        from skbio.stats.ordination import pcoa
        from sklearn.decomposition import PCA
        pc = pcoa(DistanceMatrix(squareform(pdist(mb.T.values, "braycurtis"))), number_of_dimensions=2).samples.values
        zs = (met.T - met.T.mean()) / (met.T.std() + 1e-10)
        _, _, disparity = sp_procrustes(pc[:, :2], PCA(2).fit_transform(zs))
        assert res["m2"] == pytest.approx(disparity, abs=1e-8)

    def test_old_behaviour_available_under_honest_name(self):
        mb, met = _tables()
        res = run_procrustes(mb, met, method="pca", n_permutations=0)
        assert res["ordination"]["table_1"] == "PCA of z-scored features"

    def test_no_fabricated_second_table(self):
        mb, _ = _tables()
        with pytest.raises(ValueError, match="second omics table"):
            run_cross_omics_analysis(mb, None, None, {"analysis_type": "procrustes"})


# ─────────────────────────────── PERMANOVA with repeated measures

def _repeated_design(effect_between=0.0, n_subjects=4, per_subject=6, seed=0):
    """Each subject has a tight cluster of samples far from other subjects."""
    rng = np.random.default_rng(seed)
    rows, meta = [], []
    for s in range(n_subjects):
        centre = rng.normal(scale=5, size=10)
        for v in range(per_subject):
            rows.append(centre + rng.normal(scale=0.2, size=10))
            meta.append({"sample": f"H{s}_{v}", "Host_ID": f"H{s}", "Visit": f"V{v}",
                         "Group": "A" if s < n_subjects // 2 else "B"})
    meta = pd.DataFrame(meta).set_index("sample")
    X = np.array(rows)
    dm = pd.DataFrame(squareform(pdist(X)), index=meta.index, columns=meta.index)
    return dm, meta


class TestPermanovaRepeatedMeasures:
    def test_between_subject_factor_is_tested_on_subjects(self):
        """4 subjects (2 per group) allow only 3 distinct splits, so an honest
        P value cannot be small; free sample permutation reports ~0.001."""
        dm, meta = _repeated_design()
        eng = AnalysisEngine()
        free = eng.permanova(dm, meta, "Group", n_permutations=999)
        between = eng.permanova(dm, meta, "Group", n_permutations=999, subject_var="Host_ID")
        assert between["permutation_scheme"] == "between_subject"
        assert between["pseudo_f"] == pytest.approx(free["pseudo_f"])
        assert free["pvalue"] <= 0.01
        assert between["pvalue"] >= 0.2

    def test_within_subject_factor_permutes_within_subjects(self):
        dm, meta = _repeated_design()
        eng = AnalysisEngine()
        res = eng.permanova(dm, meta, "Visit", n_permutations=199, subject_var="Host_ID")
        assert res["permutation_scheme"] == "within_subject"
        free = eng.permanova(dm, meta, "Visit", n_permutations=199)
        assert res["pseudo_f"] == pytest.approx(free["pseudo_f"])

    def test_warns_when_repeated_measures_are_ignored(self):
        dm, meta = _repeated_design()
        res = AnalysisEngine().permanova(dm, meta, "Group", n_permutations=99)
        assert res["permutation_scheme"] == "free"
        assert any("Host_ID" in w for w in res["warnings"])

    def test_unknown_subject_column_raises(self):
        dm, meta = _repeated_design()
        with pytest.raises(ValueError, match="subject column"):
            AnalysisEngine().permanova(dm, meta, "Group", subject_var="nope")


class TestStudyDesignDetection:
    def test_detects_host_id_not_visit_or_group(self):
        _, meta = _repeated_design()
        assert detect_subject_column(meta) == "Host_ID"
        assert detect_time_column(meta, "Host_ID") == "Visit"

    def test_no_subject_column_for_independent_samples(self):
        meta = pd.DataFrame({"SampleID": [f"S{i}" for i in range(10)], "Group": ["A", "B"] * 5})
        assert detect_subject_column(meta) is None


# ─────────────────────────────── Paired differential test

def _paired_data(seed=0):
    rng = np.random.default_rng(seed)
    subjects = [f"P{i}" for i in range(12)]
    meta_rows, cols = [], {}
    for subj in subjects:
        base = rng.poisson(50, size=8).astype(float) + 1
        for visit, shift in (("T0", 1.0), ("T1", 1.0), ("T2", 4.0)):
            if subj == "P11" and visit == "T2":
                continue  # incomplete pair: must be dropped, not crash
            prof = base.copy()
            prof[0] *= shift
            sid = f"{subj}_{visit}"
            cols[sid] = rng.poisson(prof).astype(float) + 1
            meta_rows.append({"sample": sid, "Subject": subj, "Visit": visit})
    df = pd.DataFrame(cols, index=[f"f{i}" for i in range(8)])
    meta = pd.DataFrame(meta_rows).set_index("sample")
    return df, meta


class TestPairedDifferential:
    def test_runs_on_features_by_samples_input(self):
        """The shipped module raised IndexError on real input (orientation bug)."""
        df, meta = _paired_data()
        res = run_paired_differential_test(df, meta, "Visit", "Subject", groups=["T0", "T2"])
        st = res["statistics"]
        assert st["groups"] == ["T0", "T2"]
        assert st["n_pairs"] == 11
        assert st["n_subjects_dropped_incomplete"] == 1
        assert "f0" in set(res["significant_features"]["feature"])

    def test_matches_scipy_wilcoxon_on_clr(self):
        df, meta = _paired_data()
        res = run_paired_differential_test(df, meta, "Visit", "Subject", groups=["T0", "T2"])
        sub = meta[meta.Visit.isin(["T0", "T2"])]
        sub = sub[sub.Subject.isin(sub.Subject.value_counts()[lambda c: c == 2].index)].sort_values("Subject")
        X = df[sub.index].T + 0.5
        clr = np.log(X).sub(np.log(X).mean(axis=1), axis=0)
        a = clr.loc[sub.index[sub.Visit == "T0"], "f3"].to_numpy()
        b = clr.loc[sub.index[sub.Visit == "T2"], "f3"].to_numpy()
        expected = stats.wilcoxon(a, b).pvalue
        got = res["results"].set_index("feature").loc["f3", "pvalue"]
        assert got == pytest.approx(expected, abs=1e-12)

    def test_more_than_two_levels_needs_groups(self):
        df, meta = _paired_data()
        with pytest.raises(ValueError, match="groups="):
            run_paired_differential_test(df, meta, "Visit", "Subject")

    def test_aldex2_without_r_refuses_unless_opted_in(self):
        from app.services import paired_differential_test as mod
        if mod.R_AVAILABLE:
            pytest.skip("R is available; the refusal path is not exercised")
        df, meta = _paired_data()
        with pytest.raises(ValueError, match="ALDEx2"):
            run_paired_differential_test(df, meta, "Visit", "Subject", method="paired_aldex2", groups=["T0", "T2"])
        res = run_paired_differential_test(df, meta, "Visit", "Subject", method="paired_aldex2",
                                           groups=["T0", "T2"], allow_approximation=True)
        assert res["statistics"]["engine"] == "python-approx::paired_aldex2"


# ─────────────────────────────── Agent cross-correlation wiring

class TestAgentCrossCorrelation:
    def test_correlates_taxa_with_metabolites(self):
        from app.agent.executor import _get_module_function
        mb, met = _tables()
        out = _get_module_function("cross_correlation")(df=mb, df2=met, metadata_df=None)
        st = out["statistics"]
        assert st["n_genera"] == mb.shape[0]
        assert st["n_metabolites"] == met.shape[0]
        assert st["n_pairs_tested"] == mb.shape[0] * met.shape[0]

    def test_without_metabolome_fails_instead_of_answering_another_question(self):
        from app.agent.executor import _get_module_function
        mb, _ = _tables()
        with pytest.raises(ValueError, match="metabolome"):
            _get_module_function("cross_correlation")(df=mb, df2=None, metadata_df=None)
