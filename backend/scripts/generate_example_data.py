#!/usr/bin/env python3
"""
Generate 5 example datasets for Meta2bAnalyst.

Datasets:
1. 2bRAD-M species abundance table (gut microbiome)
2. 2bRAD-M functional gene table (KO)
3. Strain2bScan strain-level data
4. Tag2bMap output (with ANI)
5. QIIME BIOM format example
"""
import os
import random
import numpy as np
import pandas as pd
from pathlib import Path

random.seed(42)
np.random.seed(42)


# ─────────────────────────────── Common GTDB species

GTDB_GUT_SPECIES = [
    "s__Escherichia_coli", "s__Bacteroides_fragilis", "s__Bacteroides_thetaiotaomicron",
    "s__Bacteroides_uniformis", "s__Bacteroides_vulgatus", "s__Prevotella_copri",
    "s__Faecalibacterium_prausnitzii", "s__Roseburia_intestinalis", "s__Eubacterium_rectale",
    "s__Akkermansia_muciniphila", "s__Ruminococcus_bromii", "s__Ruminococcus_torques",
    "s__Bifidobacterium_longum", "s__Bifidobacterium_adolescentis", "s__Streptococcus_salivarius",
    "s__Lactobacillus_rhamnosus", "s__Lactobacillus_reuteri", "s__Clostridium_bolteae",
    "s__Clostridium_innocuum", "s__Enterococcus_faecalis", "s__Enterococcus_faecium",
    "s__Klebsiella_pneumoniae", "s__Alistipes_finegoldii", "s__Alistipes_putredinis",
    "s__Parabacteroides_distasonis", "s__Parabacteroides_merdae", "s__Phocaeicola_dorei",
    "s__Phocaeicola_vulgatus", "s__Dialister_invisus", "s__Methanobrevibacter_smithii",
    "s__Coprococcus_comes", "s__Dorea_longicatena", "s__Anaerostipes_hadrus",
    "s__Blautia_wexlerae", "s__Blautia_obeum", "s__Collinsella_aerofaciens",
    "s__Eggerthella_lenta", "s__Fusobacterium_nucleatum", "s__Hungatella_hathewayi",
    "s__Intestinibacter_bartlettii", "s__Megasphaera_elsdenii", "s__Mitsuokella_multacida",
    "s__Odoribacter_splanchnicus", "s__Pseudoflavonifractor_capillosus",
    "s__Subdoligranulum_variabile", "s__Veillonella_parvula", "s__Veillonella_atypica",
    "s__Catenibacterium_mitsuokai", "s__Lachnospira_pectinoschiza", "s__Coprococcus_catus",
    "s__Dorea_formicigenerans", "s__Butyricicoccus_pullicaecorum", "s__Faecalibacterium_sp",
    "s__Ruminococcus_gnavus", "s__Ruminococcus_lactaris", "s__Eubacterium_hallii",
    "s__Eubacterium_cylindroides", "s__Anaerotruncus_colihominis", "s__Coprobacillus_cateniformis",
    "s__Turicibacter_sanguinis", "s__Streptococcus_thermophilus", "s__Lactococcus_lactis",
    "s__Bacillus_subtilis", "s__Staphylococcus_aureus", "s__Staphylococcus_epidermidis",
    "s__Cutibacterium_acnes", "s__Corynebacterium_accolens", "s__Propionibacterium_freudenreichii",
    "s__Pseudomonas_aeruginosa", "s__Pseudomonas_putida", "s__Acinetobacter_baumannii",
    "s__Haemophilus_influenzae", "s__Neisseria_meningitidis", "s__Moraxella_catarrhalis",
    "s__Campylobacter_jejuni", "s__Helicobacter_pylori", "s__Salmonella_enterica",
    "s__Shigella_flexneri", "s__Vibrio_cholerae", "s__Yersinia_enterocolitica",
    "s__Lactobacillus_acidophilus", "s__Lactobacillus_casei", "s__Lactobacillus_plantarum",
    "s__Bifidobacterium_bifidum", "s__Bifidobacterium_breve", "s__Bifidobacterium_pseudocatenulatum",
    "s__Akkermansia_sp", "s__Barnesiella_intestinihominis", "s__Odoribacter_laneus",
    "s__Paraprevotella_clara", "s__Phascolarctobacterium_faecium", "s__Sutterella_wadsworthensis",
    "s__Bilophila_wadsworthia", "s__Desulfovibrio_desulfuricans", "s__Desulfovibrio_piger",
    "s__Helicobacter_bilis", "s__Methanosphaera_stadtmanae", "s__Methanomassiliicoccus_luminyensis",
    "s__Erysipelatoclostridium_ramosum", "s__Erysipelotrichaceae_bacterium", "s__Holdemanella_biformis",
]


