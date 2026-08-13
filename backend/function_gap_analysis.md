# Meta2bAnalyst 功能差距分析

> 基于 MicrobiomeAnalyst 标准分析流程与当前实现对比
> 生成时间：2026-07-10

---

## 一、当前已实现功能（绿色 = 已覆盖）

### 数据输入与预处理
- ✅ 支持 2bRAD-M、QIIME、Mothur feature table 输入
- ✅ 低丰度/低方差过滤
- ✅ 4 种归一化：TSS、Rarefaction、CLR、CSS
- ✅ 数据质量检查（样本/特征统计）

### 群落分析（Community Profiling）
- ✅ Alpha diversity：Shannon, Simpson, Chao1, Observed, Pielou evenness
- ✅ Beta diversity：Bray-Curtis + PCoA + 95%置信椭圆
- ✅ PERMANOVA 组间差异检验
- ✅ 堆叠柱状图（Stacked Bar）
- ✅ 热图（Heatmap）+ Group 颜色注释条

### 差异分析（Comparative Analysis）
- ✅ t-test / Wilcoxon（基础统计）
- ✅ ANCOM-BC（微生物组专用）
- ✅ LEfSe（LDA + KW 筛选）
- ✅ 火山图（Volcano Plot）

### 机器学习
- ✅ Random Forest（含混淆矩阵、ROC 曲线、Feature Importance）

### 报告与导出
- ✅ 综合 PDF 报告（含方法学、数据驱动解读、预处理说明）
- ✅ 结果数据表格导出

---

## 二、按数据类型划分的缺失功能（红色 = 缺失）

### 2.1 16S rRNA 扩增子数据（Amplicon）

16S 数据是目前最主流的微生物组数据类型，有大量特有分析手段：

