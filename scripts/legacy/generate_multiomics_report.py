#!/usr/bin/env python3
"""Generate multi-omics report for Huang et al mBio 2021-style data."""
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.spatial.distance import braycurtis, pdist, squareform
from scipy.stats import pearsonr, spearmanr
from scipy.linalg import orthogonal_procrustes
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

out = '/Users/shihuang/Documents/kimi/workspace/meta2banalyst'

# ── Load data ──────────────────────────────────────────
microbes = pd.read_csv('/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_microbes_genus.abd_261.txt', sep='\t', index_col=0).T
metabolites = pd.read_csv('/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_metabolites_abd_261.txt', sep='\t', index_col=0).T
meta = pd.read_csv('/Users/shihuang/MyProjects/SoH_project/multi-omics/Matched_microbes_metadata_261.txt', sep='\t', index_col=0)

common = microbes.columns.intersection(metabolites.columns)
microbes = microbes[common]
metabolites = metabolites[common]
meta = meta.loc[common]

print(f"Microbiome: {microbes.shape}")
print(f"Metabolome: {metabolites.shape}")
print(f"Samples: {len(common)}")

# ── Microbiome PCoA ────────────────────────────────────
dist_mb = squareform(pdist(microbes.T.values, metric='braycurtis'))
n = len(common)
H = np.eye(n) - np.ones((n, n)) / n
B = -0.5 * H @ (dist_mb ** 2) @ H
eigvals, eigvecs = np.linalg.eigh(B)
idx = np.argsort(eigvals)[::-1]
eigvals = eigvals[idx]
eigvecs = eigvecs[:, idx]
pos_idx = eigvals > 0
coords_mb = eigvecs[:, pos_idx] * np.sqrt(eigvals[pos_idx])
var_mb = (eigvals[pos_idx] / eigvals[pos_idx].sum()) * 100

# ── Metabolome PCA ─────────────────────────────────────
met_std = StandardScaler().fit_transform(metabolites.T.values)
pca_met = PCA(n_components=10)
pca_coords = pca_met.fit_transform(met_std)
met_var = pca_met.explained_variance_ratio_ * 100

# ── Procrustes ─────────────────────────────────────────
R, s = orthogonal_procrustes(pca_coords[:, :2], coords_mb[:, :2])
Y_aligned = pca_coords[:, :2] @ R
m2 = np.sum((coords_mb[:, :2] - Y_aligned) ** 2)
norm_m2 = m2 / np.sum((coords_mb[:, :2] - coords_mb[:, :2].mean(axis=0)) ** 2)

# ── Mantel ─────────────────────────────────────────────
dist_met = squareform(pdist(metabolites.T.values, metric='euclidean'))
idx_triu = np.triu_indices(n, k=1)
mantel_r, mantel_p = pearsonr(dist_mb[idx_triu], dist_met[idx_triu])

print(f"Procrustes: m2={m2:.4f}, norm_m2={norm_m2:.6f}, scale={s:.3f}")
print(f"Mantel: r={mantel_r:.3f}, p={mantel_p:.4f}")

# ── Cross-correlations ─────────────────────────────────
top_genera = microbes.mean(axis=1).sort_values(ascending=False).head(15).index
top_mets = metabolites.mean(axis=1).sort_values(ascending=False).head(20).index

corr_mat = np.zeros((len(top_genera), len(top_mets)))
pval_mat = np.zeros((len(top_genera), len(top_mets)))
for i, g in enumerate(top_genera):
    for j, m in enumerate(top_mets):
        r, p = spearmanr(microbes.loc[g], metabolites.loc[m])
        corr_mat[i, j] = r
        pval_mat[i, j] = p

# All significant correlations
all_sig = []
for g in microbes.index:
    for m in metabolites.index:
        r, p = spearmanr(microbes.loc[g], metabolites.loc[m])
        if p < 0.05:
            all_sig.append({'genus': g, 'metabolite': m, 'r': r, 'p': p})
sig_df = pd.DataFrame(all_sig).sort_values('p')
print(f"Significant cross-correlations: {len(sig_df)}")

# ── VISUALIZATIONS ─────────────────────────────────────
visits = meta['Visit']
visit_colors = {v: plt.cm.tab10(i) for i, v in enumerate(sorted(visits.unique()))}

# Fig 1: Procrustes
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
for v in sorted(visits.unique()):
    mask = visits == v
    axes[0].scatter(coords_mb[mask, 0], coords_mb[mask, 1], c=[visit_colors[v]], label=v, s=40, alpha=0.7)