# ─────────────────────────────── KO identifiers

KO_FUNCTIONS = [f"K{str(i).zfill(5)}" for i in range(1, 51)]


# ─────────────────────────────── Strain names per species

STRAIN_POOL = {
    "s__Escherichia_coli": ["EC_001", "EC_002", "EC_003", "EC_004", "EC_005", "EC_006", "EC_007"],
    "s__Bacteroides_fragilis": ["BF_001", "BF_002", "BF_003", "BF_004"],
    "s__Bacteroides_thetaiotaomicron": ["BT_001", "BT_002", "BT_003"],
    "s__Faecalibacterium_prausnitzii": ["FP_001", "FP_002", "FP_003", "FP_004", "FP_005"],
    "s__Akkermansia_muciniphila": ["AM_001", "AM_002", "AM_003"],
    "s__Prevotella_copri": ["PC_001", "PC_002", "PC_003", "PC_004"],
    "s__Roseburia_intestinalis": ["RI_001", "RI_002", "RI_003"],
    "s__Bifidobacterium_longum": ["BL_001", "BL_002", "BL_003"],
    "s__Streptococcus_salivarius": ["SS_001", "SS_002"],
    "s__Clostridium_bolteae": ["CB_001", "CB_002"],
    "s__Ruminococcus_bromii": ["RB_001", "RB_002", "RB_003"],
    "s__Parabacteroides_distasonis": ["PD_001", "PD_002", "PD_003"],
    "s__Eubacterium_rectale": ["ER_001", "ER_002", "ER_003"],
    "s__Klebsiella_pneumoniae": ["KP_001", "KP_002"],
    "s__Enterococcus_faecalis": ["EF_001", "EF_002"],
    "s__Lactobacillus_rhamnosus": ["LR_001", "LR_002", "LR_003"],
    "s__Bacteroides_vulgatus": ["BV_001", "BV_002", "BV_003"],
    "s__Alistipes_finegoldii": ["AF_001", "AF_002"],
    "s__Dialister_invisus": ["DI_001", "DI_002"],
    "s__Coprococcus_comes": ["CC_001", "CC_002"],
}


# ─────────────────────────────── Helper functions

def _make_metadata(n_samples=30, output_dir='examples'):
    """Generate metadata DataFrame."""
    half = n_samples // 2
    data = {
        'sample_id': [f'S{i:02d}' for i in range(1, n_samples + 1)],
        'group': ['Control'] * half + ['Treatment'] * half,
        'age': np.random.randint(20, 65, n_samples).tolist(),
        'sex': random.choices(['M', 'F'], k=n_samples),
        'bmi': np.round(np.random.normal(24, 4, n_samples), 1).tolist(),
    }
    df = pd.DataFrame(data)
    df.set_index('sample_id', inplace=True)
    return df


def _generate_counts(n_features, n_samples, diff_indices, diff_directions, diff_magnitude,
                     base_mean=500, sparsity=0.3, max_count=10000):
    """Generate sparse count matrix with group differences."""
    half = n_samples // 2
    counts = np.zeros((n_features, n_samples), dtype=int)

    for i in range(n_features):
        # Base abundance
        mean_abund = np.random.lognormal(np.log(base_mean), 1.0)
        for j in range(n_samples):
            if random.random() < sparsity:
                counts[i, j] = 0
            else:
                counts[i, j] = min(np.random.poisson(mean_abund), max_count)

    # Apply differential effects
    for idx, direction, mag in zip(diff_indices, diff_directions, diff_magnitude):
        if direction == 'up':  # higher in Treatment
            for j in range(half, n_samples):
                if counts[idx, j] > 0:
                    counts[idx, j] = min(int(counts[idx, j] * mag), max_count)
        else:  # higher in Control
            for j in range(half):
                if counts[idx, j] > 0:
                    counts[idx, j] = min(int(counts[idx, j] * mag), max_count)

    return counts


