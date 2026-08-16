"""Cross-site/cross-omics statistics (Zhang et al. 2026 framework)."""
import numpy as np
import pandas as pd
import pytest

from app.services.cross_site_omics import (
    db_permanova,
    cross_site_explained_variance,
    cross_omics_gbdt_screen,
    cross_site_correlation_network,
    cross_site_concordance,
)

RNG = np.random.default_rng(7)
N = 60


def _frame(data, prefix_rows="S", cols=None):
    return pd.DataFrame(data, index=[f"{prefix_rows}{i}" for i in range(len(data))],
                        columns=cols)


class TestDbPermanova:
    def test_strong_predictor_detected(self):
        x = RNG.normal(size=N)
        # target distance fully driven by x
        target = _frame(np.column_stack([x, x * 0.5 + RNG.normal(scale=0.01, size=N)]),
                        cols=["t1", "t2"])
        from app.services.cross_site_omics import _euclidean_dist
        res = db_permanova(_frame(x.reshape(-1, 1), cols=["driver"]), _euclidean_dist(target),
                           n_perm=199)
        term = res["terms"][0]
        assert term["pvalue"] < 0.05
        assert term["r2"] > 0.5

    def test_noise_predictor_not_significant(self):
        x = RNG.normal(size=N)
        target = _frame(RNG.normal(size=(N, 3)), cols=["a", "b", "c"])
        from app.services.cross_site_omics import _euclidean_dist
        res = db_permanova(_frame(x.reshape(-1, 1), cols=["noise"]), _euclidean_dist(target),
                           n_perm=199)
        assert res["terms"][0]["pvalue"] > 0.05


class TestCrossSiteExplainedVariance:
    def test_signal_site_outranks_noise_site(self):
        driver = RNG.normal(size=N)
        target = _frame(np.column_stack([driver + RNG.normal(scale=0.3, size=N),
                                         RNG.normal(size=N)]), cols=["m1", "m2"])
        sites = {
            "gut": _frame(np.column_stack([driver, RNG.normal(size=N)]), cols=["g1", "g2"]),
            "oral": _frame(RNG.normal(size=(N, 2)), cols=["o1", "o2"]),
        }
        out = cross_site_explained_variance(sites, target, n_perm=99)
        gut = out["sites"]["gut"]
        oral = out["sites"]["oral"]
        assert gut["n_significant"] >= 1
        assert gut["cumulative_r2"] > oral["cumulative_r2"]
        sig_feats = [d["feature"] for d in gut["per_feature"] if d["pvalue"] < 0.05]
        assert "g1" in sig_feats


class TestGbdtScreen:
    def test_recovers_driver_feature(self):
        x1 = RNG.normal(size=N)
        x2 = RNG.normal(size=N)
        # nonlinear response: GBDT should capture it
        y = (x1 > 0).astype(float) * 2.0 + RNG.normal(scale=0.2, size=N)
        feats = _frame(np.column_stack([x1, x2]), cols=["driver", "noise"])
        target = _frame(y.reshape(-1, 1), cols=["met1"])
        out = cross_omics_gbdt_screen(feats, target, n_bootstrap=4, cv_folds=3, seed=1)
        assert out["n_targets_modelled"] == 1
        res = out["results"][0]
        assert res["mean_r2"] > 0.3
        top_feats = [f["feature"] for f in res["top_features"]]
        assert "driver" in top_feats

    def test_constant_target_skipped(self):
        feats = _frame(RNG.normal(size=(N, 2)), cols=["a", "b"])
        target = _frame(np.ones((N, 1)), cols=["const"])
        out = cross_omics_gbdt_screen(feats, target, n_bootstrap=2, cv_folds=3)
        assert out["n_targets_modelled"] == 0


class TestCorrelationNetwork:
    def test_shared_target_detected(self):
        g = RNG.normal(size=N)
        o = g * 0.8 + RNG.normal(scale=0.2, size=N)   # oral correlates with gut
        met = g * 0.9 + RNG.normal(scale=0.1, size=N)  # metabolite driven by both
        sites = {
            "gut": _frame(g.reshape(-1, 1), cols=["Genu"]),
            "oral": _frame(o.reshape(-1, 1), cols=["Ora"]),
        }
        target = _frame(met.reshape(-1, 1), cols=["Met1"])
        out = cross_site_correlation_network(sites, target)
        assert out["n_edges"] == 2
        assert out["shared_targets"][0]["target"] == "Met1"
        assert out["shared_targets"][0]["n_sites"] == 2
        assert out["site_hubs"]["gut"][0]["feature"] == "Genu"

    def test_no_signal_no_edges(self):
        sites = {"gut": _frame(RNG.normal(size=(N, 2)), cols=["a", "b"])}
        target = _frame(RNG.normal(size=(N, 2)), cols=["m1", "m2"])
        out = cross_site_correlation_network(sites, target, r_threshold=0.9)
        assert out["n_edges"] == 0