axes[0].set_title(f'Microbiome PCoA (PC1={var_mb[0]:.1f}%, PC2={var_mb[1]:.1f}%)')
axes[0].set_xlabel('PC1'); axes[0].set_ylabel('PC2')
axes[0].legend(title='Visit', bbox_to_anchor=(1.05, 1))

for v in sorted(visits.unique()):
    mask = visits == v
    axes[1].scatter(coords_mb[mask, 0], coords_mb[mask, 1], c='blue', s=30, alpha=0.4)
    axes[1].scatter(Y_aligned[mask, 0], Y_aligned[mask, 1], c='red', s=30, alpha=0.4, marker='^')
for i in range(0, n, 15):
    axes[1].plot([coords_mb[i, 0], Y_aligned[i, 0]], [coords_mb[i, 1], Y_aligned[i, 1]], 'k-', alpha=0.1, lw=0.5)
axes[1].set_title(f'Procrustes Alignment\nm2={norm_m2:.4f}, scale={s:.2f}')
axes[1].legend(['Microbiome', 'Metabolome'])
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig1_procrustes.png', dpi=200, bbox_inches='tight')
plt.close()

# Fig 2: Mantel scatter
fig, ax = plt.subplots(figsize=(8, 7))
ax.scatter(dist_mb[idx_triu], dist_met[idx_triu], alpha=0.2, s=5, c='green')
z = np.polyfit(dist_mb[idx_triu], dist_met[idx_triu], 1)
p_line = np.poly1d(z)
x_line = np.linspace(dist_mb[idx_triu].min(), dist_mb[idx_triu].max(), 100)
ax.plot(x_line, p_line(x_line), 'r--', lw=2, label=f'r={mantel_r:.3f}, p={mantel_p:.4f}')
ax.set_xlabel('Microbiome Bray-Curtis Distance')
ax.set_ylabel('Metabolome Euclidean Distance')
ax.set_title('Mantel Test: Distance Matrix Correlation')
ax.legend()
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig2_mantel.png', dpi=200, bbox_inches='tight')
plt.close()

# Fig 3: Cross-corr heatmap
fig, ax = plt.subplots(figsize=(16, 10))
genus_labels = [g.replace('Fla_', '').replace('Fus_', '').replace('Pre_', '').replace('Por_', '').replace('Nei_', '').replace('Pas_', '').replace('Str_', '').replace('Vei_', '').replace('Bur_', '').replace('Cam_', '').replace('Act_', '').replace('Cor_', '').replace('Mic_', '').replace('Bac_', '').replace('TM7_', '')[:20] for g in top_genera]
met_labels = [m[:25] for m in top_mets]
sns.heatmap(corr_mat, xticklabels=met_labels, yticklabels=genus_labels, cmap='RdBu_r', center=0, vmin=-0.6, vmax=0.6, mask=(pval_mat > 0.05), linewidths=0.5, ax=ax, cbar_kws={'label': 'Spearman r'})
ax.set_title('Microbiome-Metabolome Cross-correlation (Top 15 Genera x Top 20 Metabolites, p<0.05)')
ax.set_xlabel('Metabolites'); ax.set_ylabel('Bacterial Genera')
plt.xticks(rotation=45, ha='right', fontsize=8)
plt.yticks(rotation=0, fontsize=9)
plt.tight_layout()
plt.savefig(f'{out}/multiomics_fig3_crosscorr.png', dpi=200, bbox_inches='tight')
plt.close()

# Fig 4: Summary panel
fig = plt.figure(figsize=(16, 10))

ax1 = plt.subplot(2, 3, 1)
for v in sorted(visits.unique()):
    mask = visits == v
    ax1.scatter(coords_mb[mask, 0], coords_mb[mask, 1], c=[visit_colors[v]], s=20, alpha=0.7)
ax1.set_title(f'A. Microbiome PCoA\nPC1={var_mb[0]:.1f}%, PC2={var_mb[1]:.1f}%')

ax2 = plt.subplot(2, 3, 2)
for v in sorted(visits.unique()):
    mask = visits == v
    ax2.scatter(pca_coords[mask, 0], pca_coords[mask, 1], c=[visit_colors[v]], s=20, alpha=0.7)
ax2.set_title(f'B. Metabolome PCA\nPC1={met_var[0]:.1f}%, PC2={met_var[1]:.1f}%')