def _write_csv_with_header(df, filepath, header_name='#NAME'):
    """Write DataFrame with #NAME header row."""
    out_path = Path(filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(header_name)
        for col in df.columns:
            f.write(',' + str(col))
        f.write('\n')
        df.to_csv(f, header=False)


# ─────────────────────────────── Dataset 1: 2bRAD-M Species

def generate_2brad_m_species(n_samples=30, n_species=100, n_diff=20, output_dir='examples'):
    """Generate 2bRAD-M species abundance table."""
    species = GTDB_GUT_SPECIES[:n_species]
    samples = [f'S{i:02d}' for i in range(1, n_samples + 1)]
    metadata = _make_metadata(n_samples, output_dir)

    # Select differential species
    diff_indices = random.sample(range(n_species), n_diff)
    diff_directions = random.choices(['up', 'down'], k=n_diff)
    diff_magnitudes = [random.uniform(2.0, 5.0) for _ in range(n_diff)]

    counts = _generate_counts(n_species, n_samples, diff_indices, diff_directions, diff_magnitudes)
    df = pd.DataFrame(counts, index=species, columns=samples)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv_with_header(df, out_dir / '2brad_m_species.csv')
    metadata.to_csv(out_dir / 'metadata_gut.csv')
    return df, metadata


# ─────────────────────────────── Dataset 2: 2bRAD-M Function (KO)

def generate_2brad_m_function(n_samples=30, n_kos=50, n_diff=15, output_dir='examples'):
    """Generate 2bRAD-M functional gene table (KO)."""
    kos = KO_FUNCTIONS[:n_kos]
    samples = [f'S{i:02d}' for i in range(1, n_samples + 1)]

    diff_indices = random.sample(range(n_kos), n_diff)
    diff_directions = random.choices(['up', 'down'], k=n_diff)
    diff_magnitudes = [random.uniform(2.0, 4.0) for _ in range(n_diff)]

    counts = _generate_counts(n_kos, n_samples, diff_indices, diff_directions, diff_magnitudes,
                              base_mean=200, sparsity=0.4, max_count=5000)
    df = pd.DataFrame(counts, index=kos, columns=samples)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv_with_header(df, out_dir / '2brad_m_function.csv')
    return df


# ─────────────────────────────── Dataset 3: Strain2bScan

def generate_strain2bscan(n_samples=30, n_species=5, output_dir='examples'):
    """Generate Strain2bScan strain-level data (long format)."""
    samples = [f'S{i:02d}' for i in range(1, n_samples + 1)]
    half = n_samples // 2
    selected_species = list(STRAIN_POOL.keys())[:n_species]

    rows = []
    for sample in samples:
        group = 'Control' if samples.index(sample) < half else 'Treatment'
        for sp in selected_species:
            strains = STRAIN_POOL[sp]
            # Different strain composition in different groups
            if group == 'Treatment' and sp in ['s__Escherichia_coli', 's__Akkermansia_muciniphila']:
                # Treatment group has different dominant strains
                weights = [0.05] * len(strains)
                weights[-1] = 0.3  # last strain dominates
                weights[-2] = 0.2
            else:
                weights = [0.2] * len(strains)
                weights[0] = 0.4  # first strain dominates

            weights = np.array(weights) / sum(weights)
            for strain, w in zip(strains, weights):
                abundance = max(0, int(np.random.poisson(1000 * w) + np.random.normal(0, 50)))
                if abundance > 0:
                    rows.append({
                        'sample_id': sample,
                        'species': sp,
                        'strain': strain,
                        'abundance': abundance,
                    })

    df = pd.DataFrame(rows)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / 'strain2bscan_output.csv', index=False)
    return df


# ─────────────────────────────── Dataset 4: Tag2bMap

def generate_tag2bmap(n_samples=30, n_species=5, output_dir='examples'):
    """Generate Tag2bMap output with ANI and coverage."""
    samples = [f'S{i:02d}' for i in range(1, n_samples + 1)]
    half = n_samples // 2
    selected_species = list(STRAIN_POOL.keys())[:n_species]

    rows = []
    for sample in samples:
        group = 'Control' if samples.index(sample) < half else 'Treatment'
        for sp in selected_species:
            strains = STRAIN_POOL[sp]
            if group == 'Treatment' and sp in ['s__Escherichia_coli', 's__Akkermansia_muciniphila']:
                weights = [0.05] * len(strains)
                weights[-1] = 0.3
                weights[-2] = 0.2
            else:
                weights = [0.2] * len(strains)
                weights[0] = 0.4

            weights = np.array(weights) / sum(weights)
            for strain, w in zip(strains, weights):
                abundance = max(0, int(np.random.poisson(1000 * w) + np.random.normal(0, 50)))
                if abundance > 0:
                    ani = round(random.uniform(95.0, 99.9), 2)
                    coverage = round(random.uniform(0.5, 1.0), 3)
                    rows.append({
                        'sample_id': sample,
                        'species': sp,
                        'strain': strain,
                        'abundance': abundance,
                        'ani': ani,
                        'coverage': coverage,
                    })

    df = pd.DataFrame(rows)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / 'tag2bmap_output.csv', index=False)
    return df


