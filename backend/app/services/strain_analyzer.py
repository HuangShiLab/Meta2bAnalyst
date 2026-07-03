"""
Meta2bAnalyst - Strain-Level Analyzer
Handles Strain2bScan and Tag2bMap output analysis with strain-specific metrics.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.spatial.distance import pdist, squareform
from scipy.stats import entropy, mannwhitneyu

logger = logging.getLogger(__name__)


class StrainAnalyzer:
    """Analyzer for strain-level microbiome data."""

    def _filter_strain_df(
        self,
        strain_df: pd.DataFrame,
        species: Optional[str] = None,
    ) -> pd.DataFrame:
        """Filter strain DataFrame by optional species."""
        df = strain_df.copy()
        if species is not None and 'species' in df.columns:
            df = df[df['species'] == species].copy()
        return df

    def _to_strain_wide(
        self,
        strain_df: pd.DataFrame,
        species: Optional[str] = None,
    ) -> pd.DataFrame:
        """Convert long-format strain data to wide (sample x strain) per species."""
        df = self._filter_strain_df(strain_df, species=species)
        if df.empty:
            return pd.DataFrame()

        # Create unique strain identifiers (species + strain)
        if 'species' in df.columns and 'strain' in df.columns:
            df['strain_id'] = df['species'] + '_' + df['strain']
        elif 'strain' in df.columns:
            df['strain_id'] = df['strain']
        else:
            raise ValueError("DataFrame must contain 'strain' column")

        wide = df.pivot_table(
            index='sample_id',
            columns='strain_id',
            values='abundance',
            aggfunc='sum',
            fill_value=0,
        )
        return wide

    def strain_richness(
        self,
        strain_df: pd.DataFrame,
        species: Optional[str] = None,
    ) -> pd.DataFrame:
        """Calculate strain richness per sample.

        Richness is the number of distinct strains (with abundance > 0) per sample.

        Args:
            strain_df: Long-format strain DataFrame.
            species: Optional species filter.

        Returns:
            DataFrame with columns: sample_id, strain_richness.
        """
        df = self._filter_strain_df(strain_df, species=species)
        if df.empty:
            return pd.DataFrame(columns=['sample_id', 'strain_richness'])

        richness = df.groupby('sample_id')['strain'].nunique().reset_index()
        richness.columns = ['sample_id', 'strain_richness']
        return richness

    def strain_alpha_diversity(
        self,
        strain_df: pd.DataFrame,
        metric: str = 'shannon',
        species: Optional[str] = None,
    ) -> pd.DataFrame:
        """Calculate strain-level alpha diversity per sample.

        Metrics:
            - shannon: Shannon entropy.
            - simpson: Simpson diversity (1 - sum(p^2)).
            - observed: Observed strain richness.

        Args:
            strain_df: Long-format strain DataFrame.
            metric: Diversity metric name.
            species: Optional species filter.

        Returns:
            DataFrame with columns: sample_id, <metric>_diversity.
        """
        wide = self._to_strain_wide(strain_df, species=species)
        if wide.empty:
            return pd.DataFrame(columns=['sample_id', f'{metric}_diversity'])

        results = []
        for sample in wide.index:
            values = wide.loc[sample].values
            values = values[values > 0]

            if len(values) == 0:
                div_val = 0.0
            elif metric == 'shannon':
                proportions = values / values.sum()
                div_val = float(-np.sum(proportions * np.log(proportions + 1e-10)))
            elif metric == 'simpson':
                proportions = values / values.sum()
                div_val = float(1 - np.sum(proportions ** 2))
            elif metric == 'observed':
                div_val = int(len(values))
            else:
                div_val = 0.0

            results.append({
                'sample_id': sample,
                f'{metric}_diversity': div_val,
            })

        return pd.DataFrame(results)

    def strain_beta_diversity(
        self,
        strain_df: pd.DataFrame,
        distance: str = 'braycurtis',
        species: Optional[str] = None,
    ) -> pd.DataFrame:
        """Calculate strain-level beta diversity distance matrix.

        Args:
            strain_df: Long-format strain DataFrame.
            distance: Distance metric ('braycurtis', 'jaccard', 'euclidean').
            species: Optional species filter.

        Returns:
            Square distance matrix DataFrame (samples x samples).
        """
        wide = self._to_strain_wide(strain_df, species=species)
        if wide.empty or len(wide) < 2:
            return pd.DataFrame()

        metric_map = {
            'braycurtis': 'braycurtis',
            'jaccard': 'jaccard',
            'euclidean': 'euclidean',
        }
        scipy_metric = metric_map.get(distance, 'braycurtis')

        distances = pdist(wide.values, metric=scipy_metric)
        dist_matrix = squareform(distances)
        return pd.DataFrame(dist_matrix, index=wide.index, columns=wide.index)

    def strain_differential(
        self,
        strain_df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        species: Optional[str] = None,
        within_species: bool = True,
    ) -> pd.DataFrame:
        """Strain-level differential abundance analysis.

        Compares strain abundance between metadata groups using Wilcoxon rank-sum test.

        Args:
            strain_df: Long-format strain DataFrame.
            metadata: Metadata DataFrame with sample grouping.
            group_var: Grouping variable column name.
            species: Optional species filter.
            within_species: If True, compare strains within each species separately.

        Returns:
            DataFrame with differential statistics per strain.
        """
        df = self._filter_strain_df(strain_df, species=species)
        if df.empty:
            return pd.DataFrame()

        groups = metadata[group_var].dropna().unique()
        if len(groups) != 2:
            raise ValueError(f"Strain differential requires exactly 2 groups, found {len(groups)}")

        g1, g2 = groups[0], groups[1]
        g1_samples = metadata[metadata[group_var] == g1].index.intersection(df['sample_id'].unique())
        g2_samples = metadata[metadata[group_var] == g2].index.intersection(df['sample_id'].unique())

        results = []
        species_list = [species] if species is not None else df['species'].unique()

        for sp in species_list:
            sp_df = df[df['species'] == sp] if 'species' in df.columns else df.copy()
            strains = sp_df['strain'].unique()

            for st in strains:
                st_df = sp_df[sp_df['strain'] == st]
                g1_vals = st_df[st_df['sample_id'].isin(g1_samples)]['abundance'].dropna().astype(float).values
                g2_vals = st_df[st_df['sample_id'].isin(g2_samples)]['abundance'].dropna().astype(float).values

                if len(g1_vals) == 0 or len(g2_vals) == 0:
                    continue

                g1_mean = g1_vals.mean() + 1e-10
                g2_mean = g2_vals.mean() + 1e-10
                log2fc = np.log2(g2_mean / g1_mean)

                try:
                    stat, pvalue = mannwhitneyu(g1_vals, g2_vals, alternative='two-sided')
                except Exception as e:
                    logger.warning(f"Wilcoxon test failed for strain {st}: {e}")
                    continue

                result = {
                    'species': sp if 'species' in df.columns else 'NA',
                    'strain': st,
                    'log2FC': float(log2fc),
                    'pvalue': float(pvalue),
                    'mean_group1': float(g1_mean),
                    'mean_group2': float(g2_mean),
                    'n_group1': len(g1_vals),
                    'n_group2': len(g2_vals),
                }
                results.append(result)

        result_df = pd.DataFrame(results)
        if len(result_df) > 0:
            from scipy.stats import rankdata

            pvalues = result_df['pvalue'].values
            n = len(pvalues)
            if n > 0:
                ranks = rankdata(pvalues, method='max')
                padj = np.minimum(pvalues * n / ranks, 1.0)
                result_df['padj'] = padj
            result_df = result_df.sort_values('pvalue')

        return result_df

    def strain_dominance_index(self, strain_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate strain dominance index per sample per species.

        Dominance index = maximum strain abundance / total abundance within a species.
        High values indicate one strain dominates the species composition.

        Args:
            strain_df: Long-format strain DataFrame.

        Returns:
            DataFrame with columns: sample_id, species, max_strain, dominance_index.
        """
        if 'species' not in strain_df.columns:
            logger.warning("No 'species' column in strain data; dominance index requires species grouping.")
            return pd.DataFrame()

        results = []
        for (sample, species), group in strain_df.groupby(['sample_id', 'species']):
            total = group['abundance'].sum()
            if total == 0:
                continue
            max_abundance = group['abundance'].max()
            max_strain = group.loc[group['abundance'].idxmax(), 'strain']
            results.append({
                'sample_id': sample,
                'species': species,
                'max_strain': max_strain,
                'dominance_index': float(max_abundance / total),
                'total_abundance': float(total),
            })

        return pd.DataFrame(results)

    def strain_replacement_score(
        self,
        strain_df: pd.DataFrame,
        metadata: pd.DataFrame,
        group_var: str,
        group1: str,
        group2: str,
    ) -> float:
        """Calculate strain replacement score between two groups.

        Replacement score measures how much strains differ between groups,
        calculated as the proportion of strains unique to each group (Jaccard-like).

        Args:
            strain_df: Long-format strain DataFrame.
            metadata: Metadata DataFrame with grouping.
            group_var: Grouping variable.
            group1: First group name.
            group2: Second group name.

        Returns:
            Strain replacement score (0.0 = identical strains, 1.0 = completely different).
        """
        g1_samples = metadata[metadata[group_var] == group1].index.intersection(strain_df['sample_id'].unique())
        g2_samples = metadata[metadata[group_var] == group2].index.intersection(strain_df['sample_id'].unique())

        g1_strains = set(strain_df[strain_df['sample_id'].isin(g1_samples)]['strain'].unique())
        g2_strains = set(strain_df[strain_df['sample_id'].isin(g2_samples)]['strain'].unique())

        if len(g1_strains) == 0 and len(g2_strains) == 0:
            return 0.0

        # Jaccard distance = 1 - intersection / union
        intersection = len(g1_strains & g2_strains)
        union = len(g1_strains | g2_strains)

        if union == 0:
            return 0.0

        replacement_score = 1.0 - (intersection / union)
        return float(replacement_score)

    def plotly_strain_composition(
        self,
        strain_df: pd.DataFrame,
        species: str,
    ) -> dict:
        """Generate Plotly JSON for strain composition stacked bar chart.

        Args:
            strain_df: Long-format strain DataFrame.
            species: Species to visualize.

        Returns:
            Plotly figure JSON dict.
        """
        df = strain_df[strain_df['species'] == species].copy() if 'species' in strain_df.columns else strain_df.copy()
        if df.empty:
            return go.Figure().update_layout(title=f'No data for species {species}').to_dict()

        # Get relative abundance per sample
        sample_totals = df.groupby('sample_id')['abundance'].sum()
        df['rel_abundance'] = df.apply(lambda x: x['abundance'] / sample_totals.get(x['sample_id'], 1), axis=1)

        strains = df['strain'].unique()
        samples = df['sample_id'].unique()

        fig = go.Figure()
        for strain in strains:
            strain_data = df[df['strain'] == strain]
            abundances = []
            for sample in samples:
                val = strain_data[strain_data['sample_id'] == sample]['rel_abundance'].sum()
                abundances.append(val)
            fig.add_trace(go.Bar(
                name=str(strain),
                x=[str(s) for s in samples],
                y=abundances,
            ))

        fig.update_layout(
            barmode='stack',
            title=f'Strain Composition - {species}',
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

    def plotly_strain_heatmap(
        self,
        strain_df: pd.DataFrame,
        species: Optional[str] = None,
    ) -> dict:
        """Generate Plotly JSON for strain abundance heatmap.

        Args:
            strain_df: Long-format strain DataFrame.
            species: Optional species filter.

        Returns:
            Plotly figure JSON dict.
        """
        wide = self._to_strain_wide(strain_df, species=species)
        if wide.empty:
            return go.Figure().update_layout(title='No strain data available').to_dict()

        # Log-transform for visualization
        log_wide = np.log10(wide.replace(0, np.nan))

        fig = go.Figure(data=go.Heatmap(
            z=log_wide.values,
            x=[str(c) for c in wide.columns],
            y=[str(r) for r in wide.index],
            colorscale='YlOrRd',
            zmin=0,
        ))
        fig.update_layout(
            title='Strain Abundance Heatmap' + (f' - {species}' if species else ''),
            xaxis_title='Strains',
            yaxis_title='Samples',
            xaxis={'tickangle': -45},
        )
        return fig.to_dict()


# ─────────────────────────────── Module-level convenience functions


def parse_strain2bscan_output(df: pd.DataFrame) -> pd.DataFrame:
    """Parse Strain2bScan output into a structured DataFrame."""
    df.columns = [c.lower() for c in df.columns]
    return df


def filter_strains_by_ani(
    df: pd.DataFrame,
    min_ani: float = 95.0,
    max_ani: float = 100.0,
) -> pd.DataFrame:
    """Filter strain assignments by ANI threshold."""
    ani_col = [c for c in df.columns if 'ani' in c]
    if ani_col:
        mask = (df[ani_col[0]] >= min_ani) & (df[ani_col[0]] <= max_ani)
        return df[mask].copy()
    return df.copy()


def filter_strains_by_coverage(
    df: pd.DataFrame,
    min_coverage: float = 0.8,
) -> pd.DataFrame:
    """Filter strain assignments by coverage threshold."""
    cov_col = [c for c in df.columns if 'coverage' in c or 'cov' in c]
    if cov_col:
        mask = df[cov_col[0]] >= min_coverage
        return df[mask].copy()
    return df.copy()


def run_strain_profile(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], int]:
    """Generate strain profile for a target species."""
    params = parameters or {}
    min_ani = params.get('min_ani', 95.0)
    min_coverage = params.get('min_coverage', 0.8)

    df = parse_strain2bscan_output(df)
    species_col = [c for c in df.columns if 'species' in c]
    if species_col:
        df_species = df[df[species_col[0]] == species].copy()
    else:
        df_species = df.copy()

    df_species = filter_strains_by_ani(df_species, min_ani=min_ani)
    df_species = filter_strains_by_coverage(df_species, min_coverage=min_coverage)

    strain_count = len(df_species)
    strain_col = [c for c in df_species.columns if 'strain' in c]
    strain_names = df_species[strain_col[0]].tolist() if strain_col else []

    ani_col = [c for c in df_species.columns if 'ani' in c]
    cov_col = [c for c in df_species.columns if 'coverage' in c]

    stats = {
        'species': species,
        'strain_count': strain_count,
        'strain_names': [str(s) for s in strain_names],
    }

    if ani_col:
        stats['ani'] = {
            'mean': float(df_species[ani_col[0]].mean()),
            'median': float(df_species[ani_col[0]].median()),
            'min': float(df_species[ani_col[0]].min()),
            'max': float(df_species[ani_col[0]].max()),
            'std': float(df_species[ani_col[0]].std()),
        }

    if cov_col:
        stats['coverage'] = {
            'mean': float(df_species[cov_col[0]].mean()),
            'median': float(df_species[cov_col[0]].median()),
            'min': float(df_species[cov_col[0]].min()),
            'max': float(df_species[cov_col[0]].max()),
            'std': float(df_species[cov_col[0]].std()),
        }

    return {'strain_profile': stats}, strain_count