ax3 = plt.subplot(2, 3, 3)
ax3.scatter(coords_mb[:, 0], coords_mb[:, 1], c='blue', s=20, alpha=0.5, label='Microbiome')
ax3.scatter(Y_aligned[:, 0], Y_aligned[:, 1], c='red', s=20, alpha=0.5, marker='^', label='Metabolome')
for i in range(0, n, 15):
    ax3.plot([coords_mb[i, 0], Y_aligned[i, 0]], [coords_mb[i, 1], Y_aligned[i, 1]], 'k-', alpha=0.1, lw=0.5)
ax3.set_title(f'C. Procrustes\nm2={norm_m2:.4f}')
ax3.legend(fontsize=8)

ax4 = plt.subplot(2, 3, 4)
shannon = -(microbes * np.log(microbes + 1e-10)).sum(axis=0)
sns.boxplot(data=pd.DataFrame({'Visit': visits, 'Shannon': shannon}), x='Visit', y='Shannon', ax=ax4)
ax4.set_title('D. Alpha Diversity'); ax4.tick_params(axis='x', rotation=45)

ax5 = plt.subplot(2, 3, 5)
ax5.scatter(dist_mb[idx_triu], dist_met[idx_triu], alpha=0.2, s=5, c='green')
ax5.plot(x_line, p_line(x_line), 'r--', lw=2)
ax5.set_title(f'E. Mantel Test\nr={mantel_r:.3f}, p={mantel_p:.4f}')

ax6 = plt.subplot(2, 3, 6)
sig_counts = np.sum(pval_mat < 0.05, axis=1)
ax6.barh(range(len(sig_counts)), sig_counts)
ax6.set_yticks(range(len(sig_counts)))
ax6.set_yticklabels(genus_labels, fontsize=8)
ax6.set_title('F. Significant Correlations (p<0.05)'); ax6.set_xlabel('Count')
ax6.invert_yaxis()

plt.suptitle('Multi-omics Analysis: Oral Microbiome x Metabolome', fontsize=14, y=0.98)
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig(f'{out}/multiomics_fig4_summary.png', dpi=200, bbox_inches='tight')
plt.close()

print("\nAll figures saved!")

# ── Generate Markdown Report ───────────────────────────
report_lines = []
report_lines.append("# Multi-omics Analysis Report: Oral Microbiome x Metabolome")
report_lines.append("")
report_lines.append("**Dataset**: Huang et al. mBio 2021-style paired oral microbiome-metabolome data")
report_lines.append("**Analysis Date**: 2026-07-17")
report_lines.append("**Samples**: %d paired samples (24 participants, 7 timepoints)" % len(common))
report_lines.append("")
report_lines.append("---")
report_lines.append("")
report_lines.append("## 1. Data Overview")
report_lines.append("")
report_lines.append("| Layer | Features | Samples | Description |")
report_lines.append("|-------|----------|---------|-------------|")
report_lines.append("| Microbiome (Genus) | %d | %d | 16S rRNA, genus-level |" % (microbes.shape[0], microbes.shape[1]))
report_lines.append("| Metabolome | %d | %d | LC-MS, untargeted |" % (metabolites.shape[0], metabolites.shape[1]))
report_lines.append("")
report_lines.append("**Visit distribution**: " + str(dict(visits.value_counts().sort_index())))
report_lines.append("")
report_lines.append("---")
report_lines.append("")
report_lines.append("## 2. Cross-omics Joint Analysis Results")
report_lines.append("")
report_lines.append("### 2.1 Procrustes Analysis")
report_lines.append("")
report_lines.append("Procrustes analysis tests whether microbiome and metabolome sample configurations are similar after optimal rotation/scaling/translation.")
report_lines.append("")
report_lines.append("| Metric | Value |")
report_lines.append("|--------|-------|")
report_lines.append("| m2 (SSE) | %.4f |" % m2)
report_lines.append("| Normalized m2 | %.6f |" % norm_m2)
report_lines.append("| Scale factor | %.3f |" % s)
report_lines.append("")
report_lines.append("> **Interpretation**: Normalized m2 of %.4f indicates %s concordance between microbiome and metabolome configurations." % (norm_m2, "good" if norm_m2 < 0.3 else "moderate" if norm_m2 < 0.5 else "poor"))
report_lines.append("")
report_lines.append("### 2.2 Mantel Test (Distance Matrix Correlation)")
report_lines.append("")
report_lines.append("| Metric | Value |")
report_lines.append("|--------|-------|")
report_lines.append("| Pearson r | %.3f |" % mantel_r)
report_lines.append("| p-value | %.4f |" % mantel_p)
report_lines.append("")
report_lines.append("> **Interpretation**: r=%.3f (p=%.4f) - %s correlation between microbiome and metabolome distances." % (mantel_r, mantel_p, "significant" if mantel_p < 0.05 else "not significant"))
report_lines.append("")
report_lines.append("### 2.3 Feature-level Cross-correlations")
report_lines.append("")
report_lines.append("Spearman correlations between all bacterial genera and metabolites:")
report_lines.append("")
report_lines.append("| Statistic | Count |")
report_lines.append("|-----------|-------|")
report_lines.append("| Total pairs tested | %d |" % (microbes.shape[0] * metabolites.shape[0]))
report_lines.append("| Significant (p<0.05) | %d |" % len(sig_df))
report_lines.append("| Positive associations | %d |" % len(sig_df[sig_df['r'] > 0]))
report_lines.append("| Negative associations | %d |" % len(sig_df[sig_df['r'] < 0]))
report_lines.append("")
report_lines.append("#### Top 5 Positive Associations")
report_lines.append("")
report_lines.append("| Genus | Metabolite | r | p |")
report_lines.append("|-------|-----------|---|---|")
for _, row in sig_df[sig_df['r'] > 0].sort_values('r', ascending=False).head(5).iterrows():
    report_lines.append("| %s | %s | %+.3f | %.4f |" % (row['genus'][:20], row['metabolite'][:30], row['r'], row['p']))