# ─────────────────────────────── Dataset 5: QIIME BIOM

def generate_qiime_biom(n_samples=30, n_features=100, n_diff=20, output_dir='examples'):
    """Generate QIIME BIOM format feature table."""
    samples = [f'S{i:02d}' for i in range(1, n_samples + 1)]
    metadata = _make_metadata(n_samples, output_dir)
    features = [f'ASV_{i:03d}' for i in range(1, n_features + 1)]

    diff_indices = random.sample(range(n_features), n_diff)
    diff_directions = random.choices(['up', 'down'], k=n_diff)
    diff_magnitudes = [random.uniform(2.0, 5.0) for _ in range(n_diff)]

    counts = _generate_counts(n_features, n_samples, diff_indices, diff_directions, diff_magnitudes)
    df = pd.DataFrame(counts, index=features, columns=samples)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write as CSV and TSV for compatibility
    df.to_csv(out_dir / 'qiime_feature_table.csv')
    df.to_csv(out_dir / 'qiime_feature_table.tsv', sep='\t')
    metadata.to_csv(out_dir / 'qiime_metadata.csv')

    # Try to write BIOM format
    try:
        import biom
        from biom.table import Table
        table = Table(df.values, observation_ids=df.index.tolist(), sample_ids=df.columns.tolist())
        with open(out_dir / 'qiime_feature_table.biom', 'w') as f:
            table.to_json('Meta2bAnalyst', f)
        print(f"  Created BIOM file: {out_dir / 'qiime_feature_table.biom'}")
    except Exception as e:
        print(f"  BIOM creation skipped (biom library issue: {e})")

    return df, metadata


# ─────────────────────────────── Generate all

def generate_all_examples():
    """Generate all example datasets."""
    out_dir = Path('examples')
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Generating Meta2bAnalyst Example Datasets")
    print("=" * 60)

    print("\n1. 2bRAD-M Species Abundance (gut microbiome)")
    df1, meta1 = generate_2brad_m_species()
    print(f"   Samples: {df1.shape[1]}, Species: {df1.shape[0]}, File: {out_dir / '2brad_m_species.csv'}")
    print(f"   Metadata: {out_dir / 'metadata_gut.csv'}")

    print("\n2. 2bRAD-M Functional Gene Table (KO)")
    df2 = generate_2brad_m_function()
    print(f"   Samples: {df2.shape[1]}, KOs: {df2.shape[0]}, File: {out_dir / '2brad_m_function.csv'}")

    print("\n3. Strain2bScan Strain-Level Data")
    df3 = generate_strain2bscan()
    print(f"   Records: {len(df3)}, Species: {df3['species'].nunique()}, Strains: {df3['strain'].nunique()}")
    print(f"   File: {out_dir / 'strain2bscan_output.csv'}")

    print("\n4. Tag2bMap Output (with ANI)")
    df4 = generate_tag2bmap()
    print(f"   Records: {len(df4)}, Species: {df4['species'].nunique()}, Strains: {df4['strain'].nunique()}")
    print(f"   File: {out_dir / 'tag2bmap_output.csv'}")

    print("\n5. QIIME BIOM Format")
    df5, meta5 = generate_qiime_biom()
    print(f"   Samples: {df5.shape[1]}, Features: {df5.shape[0]}")
    print(f"   File: {out_dir / 'qiime_feature_table.biom'} (or .csv/.tsv fallback)")
    print(f"   Metadata: {out_dir / 'qiime_metadata.csv'}")

    print("\n" + "=" * 60)
    print("All datasets generated successfully!")
    print("=" * 60)

    # Print file sizes
    print("\nFile sizes:")
    for f in sorted(out_dir.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name:30s} {size:>10,} bytes")


if __name__ == '__main__':
    generate_all_examples()
