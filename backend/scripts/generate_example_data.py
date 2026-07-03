#!/usr/bin/env python3
"""
Generate example datasets for Meta2bAnalyst backend testing.
Creates 5 datasets in the uploads/example_data directory.
"""
import os
import random

import numpy as np
import pandas as pd


def generate_example_data(output_dir: str = "uploads/example_data") -> None:
    """Generate 5 example datasets for Meta2bAnalyst."""
    os.makedirs(output_dir, exist_ok=True)
    random.seed(42)
    np.random.seed(42)

    # 1. 2bRAD-M species abundance table (30 samples x 100 species)
    n_samples = 30
    n_species = 100
    sample_names = [f"Sample_{i+1:02d}" for i in range(n_samples)]
    species_names = [f"Species_{i+1:03d}" for i in range(n_species)]

    # Simulate counts with sparsity and group effects
    group_labels = np.array(["Control"] * 15 + ["Treatment"] * 15)
    counts = np.zeros((n_species, n_samples), dtype=int)

    for i in range(n_species):
        # Base abundance
        base = np.random.poisson(50, n_samples)
        # Treatment effect for some species
        if i < 20:
            base[15:] += np.random.poisson(30, 15)
        elif i < 40:
            base[15:] -= np.random.poisson(10, 15)
            base[15:] = np.maximum(base[15:], 0)
        counts[i, :] = base

    # Add sparsity
    zero_mask = np.random.random(counts.shape) < 0.3
    counts[zero_mask] = 0

    species_df = pd.DataFrame(counts, index=species_names, columns=sample_names)
    species_df.index.name = "Species"
    species_path = os.path.join(output_dir, "2brad_m_species_abundance.tsv")
    species_df.to_csv(species_path, sep="\t")
    print(f"Generated: {species_path} ({n_samples} samples x {n_species} species)")

    # 2. 2bRAD-M functional gene table (optional, 30 samples x 50 KOs)
    n_kos = 50
    ko_names = [f"KO_{i+1:03d}" for i in range(n_kos)]
    func_counts = np.random.poisson(20, (n_kos, n_samples))
    zero_mask = np.random.random(func_counts.shape) < 0.4
    func_counts[zero_mask] = 0

    func_df = pd.DataFrame(func_counts, index=ko_names, columns=sample_names)
    func_df.index.name = "KO"
    func_path = os.path.join(output_dir, "2brad_m_functional_genes.tsv")
    func_df.to_csv(func_path, sep="\t")
    print(f"Generated: {func_path} ({n_samples} samples x {n_kos} KOs)")

    # 3. Strain2bScan output (5 species, 3-10 strains each)
    strain_records = []
    target_species = ["Bacteroides_fragilis", "Escherichia_coli", "Faecalibacterium_prausnitzii",
                      "Akkermansia_muciniphila", "Prevotella_copri"]

    for sp in target_species:
        n_strains = random.randint(3, 10)
        strains = [f"{sp}_strain_{j+1}" for j in range(n_strains)]
        for sample in sample_names:
            # Random subset of strains present per sample
            present_strains = random.sample(strains, random.randint(1, max(1, n_strains - 1)))
            for st in present_strains:
                abundance = np.random.poisson(10) + 1
                strain_records.append({
                    "sample_id": sample,
                    "species": sp,
                    "strain": st,
                    "abundance": abundance,
                })

    strain_df = pd.DataFrame(strain_records)
    strain_path = os.path.join(output_dir, "strain2bscan_output.tsv")
    strain_df.to_csv(strain_path, sep="\t", index=False)
    print(f"Generated: {strain_path} ({len(strain_df)} strain-sample records)")

    # 4. Tag2bMap output (with ANI)
    tag_records = []
    for sp in target_species:
        n_strains = random.randint(3, 8)
        strains = [f"{sp}_strain_{j+1}" for j in range(n_strains)]
        for sample in sample_names:
            present_strains = random.sample(strains, random.randint(1, max(1, n_strains - 1)))
            for st in present_strains:
                ani = round(np.random.uniform(95.0, 99.9), 2)
                coverage = round(np.random.uniform(0.5, 1.0), 3)
                abundance = np.random.poisson(10) + 1
                tag_records.append({
                    "sample_id": sample,
                    "species": sp,
                    "strain": st,
                    "ANI": ani,
                    "coverage": coverage,
                    "abundance": abundance,
                })

    tag_df = pd.DataFrame(tag_records)
    tag_path = os.path.join(output_dir, "tag2bmap_output.tsv")
    tag_df.to_csv(tag_path, sep="\t", index=False)
    print(f"Generated: {tag_path} ({len(tag_df)} strain-sample records with ANI)")

    # 5. Metadata table (2-3 grouping variables)
    metadata = {
        "sample_id": sample_names,
        "group": ["Control"] * 15 + ["Treatment"] * 15,
        "age": np.random.randint(20, 70, n_samples).tolist(),
        "sex": random.choices(["M", "F"], k=n_samples),
        "bmi": np.round(np.random.uniform(18.0, 35.0, n_samples), 1).tolist(),
    }
    metadata_df = pd.DataFrame(metadata).set_index("sample_id")
    metadata_path = os.path.join(output_dir, "metadata.tsv")
    metadata_df.to_csv(metadata_path, sep="\t")
    print(f"Generated: {metadata_path} ({n_samples} samples, variables: {list(metadata_df.columns)})")

    print("\nExample data generation complete. Files saved to:", output_dir)


if __name__ == "__main__":
    generate_example_data()