report_lines.append("")
report_lines.append("#### Top 5 Negative Associations")
report_lines.append("")
report_lines.append("| Genus | Metabolite | r | p |")
report_lines.append("|-------|-----------|---|---|")
for _, row in sig_df[sig_df['r'] < 0].sort_values('r').head(5).iterrows():
    report_lines.append("| %s | %s | %+.3f | %.4f |" % (row['genus'][:20], row['metabolite'][:30], row['r'], row['p']))
report_lines.append("")
report_lines.append("---")
report_lines.append("")
report_lines.append("## 3. Figures")
report_lines.append("")
report_lines.append("### Figure 1: Procrustes Analysis")
report_lines.append("![Procrustes](multiomics_fig1_procrustes.png)")
report_lines.append("")
report_lines.append("### Figure 2: Mantel Test")
report_lines.append("![Mantel](multiomics_fig2_mantel.png)")
report_lines.append("")
report_lines.append("### Figure 3: Cross-omics Correlation Heatmap")
report_lines.append("![Cross-corr](multiomics_fig3_crosscorr.png)")
report_lines.append("")
report_lines.append("### Figure 4: Multi-omics Summary Panel")
report_lines.append("![Summary](multiomics_fig4_summary.png)")
report_lines.append("")
report_lines.append("---")
report_lines.append("")
report_lines.append("## 4. Methods")
report_lines.append("")
report_lines.append("- **Procrustes**: Orthogonal Procrustes with optimal rotation/scaling")
report_lines.append("- **Mantel**: Pearson correlation between Bray-Curtis (microbiome) and Euclidean (metabolome) distance matrices")
report_lines.append("- **Cross-correlations**: Spearman rank correlation between genera and metabolites")
report_lines.append("")
report_lines.append("## 5. Conclusions")
report_lines.append("")
report_lines.append("1. **Procrustes**: m2=%.4f indicates %s structural similarity between microbiome and metabolome." % (norm_m2, "good" if norm_m2 < 0.3 else "moderate" if norm_m2 < 0.5 else "weak"))
report_lines.append("2. **Mantel**: r=%.3f (p=%.4f) shows %s microbiome-metabolome distance correlation." % (mantel_r, mantel_p, "significant" if mantel_p < 0.05 else "no significant"))
report_lines.append("3. **Feature-level**: %d significant genus-metabolite correlations identified (p<0.05)." % len(sig_df))
report_lines.append("")
report_lines.append("*Generated by Meta2bAnalyst v0.1.0*")

with open(f'{out}/Huang_mBio_multiomics_report.md', 'w') as f:
    f.write('\n'.join(report_lines))

print(f"\nReport saved: {out}/Huang_mBio_multiomics_report.md")
print(f"Figures:")
print(f"  {out}/multiomics_fig1_procrustes.png")
print(f"  {out}/multiomics_fig2_mantel.png")
print(f"  {out}/multiomics_fig3_crosscorr.png")
print(f"  {out}/multiomics_fig4_summary.png")