class TestConcordance:
    def _metadata(self, n=N):
        grp = ["ctrl"] * (n // 2) + ["disease"] * (n // 2)
        return pd.DataFrame({"group": grp}, index=[f"S{i}" for i in range(n)])

    def test_concordant_feature_flagged(self):
        half = N // 2
        up = np.concatenate([RNG.normal(0, 0.5, half), RNG.normal(2, 0.5, half)])
        tables = {
            "gut": _frame(up.reshape(-1, 1), cols=["F1"]),
            "oral": _frame((up * 1.2).reshape(-1, 1), cols=["F1"]),
        }
        out = cross_site_concordance(tables, self._metadata(), "group", min_sites=2)
        assert len(out["concordant_features"]) == 1
        c = out["concordant_features"][0]
        assert c["feature"] == "F1"
        assert c["concordant_direction"] is True
        assert set(c["layers"]) == {"gut", "oral"}

    def test_discordant_direction_reported_not_concordant(self):
        half = N // 2
        up = np.concatenate([RNG.normal(0, 0.5, half), RNG.normal(2, 0.5, half)])
        tables = {
            "gut": _frame(up.reshape(-1, 1), cols=["F1"]),
            "oral": _frame((-up).reshape(-1, 1), cols=["F1"]),
        }
        out = cross_site_concordance(tables, self._metadata(), "group", min_sites=2)
        assert out["concordant_features"][0]["concordant_direction"] is False

    def test_min_sites_filters(self):
        half = N // 2
        up = np.concatenate([RNG.normal(0, 0.5, half), RNG.normal(2, 0.5, half)])
        noise = RNG.normal(size=N)
        tables = {
            "gut": _frame(up.reshape(-1, 1), cols=["F1"]),
            "oral": _frame(noise.reshape(-1, 1), cols=["F1"]),
        }
        out = cross_site_concordance(tables, self._metadata(), "group", min_sites=2)
        assert out["concordant_features"] == []

    def test_requires_two_groups(self):
        md = pd.DataFrame({"group": ["a"] * 5}, index=[f"S{i}" for i in range(5)])
        tables = {"gut": _frame(RNG.normal(size=(5, 1)), cols=["x"])}
        with pytest.raises(ValueError, match="exactly 2 levels"):
            cross_site_concordance(tables, md, "group")


class TestExecutorWiring:
    """The four cross-site modules must be registered and executable through
    the agent executor's module-function table."""

    def _session_data(self):
        n_subj, visits = 20, 2
        rows, meta = [], []
        for s in range(n_subj):
            for site in ("gut", "oral"):
                for v in range(visits):
                    rows.append(f"S{s}_{site}_{v}")
                    meta.append({"subject": f"subj{s}", "site": site,
                                 "group": "case" if s % 2 else "ctrl"})
        driver = RNG.normal(size=n_subj)
        mb = np.column_stack([
            np.repeat(driver, 4) + RNG.normal(scale=0.2, size=len(rows)),
            RNG.normal(size=len(rows)),
        ])
        met = np.column_stack([
            np.repeat(driver, 2) + RNG.normal(scale=0.3, size=n_subj * 2),
        ])
        met_rows = [f"S{s}_plasma_{v}" for s in range(n_subj) for v in range(visits)]
        met_meta = pd.DataFrame(
            {"subject": [f"subj{s}" for s in range(n_subj) for v in range(visits)],
             "group": ["case" if s % 2 else "ctrl" for s in range(n_subj) for v in range(visits)]},
            index=met_rows)
        microbiome = pd.DataFrame(mb.T, columns=rows, index=["gA", "gB"])     # features x samples
        metabolome = pd.DataFrame(met.T, columns=met_rows, index=["m1"])
        metadata = pd.concat([
            pd.DataFrame(meta, index=rows),
            met_meta,
        ])
        return microbiome, metabolome, metadata

    def test_modules_registered(self):
        from app.agent.module_registry import MODULE_REGISTRY
        for m in ("cross_site_permanova", "cross_omics_gbdt",
                  "cross_site_network", "cross_site_concordance"):
            assert m in MODULE_REGISTRY, m

    def test_executor_functions_exist(self):
        from app.agent.executor import _get_module_function
        for m in ("cross_site_permanova", "cross_omics_gbdt",
                  "cross_site_network", "cross_site_concordance"):
            assert callable(_get_module_function(m)), m

    def test_concordance_end_to_end(self):
        from app.agent.executor import _get_module_function
        mb, met, md = self._session_data()
        fn = _get_module_function("cross_site_concordance")
        out = fn(mb, df2=met, metadata_df=md, group_column="group", min_sites=2)
        assert "concordant_features" in out

    def test_network_end_to_end(self):
        from app.agent.executor import _get_module_function
        mb, met, md = self._session_data()
        fn = _get_module_function("cross_site_network")
        out = fn(mb, df2=met, metadata_df=md, r_threshold=0.3)
        assert "site_hubs" in out and "shared_targets" in out

    def test_permanova_end_to_end(self):
        from app.agent.executor import _get_module_function
        mb, met, md = self._session_data()
        fn = _get_module_function("cross_site_permanova")
        out = fn(mb, df2=met, metadata_df=md, n_permutations=49)
        assert "sites" in out and "gut" in out["sites"]

    def test_gbdt_end_to_end(self):
        from app.agent.executor import _get_module_function
        mb, met, md = self._session_data()
        fn = _get_module_function("cross_omics_gbdt")
        out = fn(mb, df2=met, metadata_df=md, n_bootstrap=2, cv_folds=3)
        assert "results" in out
