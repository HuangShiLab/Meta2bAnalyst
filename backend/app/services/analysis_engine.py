"""
Meta2bAnalyst - Analysis Engine Service (Python Statistical Analysis)
Implements Alpha/Beta diversity, differential abundance, PCoA, NMDS, heatmap,
random forest, PERMANOVA, ANOSIM, and Plotly figure generation.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy import sparse
from scipy.spatial.distance import braycurtis, cityblock, euclidean, jaccard, pdist, squareform
from scipy.stats import f_oneway, mannwhitneyu, pearsonr, spearmanr, ttest_ind, wilcoxon
from sklearn.decomposition import PCA
from sklearn.isotonic import IsotonicRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.manifold import MDS
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ─────────────────────────────── Shared statistics helpers


def adjust_pvalues(pvalues, method: str = 'fdr_bh') -> np.ndarray:
    """Multiple-testing correction.

    Delegates to ``statsmodels.stats.multitest.multipletests``. The previous
    hand-rolled version computed ``p * n / rank`` without enforcing
    monotonicity, which yields adjusted p-values that are not non-decreasing in
    p and are anti-conservative for ties.

    Args:
        pvalues: 1-D array-like of raw p-values (NaNs are passed through).
        method: Any method name accepted by statsmodels ('fdr_bh', 'fdr_by',
            'bonferroni', 'holm', ...). 'BH'/'bh' are accepted as aliases.

    Returns:
        Array of adjusted p-values, same length and order as the input.
    """
    from statsmodels.stats.multitest import multipletests

    alias = {
        'bh': 'fdr_bh', 'BH': 'fdr_bh', 'fdr': 'fdr_bh',
        'by': 'fdr_by', 'BY': 'fdr_by',
        'bonferroni': 'bonferroni', 'holm': 'holm', 'none': None,
    }
    method = alias.get(method, method)

    p = np.asarray(pvalues, dtype=float)
    out = np.full(p.shape, np.nan)
    if p.size == 0:
        return out
    if method is None:
        return p.copy()

    finite = np.isfinite(p)
    if not finite.any():
        return out
    out[finite] = multipletests(p[finite], method=method)[1]
    return out


def resolve_comparison_groups(
    metadata_df: pd.DataFrame,
    group_column: str,
    comparisons: Optional[List[str]] = None,
    reference_group: Optional[str] = None,
) -> Tuple[str, str]:
    """Decide which two groups a pairwise test should compare.

    Previously this was ``g1, g2 = groups[0], groups[1]`` -- the first two values
    pandas happened to return, so users could not choose the contrast, the
    fold-change direction flipped if the metadata rows were reordered, and a
    seven-timepoint study silently compared only two of them.

    Args:
        metadata_df: Metadata indexed by sample ID.
        group_column: Column holding the grouping variable.
        comparisons: Explicit group labels. Two labels select the contrast; one
            label is compared against ``reference_group``.
        reference_group: Baseline group (becomes ``group1``).

    Returns:
        ``(reference, test)``. Fold changes are computed as test / reference.

    Raises:
        ValueError: If the requested groups do not exist, or if the column has
            more than two groups and no explicit selection was made.
    """
    available = [str(g) for g in pd.unique(metadata_df[group_column].dropna())]
    available_sorted = sorted(available)

    def _require(label: str) -> str:
        if str(label) not in available:
            raise ValueError(
                f"Group '{label}' is not present in metadata column "
                f"'{group_column}'. Available groups: {', '.join(available_sorted)}."
            )
        return str(label)

    selected = [str(c) for c in (comparisons or []) if str(c).strip()]

    if len(selected) >= 2:
        if len(selected) > 2:
            raise ValueError(
                f"Pairwise testing compares exactly 2 groups, but {len(selected)} "
                f"were given: {', '.join(selected)}."
            )
        g1, g2 = _require(selected[0]), _require(selected[1])
        if reference_group and str(reference_group) == g2:
            g1, g2 = g2, g1  # honour an explicit baseline
        if g1 == g2:
            raise ValueError("The two groups to compare must be different.")
        return g1, g2

    if len(selected) == 1:
        if not reference_group:
            raise ValueError(
                f"Only one group ('{selected[0]}') was selected. Provide a second "
                f"group in `comparisons`, or set `reference_group` as the baseline. "
                f"Available groups: {', '.join(available_sorted)}."
            )
        return _require(reference_group), _require(selected[0])

    if reference_group:
        ref = _require(reference_group)
        others = [g for g in available_sorted if g != ref]
        if len(others) != 1:
            raise ValueError(
                f"Column '{group_column}' has {len(available)} groups, so the group "
                f"to compare against reference '{ref}' is ambiguous. Set "
                f"`comparisons`. Available groups: {', '.join(available_sorted)}."
            )
        return ref, others[0]

    if len(available) == 2:
        # Sorted, not file order, so the fold-change direction is stable.
        return available_sorted[0], available_sorted[1]

    raise ValueError(
        f"Column '{group_column}' has {len(available)} groups "
        f"({', '.join(available_sorted)}); pairwise testing needs exactly 2. "
        f"Set `comparisons` to the two groups you want to compare, e.g. "
        f'"comparisons": ["{available_sorted[0]}", "{available_sorted[1]}"].'
    )


class AnalysisEngine:
    """Core statistical analysis engine for microbiome data."""

    # ─────────────────────────────── Alpha Diversity

    def alpha_diversity(
        self,
        df: pd.DataFrame,
        metrics: list[str] = ['shannon', 'simpson', 'chao1'],
    ) -> pd.DataFrame:
        """Calculate alpha diversity indices for each sample.

        Metrics:
            - shannon: Shannon diversity index (entropy-based).
            - simpson: Simpson diversity index (1 - sum(p^2)).
            - chao1: Chao1 richness estimator.
            - ace: ACE richness estimator (simplified).
            - observed: Observed species richness.
            - pielou: Pielou's evenness (Shannon / log(richness)).

        Args:
            df: Feature table (features x samples).
            metrics: List of diversity metrics to compute.

        Returns:
            DataFrame with samples as rows and diversity metrics as columns.
        """
        results = {}

        for metric in metrics:
            if metric == 'shannon':
                results[metric] = self._calculate_shannon(df)
            elif metric == 'simpson':
                results[metric] = self._calculate_simpson(df)
            elif metric == 'chao1':
                results[metric] = self._calculate_chao1(df)
            elif metric == 'ace':
                results[metric] = self._calculate_ace(df)
            elif metric == 'observed':
                results[metric] = self._calculate_observed(df)
            elif metric == 'pielou':
                results[metric] = self._calculate_pielou(df)
            else:
                logger.warning(f"Unknown alpha diversity metric: {metric}")

        return pd.DataFrame(results, index=df.columns)

    def _calculate_shannon(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Shannon diversity index."""
        proportions = df.div(df.sum(axis=0), axis=1).fillna(0)
        proportions = proportions[proportions > 0]
        shannon = -proportions.multiply(np.log(proportions)).sum(axis=0)
        return shannon

    def _calculate_simpson(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Simpson diversity index."""
        proportions = df.div(df.sum(axis=0), axis=1).fillna(0)
        simpson = 1 - (proportions ** 2).sum(axis=0)
        return simpson

    def _calculate_chao1(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the bias-corrected Chao1 richness estimator.

        Chao1 = S_obs + F1 * (F1 - 1) / (2 * (F2 + 1))

        This is the bias-corrected form (Chao 1987), which is what vegan and
        scikit-bio report by default and which stays finite when there are no
        doubletons. The classic form S_obs + F1^2 / (2*F2) is undefined at
        F2 = 0; guarding it with a 1e-10 epsilon (as this code previously did)
        does not fix it -- it produces values on the order of 1e10 for any
        sample without doubletons, which is common in sparse 2bRAD-M tables.
        """
        counts = df.round()  # F1/F2 are only meaningful for integer counts
        singletons = (counts == 1).sum(axis=0).astype(float)
        doubletons = (counts == 2).sum(axis=0).astype(float)
        observed = (df > 0).sum(axis=0).astype(float)
        return observed + singletons * (singletons - 1) / (2 * (doubletons + 1))

    def _calculate_ace(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the ACE (Abundance-based Coverage Estimator) richness index.

        ACE = S_abund + S_rare / C_ace + F1 / C_ace * gamma^2

        with rare species defined as those with abundance <= 10, C_ace the
        Good-Turing sample coverage, and gamma^2 the estimated coefficient of
        variation of the rare-species abundances.

        Returns S_obs when there are no rare species (ACE degenerates to the
        observed richness), and NaN when every rare species is a singleton --
        coverage is then 0 and ACE is genuinely undefined. scikit-bio raises in
        that case; NaN is used here so one degenerate sample does not fail the
        whole request, and so the value is never mistaken for an estimate.
        """
        counts = df.round()
        rare_threshold = 10
        ace_values = {}

        for sample in counts.columns:
            col = counts[sample]
            col = col[col > 0]
            if col.empty:
                ace_values[sample] = 0.0
                continue

            rare = col[col <= rare_threshold]
            s_abund = float((col > rare_threshold).sum())
            s_rare = float(len(rare))
            f1 = float((col == 1).sum())
            n_rare = float(rare.sum())

            if s_rare == 0:
                # Nothing rare to extrapolate from: ACE == observed richness.
                ace_values[sample] = float(len(col))
                continue

            coverage = 1.0 - f1 / n_rare if n_rare > 0 else 0.0
            if coverage <= 0:
                # All rare taxa are singletons -> ACE undefined (see docstring).
                ace_values[sample] = float('nan')
                continue

            # Coefficient of variation of rare-species abundances.
            sum_i_i_minus_1 = float(sum(i * (i - 1) * (rare == i).sum() for i in range(1, rare_threshold + 1)))
            gamma_sq = max(
                (s_rare / coverage) * sum_i_i_minus_1 / (n_rare * (n_rare - 1)) - 1.0
                if n_rare > 1 else 0.0,
                0.0,
            )
            ace_values[sample] = s_abund + s_rare / coverage + (f1 / coverage) * gamma_sq

        return pd.Series(ace_values, index=counts.columns, dtype=float)

    def _calculate_observed(self, df: pd.DataFrame) -> pd.Series:
        """Calculate observed species richness."""
        return (df > 0).sum(axis=0)

    def _calculate_pielou(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Pielou's evenness index (Shannon / ln(richness)).

        Evenness is undefined for samples with fewer than two observed
        features: ln(1) = 0 makes the ratio 0/0. Those samples return NaN
        rather than the +inf the previous ``+ 1e-10`` guard produced.
        """
        shannon = self._calculate_shannon(df)
        richness = self._calculate_observed(df).astype(float)
        denom = np.log(richness.where(richness > 1))
        return shannon / denom

    # ─────────────────────────────── Paged Result Helpers

    def get_paged_differential_results(
        self,
        diff_df: pd.DataFrame,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = "padj",
        sort_order: str = "asc",
        p_threshold: float = 1.0,
        fc_threshold: float = 0.0,
    ) -> dict:
        """Paginate differential analysis results.

        Returns:
            Dictionary with pagination metadata and data slice.
        """
        if diff_df.empty:
            return {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "data": [],
            }

        df = diff_df.copy()

        # Filter by p-value and fold-change if thresholds set
        if p_threshold < 1.0 and "pvalue" in df.columns:
            df = df[df["pvalue"] < p_threshold]
        if fc_threshold > 0 and "log2FC" in df.columns:
            df = df[df["log2FC"].abs() > fc_threshold]

        # Sort
        sort_col = sort_by if sort_by in df.columns else "pvalue"
        ascending = sort_order.lower() == "asc"
        df = df.sort_values(sort_col, ascending=ascending)

        total = len(df)
        total_pages = (total + page_size - 1) // page_size
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size

        page_df = df.iloc[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": page_df.to_dict(orient="records"),
        }

    def get_paged_feature_table(
        self,
        df: pd.DataFrame,
        page: int = 1,
        page_size: int = 100,
        sort_by: str = None,
        sort_order: str = "asc",
    ) -> dict:
        """Paginate feature table with optional sorting by total abundance.

        Returns:
            Dictionary with pagination metadata and data slice.
        """
        if df.empty:
            return {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "data": [],
            }

        df_sorted = df.copy()
        if sort_by and sort_by in df_sorted.columns:
            ascending = sort_order.lower() == "asc"
            df_sorted = df_sorted.sort_values(sort_by, ascending=ascending)
        elif sort_by == "total_abundance":
            ascending = sort_order.lower() == "asc"
            df_sorted = df_sorted.loc[df_sorted.sum(axis=1).sort_values(ascending=ascending).index]

        total = len(df_sorted)
        total_pages = (total + page_size - 1) // page_size
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size

        page_df = df_sorted.iloc[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": page_df.to_dict(orient="index"),
        }

    # ─────────────────────────────── Beta Diversity

    def beta_diversity(
        self,
        df: pd.DataFrame,
        distance: str = 'braycurtis',
    ) -> pd.DataFrame:
        """Calculate beta diversity distance matrix between samples.

        Distances:
            - braycurtis: Bray-Curtis dissimilarity.
            - jaccard: Jaccard distance (1 - shared / union).
            - euclidean: Euclidean distance.
            - manhattan: Manhattan / city-block distance.

        Args:
            df: Feature table (features x samples).
            distance: Distance metric name.

        Returns:
            Square distance matrix DataFrame with samples as both rows and columns.
        """
        df_t = df.T.fillna(0)

        metric_map = {
            'braycurtis': 'braycurtis',
            'jaccard': 'jaccard',
            'euclidean': 'euclidean',
            'manhattan': 'cityblock',
        }
        scipy_metric = metric_map.get(distance, 'braycurtis')

        if scipy_metric == 'jaccard':
            # Jaccard is a presence/absence metric. scipy's implementation on
            # continuous input counts every position where the two vectors
            # merely *differ*, so on abundance data almost every pair comes out
            # near 1.0 regardless of which taxa are actually shared. Binarise
            # first so the metric means what its name says.
            values = (df_t.values > 0)
            distances = pdist(values, metric='jaccard')
        else:
            distances = pdist(df_t.values, metric=scipy_metric)

        dist_matrix = squareform(distances)
        return pd.DataFrame(dist_matrix, index=df_t.index, columns=df_t.index)

    # ─────────────────────────────── PCoA

    def pcoa(self, distance_matrix: pd.DataFrame) -> dict:
        """Principal Coordinates Analysis (PCoA) on a distance matrix.

        Args:
            distance_matrix: Square distance matrix (samples x samples).

        Returns:
            Dictionary with:
                - eigenvalues: List of eigenvalues for each component.
                - samples: DataFrame with PC coordinates (PC1, PC2, PC3, ...).
                - variance_explained: Percentage of variance explained by each component.
        """
        D = distance_matrix.values.astype(float)
        n = D.shape[0]

        # Double-centering for PCoA
        H = np.eye(n) - np.ones((n, n)) / n
        B = -0.5 * H @ (D ** 2) @ H

        # Eigen decomposition
        eigenvalues, eigenvectors = np.linalg.eigh(B)

        # Sort in descending order
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # Take positive eigenvalues only
        positive_mask = eigenvalues > 1e-10
        eigenvalues = eigenvalues[positive_mask]
        eigenvectors = eigenvectors[:, positive_mask]

        # Coordinates
        coordinates = eigenvectors * np.sqrt(eigenvalues)

        # Variance explained
        total_variance = np.sum(eigenvalues[eigenvalues > 0])
        variance_explained = (
            [(e / total_variance) * 100 for e in eigenvalues]
            if total_variance > 0
            else []
        )

        # Always expose at least PC1/PC2, zero-padded when the matrix is
        # rank-deficient. A degenerate distance matrix (every sample identical,
        # e.g. Jaccard on a table where all samples share all features) has no
        # positive eigenvalues; returning a 0-column frame made every downstream
        # plot raise KeyError('PC1') as an opaque 500.
        n_positive = len(eigenvalues)
        n_components = max(n_positive, 2)
        pc_cols = [f'PC{i + 1}' for i in range(n_components)]
        padded = np.zeros((len(distance_matrix.index), n_components))
        if n_positive:
            padded[:, :n_positive] = coordinates
        coords_df = pd.DataFrame(padded, index=distance_matrix.index, columns=pc_cols)

        result = {
            'eigenvalues': eigenvalues.tolist(),
            'samples': coords_df,
            'variance_explained': variance_explained + [0.0] * (n_components - n_positive),
        }
        if n_positive == 0:
            result['degenerate'] = True
            result['warning'] = (
                'All pairwise distances are zero, so the ordination carries no '
                'information: every sample is identical under this distance metric. '
                'This is typical of a presence/absence metric (jaccard) on a table '
                'where all samples share all features -- use an abundance-weighted '
                'metric such as Bray-Curtis instead.'
            )
        return result

    # ─────────────────────────────── NMDS

    def nmds(
        self,
        distance_matrix: pd.DataFrame,
        n_components: int = 2,
    ) -> dict:
        """Non-metric Multidimensional Scaling (NMDS) on a distance matrix.

        Args:
            distance_matrix: Square distance matrix (samples x samples).
            n_components: Number of dimensions to compute.

        Returns:
            Dictionary with:
                - coordinates: DataFrame with NMDS coordinates.
                - stress: Stress value (goodness of fit).
        """
        mds = MDS(
            n_components=n_components,
            metric=False,
            dissimilarity='precomputed',
            random_state=42,
            max_iter=500,
            n_init=10,
        )
        # NOTE: the embedding itself is scikit-learn-version dependent (1.9's
        # optimiser reaches a markedly lower-stress solution than 1.6 on the same
        # input). The reported stress below always describes the embedding that
        # was actually produced, so it stays interpretable either way.
        coordinates = mds.fit_transform(distance_matrix.values)

        # Kruskal stress-1, computed from the returned embedding rather than from
        # ``mds.stress_``.
        #
        # Ecologists read NMDS stress against Kruskal's rules of thumb (<0.05
        # excellent, <0.1 good, <0.2 usable, >0.2 suspect), which are defined for
        #     stress-1 = sqrt( sum((d_fit - d_hat)^2) / sum(d_fit^2) )
        # where d_hat are the disparities from a monotone regression of the
        # observed dissimilarities onto the embedding distances.
        #
        # ``mds.stress_`` cannot be used for this: its meaning changed across
        # scikit-learn versions (1.6 returns a raw sum of squares, 1.9 returns an
        # already-normalised value under normalized_stress="auto"). Deriving
        # stress-1 from it therefore produced a different number on every
        # environment -- and on new scikit-learn it double-normalised, reporting
        # 0.008 where the embedding's true stress-1 was 0.0023.
        raw_stress = float(mds.stress_)
        d_obs = squareform(distance_matrix.values, checks=False)
        d_fit = pdist(coordinates)
        denom = float(np.sum(d_fit ** 2))
        if denom > 0:
            disparities = IsotonicRegression().fit_transform(d_obs, d_fit)
            stress_1 = float(np.sqrt(np.sum((d_fit - disparities) ** 2) / denom))
        else:
            stress_1 = float('nan')

        nmds_cols = [f'NMDS{i+1}' for i in range(n_components)]
        coords_df = pd.DataFrame(
            coordinates, index=distance_matrix.index, columns=nmds_cols
        )

        return {
            'coordinates': coords_df,
            'stress': stress_1,
            'stress_type': 'kruskal_stress_1',
            'raw_stress': raw_stress,
            'n_components': n_components,
        }

    # ─────────────────────────────── Differential Analysis

    def _prepare_differential_data(
        self,
        df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        group1: str,
        group2: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
        """Prepare feature table and metadata for two-group differential analysis."""
        g1_samples = metadata[metadata[group_var] == group1].index.intersection(df.columns)
        g2_samples = metadata[metadata[group_var] == group2].index.intersection(df.columns)
        g1_samples = [str(s) for s in g1_samples]
        g2_samples = [str(s) for s in g2_samples]
        return df, metadata, g1_samples, g2_samples

    def differential_ttest(
        self,
        df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        group1: str,
        group2: str,
    ) -> pd.DataFrame:
        """Two-sample t-test for differential abundance between two groups.

        Returns:
            DataFrame with columns:
                log2FC, pvalue, padj, mean_group1, mean_group2, std_group1, std_group2.
        """
        df, metadata, g1_samples, g2_samples = self._prepare_differential_data(
            df, metadata, group_var, group1, group2
        )

        results = []
        for feature in df.index:
            g1_values = df.loc[feature, g1_samples].dropna().astype(float).values
            g2_values = df.loc[feature, g2_samples].dropna().astype(float).values

            if len(g1_values) == 0 or len(g2_values) == 0:
                continue

            g1_mean = g1_values.mean() + 1e-10
            g2_mean = g2_values.mean() + 1e-10
            log2fc = np.log2(g2_mean / g1_mean)

            try:
                stat, pvalue = ttest_ind(g1_values, g2_values, equal_var=False)
            except Exception as e:
                logger.warning(f"t-test failed for feature {feature}: {e}")
                continue

            results.append({
                'feature': feature,
                'log2FC': float(log2fc),
                'pvalue': float(pvalue),
                'mean_group1': float(g1_mean),
                'mean_group2': float(g2_mean),
                'std_group1': float(g1_values.std()),
                'std_group2': float(g2_values.std()),
            })

        result_df = pd.DataFrame(results)
        if len(result_df) > 0:
            result_df['padj'] = adjust_pvalues(result_df['pvalue'].values, 'fdr_bh')
            result_df = result_df.sort_values('pvalue')

        return result_df

    def differential_wilcoxon(
        self,
        df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        group1: str,
        group2: str,
    ) -> pd.DataFrame:
        """Wilcoxon rank-sum test (Mann-Whitney U) for differential abundance.

        Returns:
            DataFrame with columns:
                log2FC, pvalue, padj, mean_group1, mean_group2, median_group1, median_group2.
        """
        df, metadata, g1_samples, g2_samples = self._prepare_differential_data(
            df, metadata, group_var, group1, group2
        )

        results = []
        for feature in df.index:
            g1_values = df.loc[feature, g1_samples].dropna().astype(float).values
            g2_values = df.loc[feature, g2_samples].dropna().astype(float).values

            if len(g1_values) == 0 or len(g2_values) == 0:
                continue

            g1_mean = g1_values.mean() + 1e-10
            g2_mean = g2_values.mean() + 1e-10
            log2fc = np.log2(g2_mean / g1_mean)

            try:
                stat, pvalue = mannwhitneyu(g1_values, g2_values, alternative='two-sided')
            except Exception as e:
                logger.warning(f"Wilcoxon test failed for feature {feature}: {e}")
                continue

            results.append({
                'feature': feature,
                'log2FC': float(log2fc),
                'pvalue': float(pvalue),
                'mean_group1': float(g1_mean),
                'mean_group2': float(g2_mean),
                'median_group1': float(np.median(g1_values)),
                'median_group2': float(np.median(g2_values)),
            })

        result_df = pd.DataFrame(results)
        if len(result_df) > 0:
            result_df['padj'] = adjust_pvalues(result_df['pvalue'].values, 'fdr_bh')
            result_df = result_df.sort_values('pvalue')

        return result_df

    def differential_anova(
        self,
        df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
    ) -> pd.DataFrame:
        """One-way ANOVA for differential abundance across multiple groups.

        Returns:
            DataFrame with columns: feature, fstat, pvalue, padj, group_means.
        """
        groups = metadata[group_var].dropna().unique()
        group_samples = {}
        for group in groups:
            samples = metadata[metadata[group_var] == group].index.intersection(df.columns)
            group_samples[group] = [str(s) for s in samples]

        results = []
        for feature in df.index:
            group_values = []
            group_means = {}
            for group, samples in group_samples.items():
                vals = df.loc[feature, samples].dropna().astype(float).values
                if len(vals) > 0:
                    group_values.append(vals)
                    group_means[str(group)] = float(vals.mean())

            if len(group_values) < 2:
                continue

            try:
                fstat, pvalue = f_oneway(*group_values)
            except Exception as e:
                logger.warning(f"ANOVA failed for feature {feature}: {e}")
                continue

            results.append({
                'feature': feature,
                'fstat': float(fstat),
                'pvalue': float(pvalue),
                'group_means': group_means,
            })

        result_df = pd.DataFrame(results)
        if len(result_df) > 0:
            result_df['padj'] = adjust_pvalues(result_df['pvalue'].values, 'fdr_bh')
            result_df = result_df.sort_values('pvalue')

        return result_df

    # ─────────────────────────────── PERMANOVA

    def permanova(
        self,
        distance_matrix: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        n_permutations: int = 999,
        random_seed: int = 42,
    ) -> dict:
        """PERMANOVA (Permutational Multivariate Analysis of Variance).

        Anderson (2001) partitioning of the distance matrix into within- and
        between-group sums of squares, with a label-permutation test.

        Args:
            distance_matrix: Square distance matrix.
            metadata: Metadata DataFrame with grouping variable.
            group_var: Column name for grouping.
            n_permutations: Number of permutations for p-value estimation.
            random_seed: Seed for the permutation RNG. Fixed by default so the
                reported p-value is reproducible; pass None for a fresh draw.

        Returns:
            Dictionary with pseudo-F, R^2, p-value and the SS partition.

        Raises:
            ValueError: If the samples cannot be grouped into >=2 groups.
        """
        samples = distance_matrix.index.intersection(metadata.index)
        if len(samples) == 0:
            raise ValueError(
                "No overlap between the distance matrix and the metadata index; "
                "the feature table is probably transposed."
            )
        dist = distance_matrix.loc[samples, samples].values
        groups = metadata.loc[samples, group_var].values
        unique_groups = np.unique(groups)
        n = len(samples)

        if len(unique_groups) < 2:
            raise ValueError(
                f"PERMANOVA needs at least 2 groups in '{group_var}', found "
                f"{len(unique_groups)} across {n} matched samples."
            )

        # Calculate within-group sum of squares (SSW)
        def calc_ssw(dist_matrix, group_labels, groups):
            ssw = 0.0
            for g in groups:
                group_idx = np.where(group_labels == g)[0]
                if len(group_idx) < 2:
                    continue
                group_dists = dist_matrix[np.ix_(group_idx, group_idx)]
                ssw += np.sum(group_dists ** 2) / (2 * len(group_idx))
            return ssw

        ssw_obs = calc_ssw(dist, groups, unique_groups)
        sst = np.sum(dist ** 2) / (2 * n)
        ssb = sst - ssw_obs

        df_between = len(unique_groups) - 1
        df_within = n - len(unique_groups)

        def _pseudo_f(ssb_val: float, ssw_val: float) -> float:
            # No epsilon in the denominator: it biases the statistic (visible as a
            # ~1e-6 offset against vegan/scikit-bio). SSW is 0 only in degenerate
            # cases, which are reported as +inf rather than silently rescaled.
            if ssw_val <= 0:
                return float('inf') if ssb_val > 0 else float('nan')
            return (ssb_val / df_between) / (ssw_val / df_within)

        f_obs = _pseudo_f(ssb, ssw_obs)
        r_squared = ssb / sst if sst > 0 else float('nan')

        # Permutation test. Uses a dedicated Generator seeded from `random_seed`
        # so repeated runs on the same data return the same p-value; the global
        # numpy RNG previously used made results irreproducible.
        rng = np.random.default_rng(random_seed)
        f_permuted = []
        for _ in range(n_permutations):
            permuted_groups = rng.permutation(groups)
            ssw_perm = calc_ssw(dist, permuted_groups, unique_groups)
            ssb_perm = sst - ssw_perm
            f_permuted.append(_pseudo_f(ssb_perm, ssw_perm))

        pvalue = (np.sum(np.array(f_permuted) >= f_obs) + 1) / (n_permutations + 1)

        return {
            'pseudo_f': float(f_obs),
            'r_squared': float(r_squared),
            'pvalue': float(pvalue),
            'ssb': float(ssb),
            'ssw': float(ssw_obs),
            'sst': float(sst),
            'df_between': int(df_between),
            'df_within': int(df_within),
            'n_permutations': n_permutations,
            'random_seed': random_seed,
            'n_samples': int(n),
            'groups': [str(g) for g in unique_groups],
            'significant': bool(pvalue < 0.05),
        }

    # ─────────────────────────────── ANOSIM

    def anosim(
        self,
        distance_matrix: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        n_permutations: int = 999,
        random_seed: int = 42,
    ) -> dict:
        """ANOSIM (Analysis of Similarities) test.

        R = (r_between - r_within) / (N * (N - 1) / 4), where N is the number of
        **samples** and r_* are mean ranks of the between/within-group pairwise
        distances (Clarke 1993). R is bounded in [-1, 1]: ~1 means groups are
        completely separated, ~0 means no separation.

        Args:
            distance_matrix: Square distance matrix.
            metadata: Metadata DataFrame with grouping variable.
            group_var: Column name for grouping.
            n_permutations: Number of permutations for p-value estimation.
            random_seed: Seed for the permutation RNG (fixed for reproducibility).

        Returns:
            Dictionary with R statistic, p-value, and test details.

        Raises:
            ValueError: If the samples cannot be grouped into >=2 groups.
        """
        samples = distance_matrix.index.intersection(metadata.index)
        if len(samples) == 0:
            raise ValueError(
                "No overlap between the distance matrix and the metadata index; "
                "the feature table is probably transposed."
            )
        dist = distance_matrix.loc[samples, samples].values
        groups = metadata.loc[samples, group_var].values
        unique_groups = np.unique(groups)
        n = len(samples)

        if len(unique_groups) < 2:
            raise ValueError(
                f"ANOSIM needs at least 2 groups in '{group_var}', found "
                f"{len(unique_groups)} across {n} matched samples."
            )

        # Rank distances
        triu_idx = np.triu_indices(n, k=1)
        dist_vals = dist[triu_idx]
        ranks = pd.Series(dist_vals).rank().values

        group_i = groups[triu_idx[0]]
        group_j = groups[triu_idx[1]]

        within_mask = group_i == group_j
        between_mask = ~within_mask

        r_within = ranks[within_mask].mean() if within_mask.sum() > 0 else 0
        r_between = ranks[between_mask].mean() if between_mask.sum() > 0 else 0

        # Denominator is N(N-1)/4 with N = number of SAMPLES. This previously
        # used the number of pairwise distances (N(N-1)/2) in place of N, which
        # inflated the denominator by roughly N(N-1)/4 and drove R to ~0 for
        # every dataset (a perfectly separated 30-sample set reported R=0.005
        # instead of R=1.0).
        denom = n * (n - 1) / 4.0

        def _r_stat(labels: np.ndarray) -> float:
            g_i = labels[triu_idx[0]]
            g_j = labels[triu_idx[1]]
            w_mask = g_i == g_j
            b_mask = ~w_mask
            rw = ranks[w_mask].mean() if w_mask.sum() > 0 else 0
            rb = ranks[b_mask].mean() if b_mask.sum() > 0 else 0
            return (rb - rw) / denom

        r_obs = _r_stat(groups)

        # Permutation test (seeded; see permanova for rationale)
        rng = np.random.default_rng(random_seed)
        r_permuted = [_r_stat(rng.permutation(groups)) for _ in range(n_permutations)]

        pvalue = (np.sum(np.array(r_permuted) >= r_obs) + 1) / (n_permutations + 1)

        return {
            'r_statistic': float(r_obs),
            'pvalue': float(pvalue),
            'n_permutations': n_permutations,
            'random_seed': random_seed,
            'n_samples': int(n),
            'groups': [str(g) for g in unique_groups],
            'mean_rank_within': float(r_within),
            'mean_rank_between': float(r_between),
            # Legacy key names kept for existing frontend/report consumers.
            'r_within': float(r_within),
            'r_between': float(r_between),
            'significant': bool(pvalue < 0.05),
        }

    # ─────────────────────────────── Random Forest

    def random_forest(
        self,
        df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        n_estimators: int = 500,
    ) -> dict:
        """Random Forest classification with feature importance.

        Uses sklearn.ensemble.RandomForestClassifier to classify samples
        based on group membership and extract feature importance scores.

        Args:
            df: Feature table (features x samples).
            metadata: Metadata DataFrame with grouping variable.
            group_var: Column name for grouping.
            n_estimators: Number of trees in the forest.

        Returns:
            Dictionary with accuracy, feature importance, and cross-validation results.
        """
        samples = df.columns.intersection(metadata.index)
        if len(samples) == 0:
            raise ValueError(
                "No overlap between feature-table columns and metadata index; "
                "the feature table is probably transposed."
            )
        X = df[samples].T.values
        y = metadata.loc[samples, group_var].values

        # Encode labels
        from sklearn.preprocessing import LabelEncoder

        le = LabelEncoder()
        y_encoded = le.fit_transform(y)

        # Smallest class size drives what is feasible for stratified splitting/CV.
        class_counts = np.bincount(y_encoded)
        min_class_size = int(class_counts.min())
        if min_class_size < 2:
            raise ValueError(
                f"Random Forest needs at least 2 samples per group; smallest group in "
                f"'{group_var}' has {min_class_size}."
            )

        # Train/test split
        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_encoded, test_size=0.3, random_state=42, stratify=y_encoded
        )

        # Random Forest
        rf = RandomForestClassifier(
            n_estimators=n_estimators, random_state=42, n_jobs=-1
        )
        rf.fit(X_train, y_train)
        accuracy = float(rf.score(X_test, y_test))

        # Feature importance
        importances = rf.feature_importances_
        feature_names = df.index.tolist()
        importance_df = pd.DataFrame({
            'feature': feature_names,
            'importance': importances,
        }).sort_values('importance', ascending=False)

        # Cross-validation. The number of folds is bounded by the smallest class,
        # not by the number of classes (stratified CV needs >=1 sample per class
        # per fold).
        from sklearn.model_selection import cross_val_score

        n_splits = max(2, min(5, min_class_size))
        cv_scores = cross_val_score(rf, X, y_encoded, cv=n_splits)

        # Confusion matrix. y_test/y_pred are label-encoded integers, so `labels`
        # must be the encoded values -- passing le.classes_ (strings) here raises
        # a TypeError on comparison.
        from sklearn.metrics import confusion_matrix
        y_pred = rf.predict(X_test)
        encoded_labels = list(range(len(le.classes_)))
        cm = confusion_matrix(y_test, y_pred, labels=encoded_labels)
        cm_dict = {
            'labels': [str(c) for c in le.classes_],
            'matrix': cm.tolist(),
        }

        return {
            'accuracy': accuracy,
            'cv_mean_accuracy': float(cv_scores.mean()),
            'cv_std_accuracy': float(cv_scores.std()),
            'cv_folds': n_splits,
            'n_estimators': n_estimators,
            'n_features': len(feature_names),
            'n_samples': len(samples),
            'feature_importance': importance_df.head(50).to_dict(orient='records'),
            'class_labels': le.classes_.tolist(),
            'confusion_matrix': cm_dict,
        }

    # ─────────────────────────────── Plotly Chart Generators

    def plotly_alpha_boxplot(
        self,
        alpha_df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        metric: str,
    ) -> dict:
        """Generate Plotly JSON for alpha diversity box plot.

        Args:
            alpha_df: DataFrame with samples as rows and metrics as columns.
            metadata: Metadata DataFrame with grouping variable.
            group_var: Column name for grouping.
            metric: Diversity metric to plot.

        Returns:
            Plotly figure JSON dict.
        """
        samples = alpha_df.index.intersection(metadata.index)
        plot_data = []

        groups = metadata.loc[samples, group_var].unique()
        for group in groups:
            group_samples = metadata[metadata[group_var] == group].index.intersection(samples)
            values = alpha_df.loc[group_samples, metric].dropna().values
            plot_data.append(
                go.Box(
                    y=values,
                    name=str(group),
                    boxmean=True,
                )
            )

        fig = go.Figure(data=plot_data)
        fig.update_layout(
            title=f'{metric.capitalize()} Diversity by {group_var}',
            yaxis_title=metric.capitalize(),
            xaxis_title=group_var,
            boxmode='group',
        )
        return fig.to_dict()

    def plotly_pcoa_scatter(
        self,
        pcoa_result: dict,
        metadata: pd.DataFrame,
        group_var: str,
    ) -> dict:
        """Generate Plotly JSON for PCoA scatter plot.

        Args:
            pcoa_result: Result dictionary from pcoa().
            metadata: Metadata DataFrame with grouping variable.
            group_var: Column name for grouping.

        Returns:
            Plotly figure JSON dict.
        """
        coords_df = pcoa_result['samples']
        samples = coords_df.index.intersection(metadata.index)
        variance = pcoa_result.get('variance_explained', [0, 0])

        plot_data = []
        groups = metadata.loc[samples, group_var].unique()
        for group in groups:
            group_samples = metadata[metadata[group_var] == group].index.intersection(samples)
            x_vals = coords_df.loc[group_samples, 'PC1'].values
            y_vals = coords_df.loc[group_samples, 'PC2'].values
            plot_data.append(
                go.Scatter(
                    x=x_vals,
                    y=y_vals,
                    mode='markers',
                    name=str(group),
                    text=[str(s) for s in group_samples],
                    marker=dict(size=10),
                )
            )

        fig = go.Figure(data=plot_data)
        pc1_label = f"PC1 ({variance[0]:.1f}%)" if len(variance) > 0 else "PC1"
        pc2_label = f"PC2 ({variance[1]:.1f}%)" if len(variance) > 1 else "PC2"
        fig.update_layout(
            title='PCoA Plot',
            xaxis_title=pc1_label,
            yaxis_title=pc2_label,
            hovermode='closest',
        )
        return fig.to_dict()

    def plotly_heatmap(
        self,
        df: pd.DataFrame,
        metadata: Optional[pd.DataFrame] = None,
        group_var: Optional[str] = None,
    ) -> dict:
        """Generate Plotly JSON for heatmap.

        Args:
            df: Feature table (features x samples).
            metadata: Optional metadata for grouping.
            group_var: Optional grouping variable for column annotation.

        Returns:
            Plotly figure JSON dict.
        """
        # Select top 50 features by variance for display
        if len(df) > 50:
            top_features = df.var(axis=1).sort_values(ascending=False).head(50).index
            df_plot = df.loc[top_features]
        else:
            df_plot = df.copy()

        # Z-score normalization per feature for visualization
        df_plot = df_plot.T.apply(lambda x: (x - x.mean()) / (x.std() + 1e-10), axis=0).T

        fig = go.Figure(data=go.Heatmap(
            z=df_plot.values,
            x=[str(c) for c in df_plot.columns],
            y=[str(r) for r in df_plot.index],
            colorscale='RdBu_r',
            zmid=0,
        ))
        fig.update_layout(
            title='Feature Abundance Heatmap (Top 50 by Variance)',
            xaxis_title='Samples',
            yaxis_title='Features',
            xaxis={'tickangle': -45},
        )
        return fig.to_dict()

    def plotly_stacked_bar(
        self,
        df: pd.DataFrame,
        metadata: Optional[pd.DataFrame] = None,
        group_var: Optional[str] = None,
        tax_level: Optional[str] = None,
    ) -> dict:
        """Generate Plotly JSON for stacked bar chart (compositional plot).

        Args:
            df: Feature table (features x samples).
            metadata: Optional metadata for grouping.
            group_var: Optional grouping variable to sort samples.
            tax_level: Optional taxonomy level (for labeling).

        Returns:
            Plotly figure JSON dict.
        """
        # Convert to relative abundance
        rel_abund = df.div(df.sum(axis=0), axis=1).fillna(0)

        # Select top 20 features; group rest as "Other"
        if len(rel_abund) > 20:
            top_features = rel_abund.mean(axis=1).sort_values(ascending=False).head(20).index
            other = rel_abund.loc[~rel_abund.index.isin(top_features)].sum(axis=0)
            rel_abund = rel_abund.loc[top_features]
            rel_abund.loc['Other'] = other

        # Sort samples by group if metadata provided
        sample_order = list(rel_abund.columns)
        if metadata is not None and group_var is not None and group_var in metadata.columns:
            samples = [s for s in rel_abund.columns if s in metadata.index]
            groups = metadata.loc[samples, group_var]
            sample_order = groups.sort_values().index.tolist()
            # Ensure all columns are included
            sample_order = [s for s in sample_order if s in rel_abund.columns]
            missing = [s for s in rel_abund.columns if s not in sample_order]
            sample_order = sample_order + missing

        fig = go.Figure()
        for feature in rel_abund.index:
            fig.add_trace(go.Bar(
                name=str(feature),
                x=[str(s) for s in sample_order],
                y=rel_abund.loc[feature, sample_order].values,
            ))

        fig.update_layout(
            barmode='stack',
            title='Relative Abundance Composition',
            xaxis_title='Samples',
            yaxis_title='Relative Abundance',
            xaxis={'tickangle': -45},
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=-0.5,
            ),
        )
        return fig.to_dict()

    def plotly_volcano(
        self,
        diff_df: pd.DataFrame,
        p_threshold: float = 0.05,
        fc_threshold: float = 1.0,
    ) -> dict:
        """Generate Plotly JSON for volcano plot.

        Args:
            diff_df: Differential analysis result DataFrame.
            p_threshold: P-value significance threshold.
            fc_threshold: Log2 fold-change threshold.

        Returns:
            Plotly figure JSON dict.
        """
        diff_df = diff_df.copy()
        diff_df['neg_log10_p'] = -np.log10(diff_df['pvalue'].replace(0, 1e-300))

        # Color points
        def get_color(row):
            if row['pvalue'] < p_threshold and abs(row['log2FC']) > fc_threshold:
                return 'red' if row['log2FC'] > 0 else 'blue'
            elif row['pvalue'] < p_threshold:
                return 'orange'
            else:
                return 'gray'

        diff_df['color'] = diff_df.apply(get_color, axis=1)

        fig = go.Figure(data=go.Scatter(
            x=diff_df['log2FC'].values,
            y=diff_df['neg_log10_p'].values,
            mode='markers',
            text=diff_df['feature'].values,
            marker=dict(
                color=diff_df['color'].values,
                size=8,
            ),
        ))

        max_y = diff_df['neg_log10_p'].max()
        fig.add_vline(x=-fc_threshold, line_dash='dash', line_color='gray')
        fig.add_vline(x=fc_threshold, line_dash='dash', line_color='gray')
        fig.add_hline(y=-np.log10(p_threshold), line_dash='dash', line_color='gray')

        fig.update_layout(
            title='Volcano Plot',
            xaxis_title='Log2 Fold Change',
            yaxis_title='-Log10 P-value',
            hovermode='closest',
        )
        return fig.to_dict()

    def plotly_library_size(self, df: pd.DataFrame) -> dict:
        """Generate Plotly JSON for library size bar chart.

        Args:
            df: Feature table (features x samples).

        Returns:
            Plotly figure JSON dict.
        """
        lib_sizes = df.sum(axis=0).sort_values(ascending=False)

        fig = go.Figure(data=go.Bar(
            x=[str(s) for s in lib_sizes.index],
            y=lib_sizes.values,
            marker_color='steelblue',
        ))
        fig.update_layout(
            title='Library Size per Sample',
            xaxis_title='Samples',
            yaxis_title='Total Reads',
            xaxis={'tickangle': -45},
        )
        return fig.to_dict()

    def plotly_rf_feature_importance(self, fi_df: pd.DataFrame, top_n: int = 20) -> dict:
        """Generate feature importance bar chart as Plotly JSON."""
        if fi_df.empty or 'feature' not in fi_df.columns or 'importance' not in fi_df.columns:
            return {'data': [], 'layout': {'title': 'Feature Importance (No data)'}}
        fi_df = fi_df.sort_values('importance', ascending=True).tail(top_n)
        colors = fi_df['importance'].apply(lambda x: f'rgba(30, 64, 175, {0.3 + 0.7 * x / fi_df["importance"].max()})')
        fig = go.Figure(data=go.Bar(
            x=fi_df['importance'].values,
            y=fi_df['feature'].values,
            orientation='h',
            marker_color=colors.values,
        ))
        fig.update_layout(
            title=f'Top {top_n} Feature Importance (Random Forest)',
            xaxis_title='Importance',
            yaxis_title='Feature',
            margin=dict(l=200),
        )
        return fig.to_dict()

    def plotly_confusion_matrix(self, cm_data: dict) -> dict:
        """Generate confusion matrix heatmap as Plotly JSON."""
        labels = cm_data.get('labels', [])
        matrix = cm_data.get('matrix', [])
        if not labels or not matrix:
            return {'data': [], 'layout': {'title': 'Confusion Matrix (No data)'}}
        fig = go.Figure(data=go.Heatmap(
            z=matrix,
            x=[str(l) for l in labels],
            y=[str(l) for l in labels],
            colorscale='Blues',
            showscale=True,
            text=[[str(v) for v in row] for row in matrix],
            texttemplate='%{text}',
            textfont={'size': 12},
        ))
        fig.update_layout(
            title='Confusion Matrix',
            xaxis_title='Predicted',
            yaxis_title='Actual',
            xaxis_side='bottom',
        )
        return fig.to_dict()

    def plotly_lefse_bar(self, lefse_df: pd.DataFrame, lda_threshold: float = 2.0) -> dict:
        """Generate LEfSe LDA bar chart as Plotly JSON."""
        if lefse_df.empty or 'lda_score' not in lefse_df.columns:
            return {'data': [], 'layout': {'title': 'LEfSe LDA Scores (No data)'}}
        # Filter by absolute LDA threshold
        plot_df = lefse_df[lefse_df['lda_score'].abs() >= lda_threshold].copy()
        if plot_df.empty:
            plot_df = lefse_df.copy()
        plot_df = plot_df.sort_values('lda_score', ascending=True)
        # Determine colors: positive vs negative
        def get_color(x):
            return '#dc2626' if x > 0 else '#1e40af'
        colors = plot_df['lda_score'].apply(get_color)
        fig = go.Figure(data=go.Bar(
            x=plot_df['lda_score'].values,
            y=plot_df['feature'].values,
            orientation='h',
            marker_color=colors.values,
        ))
        fig.add_vline(x=lda_threshold, line_dash='dash', line_color='gray')
        fig.add_vline(x=-lda_threshold, line_dash='dash', line_color='gray')
        fig.update_layout(
            title=f'LEfSe LDA Scores (|LDA| >= {lda_threshold})',
            xaxis_title='LDA Score',
            yaxis_title='Feature',
            margin=dict(l=200),
        )
        return fig.to_dict()

    def plotly_maaslin3_bar(self, maaslin_df: pd.DataFrame) -> dict:
        """Generate MaAsLin3 coefficient bar plot as Plotly JSON.

        Args:
            maaslin_df: MaAsLin3 result DataFrame with columns:
                feature, metadata, coefficient, padj.

        Returns:
            Plotly figure JSON dict.
        """
        if len(maaslin_df) == 0:
            return {'data': [], 'layout': {'title': 'MaAsLin3 Results (No significant associations)'}}

        # Filter significant results
        sig_df = maaslin_df[maaslin_df.get('padj', 1.0) < 0.05] if 'padj' in maaslin_df.columns else maaslin_df.head(50)
        if sig_df.empty:
            sig_df = maaslin_df.head(50)

        colors = sig_df['coefficient'].apply(lambda x: '#dc2626' if x > 0 else '#1e40af')

        return {
            'data': [{
                'type': 'bar',
                'x': sig_df['feature'].tolist(),
                'y': sig_df['coefficient'].tolist(),
                'marker': {'color': colors.tolist()},
                'text': sig_df['metadata'].tolist(),
            }],
            'layout': {
                'title': 'MaAsLin3 Significant Associations',
                'xaxis': {'title': 'Feature', 'tickangle': -45},
                'yaxis': {'title': 'Coefficient'},
                'shapes': [{
                    'type': 'line',
                    'x0': -0.5, 'x1': len(sig_df) - 0.5,
                    'y0': 0, 'y1': 0,
                    'line': {'color': '#94a3b8', 'width': 1, 'dash': 'dash'}
                }]
            }
        }


# ─────────────────────────────── Module-level convenience functions


def run_alpha_diversity(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run alpha diversity analysis and return structured results."""
    params = parameters or {}
    indices = params.get('indices', ['shannon', 'simpson', 'observed', 'chao1', 'evenness'])

    # `df` is expected in canonical features x samples orientation, resolved once
    # at the data-access layer (app/services/orientation.py). This function used
    # to re-guess with a regex on the first row/column label, which disagreed with
    # the heuristics in run_beta_diversity and with run_pcoa (which had none) --
    # so one upload could yield alpha diversity over samples and PCoA over taxa.
    engine = AnalysisEngine()
    alpha_df = engine.alpha_diversity(df, metrics=indices)

    results = {'sample_diversity': alpha_df.to_dict(orient='index')}

    # Group statistics
    group_column = params.get('group_column')
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results['group_statistics'] = {}
        groups = metadata_df[group_column].dropna().unique()

        for metric in indices:
            if metric not in alpha_df.columns:
                continue
            group_stats = {}
            for group in groups:
                group_samples = metadata_df[metadata_df[group_column] == group].index.intersection(alpha_df.index)
                if len(group_samples) > 0:
                    vals = alpha_df.loc[group_samples, metric]
                    group_stats[str(group)] = {
                        'mean': float(vals.mean()),
                        'median': float(vals.median()),
                        'std': float(vals.std()),
                        'min': float(vals.min()),
                        'max': float(vals.max()),
                        'n': int(len(vals)),
                    }

            # Statistical test
            if len(groups) == 2:
                g1, g2 = groups
                s1 = metadata_df[metadata_df[group_column] == g1].index.intersection(alpha_df.index)
                s2 = metadata_df[metadata_df[group_column] == g2].index.intersection(alpha_df.index)
                if len(s1) > 0 and len(s2) > 0:
                    try:
                        stat, pvalue = mannwhitneyu(
                            alpha_df.loc[s1, metric].values,
                            alpha_df.loc[s2, metric].values,
                            alternative='two-sided',
                        )
                        group_stats['statistical_test'] = {
                            'test': 'Mann-Whitney U',
                            'statistic': float(stat),
                            'pvalue': float(pvalue),
                            'significant': bool(pvalue < 0.05),
                        }
                    except Exception as e:
                        logger.warning(f"Statistical test failed: {e}")
            elif len(groups) > 2:
                group_values = [
                    alpha_df.loc[
                        metadata_df[metadata_df[group_column] == g].index.intersection(alpha_df.index),
                        metric,
                    ].values
                    for g in groups
                ]
                group_values = [g for g in group_values if len(g) > 0]
                if len(group_values) > 1:
                    try:
                        stat, pvalue = f_oneway(*group_values)
                        group_stats['statistical_test'] = {
                            'test': 'ANOVA (F-test)',
                            'statistic': float(stat),
                            'pvalue': float(pvalue),
                            'significant': bool(pvalue < 0.05),
                        }
                    except Exception as e:
                        logger.warning(f"ANOVA failed: {e}")

            results['group_statistics'][metric] = group_stats

    return results


def run_beta_diversity(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run beta diversity analysis and return structured results."""
    params = parameters or {}
    metric = params.get('metric', 'braycurtis')

    # See run_alpha_diversity: orientation is settled upstream, not guessed here.
    engine = AnalysisEngine()
    dist_matrix = engine.beta_diversity(df, distance=metric)

    results = {
        'metric': metric,
        'distance_matrix': dist_matrix.to_dict(),
        'sample_count': len(df.columns),
    }

    group_column = params.get('group_column')
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        groups = metadata_df[group_column].dropna().unique()
        group_stats = {}
        for group in groups:
            group_samples = metadata_df[metadata_df[group_column] == group].index.intersection(dist_matrix.index)
            group_samples = [str(s) for s in group_samples]
            if len(group_samples) > 1:
                group_dists = dist_matrix.loc[group_samples, group_samples]
                upper_tri = np.triu(group_dists.values, k=1)
                non_zero = upper_tri[upper_tri > 0]
                group_stats[str(group)] = {
                    'mean_within_group_distance': float(non_zero.mean()) if len(non_zero) > 0 else 0.0,
                    'n_samples': int(len(group_samples)),
                }
        results['group_statistics'] = group_stats

    return results


def _group_confidence_ellipse(
    xs: List[float], ys: List[float], n_points: int = 60
) -> Optional[tuple]:
    """95% confidence ellipse (chi2 df=2 -> scale sqrt(5.99) ~ 2.448) for a
    cloud of 2-D points, matching the per-timepoint ellipses in the source
    publication's PCoA panels. Returns (xs, ys) of the ellipse outline or
    None when the group has too few points."""
    if len(xs) < 3:
        return None
    cov = np.cov(xs, ys)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = np.maximum(eigvals[order], 0.0)
    eigvecs = eigvecs[:, order]
    theta = np.linspace(0, 2 * np.pi, n_points)
    circle = np.vstack([np.cos(theta), np.sin(theta)])
    radii = np.sqrt(eigvals) * 2.448
    pts = eigvecs @ (circle * radii[:, None])
    pts[0] += float(np.mean(xs))
    pts[1] += float(np.mean(ys))
    return pts[0].tolist(), pts[1].tolist()


_PLOTLY_GROUP_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]


def _ordination_scatter_plot(
    coords: pd.DataFrame,
    x_col: str,
    y_col: str,
    *,
    xlabel: str,
    ylabel: str,
    title: str,
    group_metadata: Optional[Dict[str, str]] = None,
    point_sizes: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Build a Plotly scatter figure for ordination coordinates.

    One trace per group when ``group_metadata`` (sample -> group) is given,
    with a 95% confidence ellipse per group (the source publication's PCoA
    style); otherwise a single trace with all samples.  ``point_sizes``
    (sample -> continuous value, e.g. bleeding severity) scales marker
    diameters.  Always returns a figure dict so the agent executor can
    stream it as ``plot_data``.
    """
    size_for: Optional[Dict[str, float]] = None
    if point_sizes:
        vals = [float(v) for v in point_sizes.values() if np.isfinite(float(v))]
        if vals:
            lo, hi = min(vals), max(vals)
            span = (hi - lo) or 1.0
            size_for = {
                str(k): 6.0 + 12.0 * (float(v) - lo) / span
                for k, v in point_sizes.items()
            }

    def _marker(color: Optional[str], index: pd.Index) -> Dict[str, Any]:
        marker: Dict[str, Any] = {'opacity': 0.8}
        if color:
            marker['color'] = color
        if size_for:
            marker['size'] = [size_for.get(str(s), 8.0) for s in index]
        else:
            marker['size'] = 10
        return marker

    traces: List[Dict[str, Any]] = []
    if group_metadata:
        groups = pd.Series({str(k): str(v) for k, v in group_metadata.items()})
        common = coords.index.intersection(groups.index)
        for i, grp in enumerate(groups.loc[common].unique()):
            color = _PLOTLY_GROUP_COLORS[i % len(_PLOTLY_GROUP_COLORS)]
            mask = (groups.loc[common] == grp).values
            sub = coords.loc[common][mask]
            traces.append({
                'x': sub[x_col].tolist(),
                'y': sub[y_col].tolist(),
                'mode': 'markers',
                'name': str(grp),
                'text': [str(s) for s in sub.index],
                'marker': _marker(color, sub.index),
            })
            # Per-group 95% confidence ellipse (paper Fig 1c/1d style)
            ellipse = _group_confidence_ellipse(sub[x_col].tolist(), sub[y_col].tolist())
            if ellipse is not None:
                traces.append({
                    'x': ellipse[0],
                    'y': ellipse[1],
                    'mode': 'lines',
                    'name': f'{grp} 95% ellipse',
                    'line': {'color': color, 'width': 2},
                    'showlegend': False,
                    'hoverinfo': 'skip',
                })
    else:
        traces.append({
            'x': coords[x_col].tolist(),
            'y': coords[y_col].tolist(),
            'mode': 'markers',
            'name': 'samples',
            'text': [str(s) for s in coords.index],
            'marker': _marker(None, coords.index),
        })
    return {
        'data': traces,
        'layout': {
            'title': title,
            'xaxis': {'title': xlabel},
            'yaxis': {'title': ylabel},
            'hovermode': 'closest',
        },
    }


def run_pcoa(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run PCoA and return structured results."""
    params = parameters or {}
    metric = params.get('metric', 'braycurtis')
    engine = AnalysisEngine()
    dist_matrix = engine.beta_diversity(df, distance=metric)
    pcoa_result = engine.pcoa(dist_matrix)

    results = {
        'metric': metric,
        'coordinates': pcoa_result['samples'].to_dict(orient='index'),
        'eigenvalues': pcoa_result['eigenvalues'],
        'variance_explained': pcoa_result['variance_explained'],
    }

    group_column = params.get('group_column')
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results['group_metadata'] = {
            str(s): str(metadata_df.loc[s, group_column])
            for s in pcoa_result['samples'].index
            if s in metadata_df.index
        }

    samples_df = pcoa_result['samples']
    if 'PC1' in samples_df.columns and 'PC2' in samples_df.columns:
        ve = results['variance_explained']
        vx = ve[0] if len(ve) > 0 else 0.0
        vy = ve[1] if len(ve) > 1 else 0.0
        # Optional continuous metadata column scales marker size (the paper
        # sizes dots by bleeding severity).
        point_sizes = None
        size_column = params.get('size_column')
        if metadata_df is not None and size_column and size_column in metadata_df.columns:
            point_sizes = {
                str(s): float(metadata_df.loc[s, size_column])
                for s in samples_df.index
                if s in metadata_df.index
                and pd.notna(metadata_df.loc[s, size_column])
            }
        results['plot_data'] = _ordination_scatter_plot(
            samples_df, 'PC1', 'PC2',
            xlabel=f'PC1 ({vx:.1f}%)',
            ylabel=f'PC2 ({vy:.1f}%)',
            title=f'Microbiome PCoA ({metric})',
            group_metadata=results.get('group_metadata'),
            point_sizes=point_sizes,
        )

    return results


def run_nmds(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run NMDS and return structured results."""
    params = parameters or {}
    metric = params.get('metric', 'braycurtis')
    n_components = params.get('n_components', 2)
    engine = AnalysisEngine()
    dist_matrix = engine.beta_diversity(df, distance=metric)
    nmds_result = engine.nmds(dist_matrix, n_components=n_components)

    results = {
        'metric': metric,
        'coordinates': nmds_result['coordinates'].to_dict(orient='index'),
        'stress': nmds_result['stress'],
        'stress_type': nmds_result['stress_type'],
        'raw_stress': nmds_result['raw_stress'],
        'n_components': n_components,
    }

    group_column = params.get('group_column')
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results['group_metadata'] = {
            str(s): str(metadata_df.loc[s, group_column])
            for s in nmds_result['coordinates'].index
            if s in metadata_df.index
        }

    coords_df = nmds_result['coordinates']
    if 'NMDS1' in coords_df.columns and 'NMDS2' in coords_df.columns:
        stress = results['stress']
        stress_txt = f'{stress:.4f}' if isinstance(stress, (int, float)) else 'n/a'
        results['plot_data'] = _ordination_scatter_plot(
            coords_df, 'NMDS1', 'NMDS2',
            xlabel='NMDS1',
            ylabel='NMDS2',
            title=f'Microbiome NMDS ({metric}, stress={stress_txt})',
            group_metadata=results.get('group_metadata'),
        )

    return results


def run_differential_analysis(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run differential abundance analysis and return structured results."""
    params = parameters or {}
    group_column = params.get('group_column')
    test_method = params.get('test_method', 'mannwhitney')
    pvalue_threshold = params.get('pvalue_threshold', 0.05)

    if metadata_df is None or group_column not in metadata_df.columns:
        return {'error': 'Metadata with group column required for differential analysis'}

    groups = metadata_df[group_column].dropna().unique()

    # ANCOM-BC: requires exactly 2 groups
    if test_method in ('ancombc', 'ANCOM-BC'):
        if len(groups) != 2:
            return {'error': f'ANCOM-BC requires exactly 2 groups, found {len(groups)}'}
        from app.services.r_analysis import run_ancombc
        zero_cut = params.get('zero_cut', 0.9)
        lib_cut = params.get('lib_cut', 0)
        struc_zero = params.get('struc_zero', True)
        p_adj_method = params.get('p_adj_method', 'BH')
        diff_df = run_ancombc(df, metadata_df, group_column, zero_cut, lib_cut, struc_zero, p_adj_method)
        if 'error' in diff_df.columns:
            return {'error': str(diff_df['error'].iloc[0])}
        return {
            'group_column': group_column,
            'test_method': 'ANCOM-BC',
            'zero_cut': zero_cut,
            'lib_cut': lib_cut,
            'struc_zero': struc_zero,
            'significant_features': diff_df[diff_df['diff_abn'] == True].to_dict(orient='records') if 'diff_abn' in diff_df.columns else [],
            'all_features': diff_df.to_dict(orient='records'),
        }

    # MaAsLin3: multivariate association, does not require exactly 2 groups
    if test_method in ('maaslin3', 'MaAsLin3'):
        from app.services.r_analysis import run_maaslin3
        fixed_effects = params.get('fixed_effects', [group_column])
        random_effects = params.get('random_effects', None)
        normalization = params.get('normalization', 'TSS')
        transform = params.get('transform', 'LOG')
        diff_df = run_maaslin3(df, metadata_df, fixed_effects, random_effects, group_column, normalization, transform)
        if 'error' in diff_df.columns:
            return {'error': str(diff_df['error'].iloc[0])}
        return {
            'test_method': 'MaAsLin3',
            'normalization': normalization,
            'transform': transform,
            'fixed_effects': fixed_effects,
            'significant_features': diff_df[diff_df['padj'] < pvalue_threshold].to_dict(orient='records') if 'padj' in diff_df.columns else [],
            'all_features': diff_df.to_dict(orient='records'),
        }

    elif test_method == 'lefse':
        from app.services.r_analysis import run_lefse
        engine = AnalysisEngine()
        lda_threshold = params.get('lda_threshold', 2.0)
        lefse_df = run_lefse(df, metadata_df, group_column, lda_threshold=lda_threshold)
        result_data = {
            'test_method': 'LEfSe',
            'group_column': group_column,
            'lda_threshold': lda_threshold,
            'significant_features': lefse_df[lefse_df['lda_score'].abs() >= lda_threshold].to_dict(orient='records') if 'lda_score' in lefse_df.columns else [],
            'all_features': lefse_df.to_dict(orient='records'),
        }
        if 'lda_score' in lefse_df.columns:
            plot_data = engine.plotly_lefse_bar(lefse_df, lda_threshold)
            result_data['plot_data'] = plot_data
        return result_data

    engine = AnalysisEngine()
    try:
        g1, g2 = resolve_comparison_groups(
            metadata_df,
            group_column,
            params.get('comparisons'),
            params.get('reference_group'),
        )
    except ValueError as e:
        return {'error': str(e)}

    if test_method in ('ttest', 't-test'):
        diff_df = engine.differential_ttest(df, metadata_df, group_column, g1, g2)
    elif test_method in ('wilcoxon', 'mannwhitney'):
        diff_df = engine.differential_wilcoxon(df, metadata_df, group_column, g1, g2)
    else:
        diff_df = engine.differential_wilcoxon(df, metadata_df, group_column, g1, g2)

    return {
        'group_column': group_column,
        'group1': str(g1),
        'group2': str(g2),
        'reference_group': str(g1),
        'test_method': test_method,
        # log2FC is computed as log2(mean(group2) / mean(group1)): positive means
        # enriched in group2 relative to the reference.
        'fold_change_direction': f'{g2} vs {g1}',
        'significant_features': diff_df[diff_df['pvalue'] < pvalue_threshold].to_dict(orient='records'),
        'all_features': diff_df.to_dict(orient='records'),
    }


def run_permanova(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run PERMANOVA and return structured results."""
    params = parameters or {}
    metric = params.get('metric', 'braycurtis')
    group_column = params.get('group_column')
    n_permutations = params.get('n_permutations', 999)

    if metadata_df is None or group_column not in metadata_df.columns:
        return {'error': 'Metadata with group column required for PERMANOVA'}

    engine = AnalysisEngine()
    dist_matrix = engine.beta_diversity(df, distance=metric)
    result = engine.permanova(dist_matrix, metadata_df, group_column, n_permutations=n_permutations)
    return result


def run_anosim(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run ANOSIM and return structured results."""
    params = parameters or {}
    metric = params.get('metric', 'braycurtis')
    group_column = params.get('group_column')
    n_permutations = params.get('n_permutations', 999)

    if metadata_df is None or group_column not in metadata_df.columns:
        return {'error': 'Metadata with group column required for ANOSIM'}

    engine = AnalysisEngine()
    dist_matrix = engine.beta_diversity(df, distance=metric)
    result = engine.anosim(dist_matrix, metadata_df, group_column, n_permutations=n_permutations)
    return result


def run_random_forest(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run Random Forest and return structured results."""
    params = parameters or {}
    group_column = params.get('group_column')
    n_estimators = params.get('n_estimators', 500)

    if metadata_df is None or group_column not in metadata_df.columns:
        return {'error': 'Metadata with group column required for Random Forest'}

    engine = AnalysisEngine()
    return engine.random_forest(df, metadata_df, group_column, n_estimators=n_estimators)


def run_heatmap(
    df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run heatmap generation and return structured results."""
    params = parameters or {}
    top_n = params.get('top_n', 50)
    cluster_rows = params.get('cluster_rows', True)
    cluster_cols = params.get('cluster_cols', True)
    normalize = params.get('normalize', 'zscore')

    # Select top features
    if len(df) > top_n:
        feature_var = df.var(axis=1).sort_values(ascending=False)
        top_features = feature_var.head(top_n).index
        df_plot = df.loc[top_features]
    else:
        df_plot = df.copy()

    # Normalize
    if normalize == 'zscore':
        df_norm = df_plot.T.apply(lambda x: (x - x.mean()) / (x.std() + 1e-10), axis=0).T
    elif normalize == 'relative':
        df_norm = df_plot.div(df_plot.sum(axis=0), axis=1).fillna(0)
    elif normalize == 'log':
        df_norm = np.log10(df_plot + 1e-10)
    else:
        df_norm = df_plot.copy()

    # Clustering
    row_order = list(df_norm.index)
    col_order = list(df_norm.columns)

    if cluster_rows and len(df_norm) > 1:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import pdist
        try:
            row_dist = pdist(df_norm.values)
            row_linkage = linkage(row_dist, method='average')
            row_order = [df_norm.index[i] for i in leaves_list(row_linkage)]
        except Exception as e:
            logger.warning(f"Row clustering failed: {e}")

    if cluster_cols and len(df_norm.columns) > 1:
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import pdist
        try:
            col_dist = pdist(df_norm.T.values)
            col_linkage = linkage(col_dist, method='average')
            col_order = [df_norm.columns[i] for i in leaves_list(col_linkage)]
        except Exception as e:
            logger.warning(f"Column clustering failed: {e}")

    df_ordered = df_norm.loc[row_order, col_order]

    results = {
        'matrix': df_ordered.to_dict(),
        'row_order': row_order,
        'col_order': col_order,
        'normalize': normalize,
    }

    group_column = params.get('group_column')
    if metadata_df is not None and group_column and group_column in metadata_df.columns:
        results['group_metadata'] = {
            str(s): str(metadata_df.loc[s, group_column])
            for s in col_order
            if s in metadata_df.index
        }

    return results


def run_network_analysis(df, metadata_df=None, parameters=None):
    from app.services.network_analysis import run_network_analysis as _run
    return _run(df, **(parameters or {}))


def run_correlation_analysis(df, metadata_df=None, parameters=None):
    from app.services.correlation_analysis import run_correlation_analysis as _run
    return _run(df, metadata_df, parameters)


def run_pathway_analysis(df, metadata_df=None, parameters=None):
    from app.services.functional_analysis import run_pathway_analysis as _run
    return _run(df, diff_result_data=None, parameters=parameters)


def run_functional_prediction(df, metadata_df=None, parameters=None):
    from app.services.functional_prediction import run_functional_prediction as _run
    return _run(df, metadata_df, parameters)


def run_phylogenetic_analysis(df, metadata_df=None, parameters=None):
    from app.services.phylogenetic_analysis import run_phylogenetic_analysis as _run
    return _run(df, metadata_df, parameters)


def run_hierarchical_clustering(df, metadata_df=None, parameters=None):
    from app.services.hierarchical_clustering import run_hierarchical_clustering as _run
    return _run(df, metadata_df, parameters)

def run_cross_omics_analysis(df1, df2=None, metadata_df=None, parameters=None):
    from app.services.cross_omics import run_cross_omics_analysis as _run
    return _run(df1, df2, metadata_df, parameters)

def run_advanced_dimred(df, metadata_df=None, parameters=None):
    from app.services.advanced_dimred import run_advanced_dimred as _run
    return _run(df, metadata_df, parameters)

def run_source_tracking_analysis(df, metadata_df=None, parameters=None):
    from app.services.source_tracking import run_source_tracking_analysis as _run
    return _run(df, metadata_df, parameters)


def run_metabolomics_analysis(df, metadata_df=None, parameters=None):
    from app.services.metabolomics_analysis import run_metabolomics_analysis as _run
    return _run(df, metadata_df, parameters)


def run_sparse_cca_analysis(microbiome_df, metabolome_df=None, metadata_df=None, parameters=None):
    from app.services.sparse_cca import run_sparse_cca_analysis as _run
    return _run(microbiome_df, metabolome_df, metadata_df, parameters)


def run_rda_analysis(microbiome_df, metabolome_df=None, metadata_df=None, parameters=None):
    from app.services.rda_analysis import run_rda_analysis as _run
    return _run(microbiome_df, metabolome_df, metadata_df, parameters)


def run_o2pls_analysis(microbiome_df, metabolome_df=None, metadata_df=None, parameters=None):
    from app.services.o2pls_analysis import run_o2pls_analysis as _run
    return _run(microbiome_df, metabolome_df, metadata_df, parameters)

    from app.services.source_tracking import run_source_tracking_analysis as _run
    return _run(df, metadata_df, parameters)