def run_strain_comparison(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compare strain profiles between groups or samples."""
    params = parameters or {}
    group_column = params.get('group_column')

    profile, strain_count = run_strain_profile(df, species, parameters)

    if not group_column or group_column not in df.columns:
        return profile

    groups = df[group_column].dropna().unique().tolist()
    group_profiles = {}

    for group in groups:
        group_df = df[df[group_column] == group]
        group_profile, _ = run_strain_profile(group_df, species, parameters)
        group_profiles[str(group)] = group_profile['strain_profile']

    return {
        'strain_profile': profile['strain_profile'],
        'group_profiles': group_profiles,
        'groups': [str(g) for g in groups],
    }


def run_ani_matrix(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate ANI distance matrix between strains."""
    params = parameters or {}
    min_ani = params.get('min_ani', 95.0)

    df = parse_strain2bscan_output(df)
    species_col = [c for c in df.columns if 'species' in c]
    if species_col:
        df_species = df[df[species_col[0]] == species].copy()
    else:
        df_species = df.copy()

    df_species = filter_strains_by_ani(df_species, min_ani=min_ani)

    strain_col = [c for c in df_species.columns if 'strain' in c]
    if not strain_col:
        return {'error': 'No strain column found in data'}

    strains = df_species[strain_col[0]].unique().tolist()
    n = len(strains)
    ani_matrix = np.zeros((n, n))

    ani_col = [c for c in df_species.columns if 'ani' in c]
    if ani_col:
        for i, strain_i in enumerate(strains):
            for j, strain_j in enumerate(strains):
                if i == j:
                    ani_matrix[i, j] = 100.0
                else:
                    ani_i = df_species[df_species[strain_col[0]] == strain_i][ani_col[0]].mean()
                    ani_j = df_species[df_species[strain_col[0]] == strain_j][ani_col[0]].mean()
                    ani_matrix[i, j] = (ani_i + ani_j) / 2
    else:
        np.fill_diagonal(ani_matrix, 100.0)

    dist_matrix = 100.0 - ani_matrix

    return {
        'species': species,
        'strains': [str(s) for s in strains],
        'ani_matrix': ani_matrix.tolist(),
        'distance_matrix': dist_matrix.tolist(),
        'strain_count': n,
    }


def run_strain_pcoa(
    df: pd.DataFrame,
    species: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run PCoA on strain-level ANI distances."""
    ani_result = run_ani_matrix(df, species, parameters)
    if 'error' in ani_result:
        return ani_result

    dist_matrix = np.array(ani_result['distance_matrix'])
    strains = ani_result['strains']

    n = dist_matrix.shape[0]
    H = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * H @ (dist_matrix ** 2) @ H

    eigenvalues, eigenvectors = np.linalg.eigh(B)
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    positive_mask = eigenvalues > 0
    eigenvalues = eigenvalues[positive_mask][:3]
    eigenvectors = eigenvectors[:, positive_mask][:, :3]

    coordinates = eigenvectors * np.sqrt(eigenvalues)
    total_variance = np.sum(eigenvalues[eigenvalues > 0])
    variance_explained = (
        [(e / total_variance) * 100 for e in eigenvalues]
        if total_variance > 0
        else []
    )

    return {
        'species': species,
        'strains': strains,
        'coordinates': {
            strain: coords.tolist()
            for strain, coords in zip(strains, coordinates)
        },
        'eigenvalues': eigenvalues.tolist(),
        'variance_explained': variance_explained,
    }