| 缺失模块 | 重要性 | 说明 |
|---------|--------|------|
| **Phylogenetic Diversity (Faith's PD)** | 🔴 高 | 基于系统发育树的多样性，16S 标志性指标 |
| **Weighted / Unweighted UniFrac** | 🔴 高 | 16S 最经典的 Beta diversity 距离，需要 phylogenetic tree |
| **UniFrac PCoA / NMDS** | 🔴 高 | 基于 UniFrac 的降维可视化 |
| **PICRUSt2 / Tax4Fun 功能预测** | 🔴 高 | 从16S推断功能潜能，不需要shotgun测序 |
| **Phylogenetic Tree 可视化** | 🟡 中 | 进化树 + 热图（Heat tree） |
| **DADA2 / Deblur 去噪** | 🟡 中 | 上游 ASV 生成，后端可集成 R 包 |
| **Taxonomy 分类注释** | 🟡 中 | Kingdom → Species 层级注释，当前仅有 feature ID |
| **Rarefaction curve** | 🟡 中 | 测序深度饱和曲线 |
| **Good's coverage** | 🟡 中 | 覆盖度评估，简单 Alpha 指标 |
| **Core microbiome** | 🟡 中 | 核心菌群（在所有/大部分样本中出现的特征） |

### 2.2 Shotgun 宏基因组数据（WGS / Metagenomic）

Shotgun 数据直接测到 DNA 序列，功能信息更丰富：

| 缺失模块 | 重要性 | 说明 |
|---------|--------|------|
| **功能注释数据库整合** | 🔴 高 | KEGG、COG、GO、CAZy、EggNOG 等功能注释 |
| **Pathway 富集分析** | 🔴 高 | KEGG Pathway / MetaCyc 通路富集（类似图1-J） |
| **通路丰度图** | 🔴 高 | Pathway 级别的堆叠柱状图和差异分析 |
| **Gene family 分析** | 🟡 中 | 基因家族丰度、多样性 |
| **Strain-level profiling** | 🟡 中 | 菌株/株水平解析（用户原需求提及） |
| **MAG (Metagenome-Assembled Genome)** | 🟡 中 | 宏基因组组装基因组的质量评估和注释 |
| **Antibiotic resistance genes** | 🟡 中 | ARG 注释和丰度分析（ResFinder/CARD） |
| **Virulence factor** | 🟡 中 | 毒力因子分析（VFDB） |

### 2.3 2bRAD-M 数据

2bRAD-M 是当前最成熟的物种水平标记分析，但仍有扩展空间：

| 缺失模块 | 重要性 | 说明 |
|---------|--------|------|
| **Species-level biomarker discovery** | 🟡 中 | 当前分析是 feature-level，需支持物种注释后的 biomarker |
| **Strain-level ANI/phylogeny** | 🟡 中 | 同一物种内不同株系的遗传距离 |
| **2bRAD-M 特有质控** | 🟡 中 | 标记覆盖度、测序深度均一性检查 |
| **Taxonomy 层级汇总** | 🟡 中 | Phylum/Class/Order/Family/Genus 层级汇总分析 |

### 2.4 跨组学分析（Metagenome-Metabolome）

用户明确提到这是未来需求：

| 缺失模块 | 重要性 | 说明 |
|---------|--------|------|
| **Feature-Metabolite 关联分析** | 🔴 高 | Spearman/Pearson 相关，热图 + 网络 |
| **Procrustes analysis** | 🔴 高 | 微生物组与代谢组 PCoA 配置一致性检验 |
| **Mantel test** | 🔴 高 | 距离矩阵相关性（群落 vs 代谢距离） |
| **Sparse CCA / RDA** | 🟡 中 | 典范对应分析，约束排序 |
| **O2PLS / PLS-DA** | 🟡 中 | 多变量统计整合分析 |
| **mmvec / MIMOSA** | 🟡 中 | 深度学习/概率模型推断微生物-代谢物关联 |

### 2.5 通用分析（所有数据类型）

以下分析不依赖特定数据类型，是通用能力：

| 缺失模块 | 重要性 | 说明 |
|---------|--------|------|
| **Network analysis（共现网络）** | 🔴 高 | SpiecEasi / SparCC / IGraph 微生物共现网络（图1-H） |
| **Hierarchical clustering** | 🔴 高 | 层次聚类 + 树状图（图1-F左侧） |
| **NMDS** | 🔴 高 | 非度量多维尺度分析，生态学常用 |
| **t-SNE / UMAP** | 🟡 中 | 非线性降维，可视化高维微生物数据 |
| **Correlation analysis** | 🔴 高 | 特征-特征、特征-元数据相关矩阵 + 热图 |
| **Source tracking（FEAST / SourceTracker）** | 🟡 中 | 来源追踪（图1-G） |
| **Temporal / Longitudinal analysis** | 🟡 中 | 时间序列分析，如果 metadata 有时间变量 |
| **DESeq2 / edgeR** | 🟡 中 | 差异分析（count 数据专用，比 t-test 更严谨） |
| **ALDEx2** | 🟡 中 | 成分数据差异分析（CLR-based） |
| **MaAsLin3** | 🟡 中 | 用户明确要求的通用多变量关联分析 |

---

## 三、优先级排序（建议实现顺序）

### P0（最高优先级，约 2-3 周）
1. **功能注释与通路分析**（Shotgun 数据核心）
   - KEGG 注释 + Pathway 富集（Fisher's exact / hypergeometric）
   - Pathway 丰度可视化（堆叠柱状图 + 差异 Pathway）
2. **Network analysis（共现网络）**
   - SparCC / Spearman 相关性 → 网络图
   - Cytoscape / Gephi 格式导出
3. **Correlation analysis**
   - Feature-Feature 相关矩阵 + 热图
   - Feature-Metadata 关联

### P1（高优先级，约 3-4 周）
4. **16S 功能预测（PICRUSt2 / Tax4Fun）**
   - 用户常只有16S数据但需要功能洞察
5. **UniFrac + Faith's PD**
   - 16S 标志性分析，需要 phylogenetic tree（可用 GreenGenes/SILVA 预建树）
6. **NMDS + PERMANOVA 整合**
   - 与 PCoA 并列的 ordination 方法
7. **Hierarchical clustering + Heat tree**
   - 聚类 + 进化树可视化

### P2（中优先级，约 4-6 周）
8. **Metagenome-Metabolome 跨组学**
   - Procrustes + Mantel test + Feature-Metabolite 相关
9. **MaAsLin3**
   - 用户明确要求的通用多变量关联
10. **t-SNE / UMAP**
    - 非线性降维可视化
11. **Source tracking（FEAST）**
    - 来源追踪
12. **DESeq2 / edgeR / ALDEx2**
    - 更严谨的差异分析工具

### P3（低优先级，约 6-8 周）
13. **Strain-level analysis**
14. **Time-series / Longitudinal analysis**
15. **Core microbiome**
16. **Taxonomy 层级汇总（从 feature 到各分类层级）**
17. **Rarefaction curve**
18. **MAG 注释与质量评估**

---

## 四、与图1/图2的对照

| 图中标识 | 分析内容 | 当前状态 | 差距说明 |
|---------|---------|---------|---------|
| A | Alpha boxplot | ✅ 已实现 | 已有 |
| B | Stacked bar | ✅ 已实现 | 已有 |
| C | PCoA + Ellipse | ✅ 已实现 | 已加置信椭圆 |
| D | Scatter / Volcano | ✅ 已实现 | 已有 |
| E | Feature ranking | ✅ 已实现 | RF importance + LEfSe |
| F | Heat tree / Hclust | ❌ 缺失 | 需要层次聚类 + 进化树 |
| G | Source tracking | ❌ 缺失 | FEAST/SourceTracker |
| H | Network analysis | ❌ 缺失 | 共现网络 |
| I | 3D PCoA / Pie | 🟡 部分 | 3D PCoA 未实现，但 2D 已有 |
| J | Pathway analysis | ❌ 缺失 | KEGG 通路富集和可视化 |

---

## 五、技术实现建议

### 5.1 需要新增的后端依赖
```
# 功能注释
- eggnog-mapper (for EggNOG)
- kofamscan (for KEGG)
- humann3 (for Shotgun pathway)

# 16S 功能预测
- picrust2 (R/Python package)
- Tax4Fun2 (R package)

# 网络分析
- spieceasi (R package)
- igraph (Python/R)

# 跨组学
- vegan (R: Procrustes, Mantel)
- mmvec (Python/conda)
- maaslin3 (R/Bioconductor)

# 其他
- biom-format (for BIOM file I/O)
- scikit-bio (for UniFrac, Faith's PD)
```

### 5.2 前端需要新增的分析选择页签
当前分析选择页面需要增加：
- **Functional Analysis**（功能分析）
- **Network Analysis**（网络分析）
- **Cross-omics Analysis**（跨组学）
- **Correlation Analysis**（相关分析）
- **Strain Analysis**（株水平）

### 5.3 数据库依赖
- **KEGG**：通路注释（需要本地数据库或 API）
- **EggNOG**：功能注释（可在线或本地）
- **GreenGenes / SILVA**：16S 系统发育树（预建树）
- **GTDB**：2bRAD/Shotgun 物种分类（当前报告已有 GTDB 前缀）

---

## 六、总结

当前实现覆盖了微生物组分析的 **基础分析层**（约 40-50%），但缺少以下核心层：

| 层级 | 覆盖度 | 说明 |
|------|--------|------|
| 基础统计（Alpha/Beta/Diff） | ~80% | 基本覆盖，但 UniFrac/NMDS 等缺失 |
| 功能分析 | ~10% | 几乎空白，需要 KEGG/通路/功能预测 |
| 网络分析 | ~0% | 完全缺失，共现网络是微生物组标配 |
| 跨组学 | ~0% | 完全缺失，metagenome-metabolome 未实现 |
| 机器学习 | ~30% | 只有 RF，缺 cross-validation 优化、其他模型 |
| 可视化 | ~60% | 基本图表有，但缺少 heat tree、3D 等 |

**建议下一步**：优先实现 **P0 功能**（功能注释、网络分析、相关分析），使平台达到可用水平，然后逐步扩展至 P1/P2。
