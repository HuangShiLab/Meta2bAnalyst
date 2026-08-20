# Meta2bAnalyst 架构分析报告：多组学/多位点分析覆盖缺口

> **分析日期**: 2026-08-18  
> **分析范围**: `module_registry.py` + `executor.py` 全量模块  
> **已注册模块总数**: 42 个

---

## 一、现有模块全景

### 1.1 按类别汇总

| 类别 | 模块数量 | 具体模块 |
|------|---------|---------|
| preprocessing | 1 | data_validator |
| individual_omics | 23 | microbiome_pcoa, microbiome_alpha, microbiome_nmds, metabolome_pca, metabolome_alpha, network_sparcc, pathway_kegg, functional_prediction, tsne, umap, anosim, random_forest, aldex2, songbird, enterotype, rarefaction, taxonomy_bar, wgcna, unifrac, strain_analyzer, source_tracking, upset, heatmap, volcano |
| marker | 4 | microbiome_marker, metabolome_marker, maaslin3, random_forest* |
| integration | 12 | procrustes, mantel_test, sparse_cca, rda, o2pls, cross_correlation, mofa, diablo, cross_site_permanova, cross_omics_gbdt, cross_site_network, cross_site_concordance |
| visualization | 1 | report_generator（其余 viz 模块归入 individual_omics） |

> *random_forest 在 registry 中 category 为 marker，executor 已 wiring

### 1.2 关键发现

- **所有 42 个模块均已完成 executor wiring**，无 pending 模块（`PENDING_EXECUTOR_WIRING` 为空）。
- 多组学整合模块（integration）达 12 个，是系统中**最密集**的方法学簇。
- 数据预处理层面**仅有** data_validator，无专用标准化、批次校正、缺失值处理模块。
- 统计检验层面以**单因素/两组比较**为主，配对设计、协变量调整、通用混合效应框架存在显著缺口。

---

## 二、四维度覆盖度评估

---

### A. 多组学整合方法

| 方法类别 | 现有模块 | 覆盖度 | 缺失方法 |
|---------|---------|--------|---------|
| 矩阵相关/回归 | Procrustes, Mantel, sparse-CCA, RDA | **4/5** | 偏最小二乘路径建模 (PLS-PM)、核典型相关分析 (KCCA) |
| 潜变量/因子模型 | MOFA+, O2PLS, DIABLO | **5/5** | — |
| 预测建模 | cross_omics_gbdt (GBDT/LASSO), Random Forest | **3/5** | 支持向量机 (SVM)、弹性网络 (Elastic Net)、XGBoost/LightGBM 调参优化 |
| 贝叶斯整合 | — | **0/5** | 贝叶斯相关分析 (Bayesian correlation, SPIEC-EASI 贝叶斯后端)、Stan-based 多组学模型、整合贝叶斯因子分析 |
| 网络推断 | network_sparcc (SparCC, 仅单组学) | **2/5** | SPIEC-EASI、gCoda、FLASHWeave、Bayesian 网络推断 (hgmn) |
| 纵向动态 | MaAsLin3 (固定效应 + 随机效应) | **3/5** | 广义估计方程 (GEE)、时间序列模型 (ARMA/状态空间)、动态贝叶斯网络 |

#### 评分理由

- **矩阵相关/回归 (4/5)**：Procrustes、Mantel、sparse-CCA、RDA 已覆盖经典线性关联框架。RDA 可视为约束排序，但缺乏更灵活的 PLS-PM 结构方程路径建模。当前无核方法扩展非线性关联。
- **潜变量/因子模型 (5/5)**：MOFA+（无监督多组学因子分解）、O2PLS（正交信号校正 + 联合变异分离）、DIABLO（监督稀疏 PLS-DA）已形成完整三角覆盖，是该系统最强维度。
- **预测建模 (3/5)**：GBDT/LASSO 通过 `cross_omics_gbdt` 以嵌套 CV + bootstrap 提供生产级实现；Random Forest 提供基线分类。但缺少 SVM、Elastic Net 等正则化线性模型，以及现代梯度提升框架（XGBoost/LightGBM 深度调参）。
- **贝叶斯整合 (0/5)**：完全空白。微生物组领域贝叶斯方法（如 `corncob` 的贝叶斯逻辑正态、Stan 驱动的多层次模型）可提供不确定性量化和先验知识整合，是当前最大方法学盲区。
- **网络推断 (2/5)**：SparCC 仅处理单组学组成效应，无跨组学网络推断。SPIEC-EASI（基于稀疏逆协方差/贝叶斯图形套索）和 gCoda（组成数据网络）是领域标准，均未覆盖。
- **纵向动态 (3/5)**：MaAsLin3 支持 mixed-effects，可处理重复测量，但仅限于关联分析框架。缺乏 GEE（处理缺失更稳健）、时间序列建模和动态网络推断。

---

### B. 多部位分析方法

| 分析目标 | 现有模块 | 覆盖度 | 缺失方法 |
|---------|---------|--------|---------|
| 位间组成比较 | cross_site_permanova | **3/5** | 多位点联合 PERMANOVA、adonis2 多变量模型 |
| 位间关联网络 | cross_site_network | **3/5** | 跨位点微生物-微生物网络、跨位点代谢物共变网络 |
| 来源追踪 | source_tracking (FEAST-style NNLS/EM) | **3/5** | SourceTracker (贝叶斯)、FastSpar、比例推断的不确定性量化 |
| 菌株传播 | strain_analyzer | **2/5** | 通用菌株传播推断（非 Strain2bScan 依赖）、传播网络重构 |
| 一致性分析 | cross_site_concordance | **4/5** | 更精细的效应量一致性检验 (concordance correlation coefficient) |
| 空间梯度 | — | **0/5** | 距离衰减曲线、Mantel correlogram、空间自相关 (Moran's I)、梯度森林 |

#### 评分理由

- **位间组成比较 (3/5)**：`cross_site_permanova` 实现了 per-site 的 univariate feature screen + multivariable adonis2-style R² 累积解释，但缺少正式的**多位点联合** PERMANOVA（将 site 作为随机效应或分层变量）。
- **位间关联网络 (3/5)**：Spearman 相关 + hub 检测已实现，但网络类型局限于"特征-靶标"二部网，缺乏**同组学跨位点**的网络（如口腔-肠道菌属共现网络）。
- **来源追踪 (3/5)**：NNLS/EM 双方法已 wiring，但 FEAST 仅是来源追踪方法之一。SourceTracker（基于 Dirichlet 的贝叶斯比例估计）在不确定性和先验表达上更优，且 `source_tracking` 对 source/sink 的标注依赖 metadata，自动化程度有限。
- **菌株传播 (2/5)**：`strain_analyzer` 强耦合 Strain2bScan 输出格式，非通用菌株分析模块。缺乏基于 SNP/ANI 的传播链推断（如跨样本菌株聚类 + 时空传播模型）。
- **一致性分析 (4/5)**：`cross_site_concordance` 实现了方向一致性筛选（Mann-Whitney + FDR + concordance flag），是较完整的实现。可补充 Lin's concordance correlation coefficient 等更精细的统计量。
- **空间梯度 (0/5)**：完全空白。人体微生物组多位点研究天然涉及空间维度（口腔→胃→肠→肛门距离梯度），距离衰减分析、空间自相关、梯度森林 (gradient forest) 是生态学标准工具。

---

### C. 数据预处理/质量控制

| 处理步骤 | 现有模块 | 覆盖度 | 备注 |
|---------|---------|--------|------|
| 批次效应校正 | — | **0/5** | 无 ComBat、Harmony、MMUPHin 等任何实现 |
| 缺失值插补 | — | **0/5** | 无 KNN-impute、RF-impute、贝叶斯插补 |
| 数据标准化 (TSS/CLR/CSS) | 分散于各模块 | **3/5** | MaAsLin3 支持 TSS/CLR/NONE；metabolome_pca 支持 zscore/log/log1p/clr；microbiome_marker 强制 CLR。但无统一标准化入口 |
| 稀疏数据处理 | — | **1/5** | 仅 data_validator 检测零值比例，无零膨胀模型、伪计数添加策略模块 |
| 离群值检测 | — | **1/5** | data_validator 有基础维度/缺失检查，无 AOD、Cook's distance、孤立森林等统计/机器学习离群检测 |

#### 评分理由

- **批次效应校正 (0/5)**：多中心研究/多批次测序的批次效应是微生物组/代谢组学的首要偏差来源。ComBat-seq（针对计数数据）、MMUPHin（针对微生物组）、Harmony（针对嵌入空间）均无实现。此缺口导致跨批次数据无法可靠整合。
- **缺失值插补 (0/5)**：代谢组学数据常有 20-50% 的缺失率（检测限以下）。KNN-impute、随机森林插补 (missForest)、最小二乘插补 是标准流程，当前完全依赖用户上传前处理。
- **数据标准化 (3/5)**：TSS (Total Sum Scaling)、CLR、z-score、log1p 在分散模块中可用，但缺乏 Cumulative Sum Scaling (CSS)、Rarefaction to even depth、TMM (edgeR) 等微生物组专用标准化。且标准化逻辑**分散在各个分析模块内部**，用户无法选择"先标准化，再分析"的显式流程。
- **稀疏数据处理 (1/5)**：微生物组数据高度稀疏（大量零值）。当前仅有 validator 报告零值比例，无零膨胀模型 (ZINB/ZILN)、伪计数策略优化（如 `bayes_zero` 或自适应 pseudo-count）。
- **离群值检测 (1/5)**：无专用模块。PCA/PCoA 可视化可辅助目视判断，但缺乏自动化统计检测（如基于马氏距离、孤立森林、或组成数据专用的 Aitchison outlier detection）。

---

### D. 高级统计检验

| 检验类型 | 现有模块 | 覆盖度 | 缺失 |
|---------|---------|--------|------|
| 组成数据检验 | ALDEx2 | **3/5** | ANCOM-BC (支持协变量、更稳健)、corncob (贝叶斯逻辑正态) |
| 多变量方差分析 | PERMANOVA, ANOSIM | **4/5** | 多位点分层 PERMANOVA (adonis2 with strata)、CAP (约束主坐标分析) |
| 配对检验 | — | **0/5** | Wilcoxon signed-rank (配对)、paired t-test、DESeq2 paired、配对 ALDEx2 |
| 重复测量 | MaAsLin3 (random_effects) | **3/5** | GEE (广义估计方程)、nlme::lme (更灵活的协方差结构)、MMRM |
| 协变量调整 | — | **1/5** | MaAsLin3 有 fixed_effects 但仅用于关联分析；无通用协变量调整差异检验模块 |
| 多层/混合效应 | MaAsLin3 (random_effects) | **2/5** | 通用 mixed-effects 框架 (lme4/glmmTMB) 用于 alpha/beta 多样性、marker discovery |

#### 评分理由

- **组成数据检验 (3/5)**：ALDEx2 通过 CLR + 蒙特卡洛采样 + Welch/Mann-Whitney/Kruskal 覆盖基本需求。但 ANCOM-BC 是更新一代方法，支持协变量调整和偏差校正，当前缺失。corncob 提供贝叶斯不确定性量化，亦未覆盖。
- **多变量方差分析 (4/5)**：PERMANOVA + ANOSIM 覆盖经典需求。但缺少 `adonis2` 的 `strata` 参数支持（用于配对/分层设计）和 CAP (canonical analysis of principal coordinates，即约束排序的 PERMANOVA 扩展)。
- **配对检验 (0/5)**：临床微生物组研究大量采用自身前后对照/配对设计（如干预前后、肿瘤-癌旁）。当前所有 marker 模块均为独立两组检验（Mann-Whitney / Welch），无配对等价物。
- **重复测量 (3/5)**：MaAsLin3 的 random_effects 参数可处理 subject-level 重复，但仅限于多变量关联。Alpha/beta 多样性的重复测量分析（如混合效应模型检验时间×组别交互）无专用模块。
- **协变量调整 (1/5)**：MaAsLin3 支持多固定效应，可部分调整协变量，但仅在关联分析语境下。标准的差异丰度分析（marker discovery）无协变量调整能力（如年龄、BMI、抗生素使用史的校正）。
- **多层/混合效应 (2/5)**：MaAsLin3 提供了一层 random_effects，但非通用框架。例如，无法对 alpha diversity 拟合 `lmer(Shannon ~ Group * Time + (1\|Subject))`，也无法对 beta diversity 进行基于距离的 PERMANOVA 配对层 (strata)。

---

## 三、综合雷达图评分

```
多组学整合方法        ████████████████████████████████████░░░░  2.83/5  (17/30)
  ├─ 矩阵相关/回归    ████████████████████████████████████░░░░  4/5
  ├─ 潜变量/因子模型  ██████████████████████████████████████████ 5/5
  ├─ 预测建模         ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 贝叶斯整合       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/5
  ├─ 网络推断         █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░  2/5
  └─ 纵向动态         ██████████████████████░░░░░░░░░░░░░░░░░░  3/5

多部位分析方法        ████████████████████████░░░░░░░░░░░░░░░░  2.50/5  (15/30)
  ├─ 位间组成比较     ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 位间关联网络     ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 来源追踪         ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 菌株传播         █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░  2/5
  ├─ 一致性分析       ████████████████████████████████████████░ 4/5
  └─ 空间梯度         ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/5

数据预处理/质控       ██████████████████░░░░░░░░░░░░░░░░░░░░░░  1.00/5  (5/25)
  ├─ 批次效应校正     ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/5
  ├─ 缺失值插补       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/5
  ├─ 数据标准化       ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 稀疏数据处理     ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1/5
  └─ 离群值检测       ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1/5

高级统计检验          ███████████████████░░░░░░░░░░░░░░░░░░░░░  2.17/5  (13/30)
  ├─ 组成数据检验     ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 多变量方差分析   ████████████████████████████████████████░ 4/5
  ├─ 配对检验         ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  0/5
  ├─ 重复测量         ██████████████████████░░░░░░░░░░░░░░░░░░  3/5
  ├─ 协变量调整       ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  1/5
  └─ 多层/混合效应    ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  2/5

─────────────────────────────────────────────────────────────────────
系统总评              ███████████████████████░░░░░░░░░░░░░░░░░  2.12/5  (50/115)
```

---

## 四、Top 10 最应优先补充的分析单元

> 排序依据：(1) 领域使用频率 / (2) 当前缺口严重性 / (3) 下游分析依赖度 / (4) 实现可行性

---

### P1. batch_correction — 批次效应校正

| 属性 | 内容 |
|------|------|
| **积木名称** | `batch_correction` |
| **方法学描述** | 采用 ComBat-seq（适用于计数数据）或 ComBat（适用于连续数据）对微生物组/代谢组数据进行批次效应校正。支持多批次协变量保留，确保生物学信号不受测序批次或实验中心的系统性偏差影响。 |
| **输入规格** | `df`: features × samples 计数/丰度矩阵; `metadata_df`: 样本注释表，须含 `batch_column` (批次标签) 和可选 `biological_covariates` (需保留的生物学协变量) |
| **输出规格** | `corrected_matrix`: 校正后矩阵 (同维度); `combat_params`: 估计的批次参数; `plot_data`: PCA 校正前后对比图; `report`: 批次解释方差比例 |
| **实现复杂度** | **中等** |
| **推荐实现路径** | Python 包 `pymorhp` (ComBat-seq 移植) 或调用 R `sva::ComBat` / `sva::ComBat_seq` via `rpy2`。对于微生物组专用场景，可直接封装 `MMUPHin::adjust_batch`。 |
| **优先级理由** | 多中心/多批次研究的数据整合**前置必要条件**。当前无任何实现，导致用户必须外部处理数据后再上传，破坏了端到端分析闭环。下游所有整合分析（MOFA、DIABLO、Procrustes）的可靠性均直接依赖此步骤。 |

---

### P2. paired_differential_test — 配对差异检验

| 属性 | 内容 |
|------|------|
| **积木名称** | `paired_differential_test` |
| **方法学描述** | 针对配对/自身前后对照设计（如干预前 vs 干预后、肿瘤 vs 癌旁）的组成数据差异检验。采用配对 Wilcoxon signed-rank 检验 CLR 转换后的丰度，或配对 ALDEx2 (CLR + 蒙特卡洛采样 + paired Wilcoxon)。 |
| **输入规格** | `df`: features × samples; `metadata_df`: 须含 `group_column` (二水平分组) 和 `subject_column` (配对 ID); `method`: ["paired_wilcoxon", "paired_aldex2", "deseq2_paired"] |
| **输出规格** | `significant_features`: DataFrame (feature, effect_size, pvalue, padj, direction); `volcano_plot`: Plotly; `statistics`: 配对样本数、检验类型摘要 |
| **实现复杂度** | **中等** |
| **推荐实现路径** | Python 自研（`scipy.stats.wilcoxon` on CLR-transformed paired samples）或 R `ALDEx2::aldex(..., paired.test=TRUE)` via `rpy2`。DESeq2 paired 模式可作为高阶备选。 |
| **优先级理由** | 临床/干预研究中最常见的设计类型之一。当前所有 marker discovery 模块均为**非配对**检验，直接应用于配对数据会导致统计效能损失和假阳性膨胀。与现有 `microbiome_marker`/`aldex2` 模块形成互补而非重叠。 |

---

### P3. ancom_bc — ANCOM-BC 组成数据差异分析

| 属性 | 内容 |
|------|------|
| **积木名称** | `ancom_bc` |
| **方法学描述** | ANCOM-BC (Analysis of Composition of Microbiomes with Bias Correction) 通过估计并校正样本间对数倍数变化的抽样偏差，实现协变量调整的差异丰度检验。支持多组比较、重复测量、和复杂协变量结构。 |
| **输入规格** | `df`: features × samples 计数矩阵; `metadata_df`: 样本注释; `group_column`: 主效应; `covariates`: 可选协变量列表; `random_effects`: 可选随机效应列 |
| **输出规格** | `significant_features`: DataFrame (W-statistic, pvalue, padj, bias_corrected_lfc); `volcano_plot`: Plotly; `sensitivity_plot`: 差异特征检出数随 cutoff 变化曲线 |
| **实现复杂度** | **中等** |
| **推荐实现路径** | R 包 `ANCOMBC` (v2.0+) via `rpy2`。该包是微生物组差异分析的事实标准之一，直接封装 `ancombc2()` 函数，参数映射清晰。 |
| **优先级理由** | ANCOM-BC 是当前微生物组差异分析领域**引用增长最快**的方法之一，解决了 ALDEx2 无法处理协变量和 DESeq2 对组成数据假设不成立的问题。填补"协变量调整 + 组成数据"双重需求缺口，与现有 `aldex2`/`songbird`/`maaslin3` 形成方法学梯队。 |

---

### P4. spiec_easi — SPIEC-EASI 组成数据网络推断

| 属性 | 内容 |
|------|------|
| **积木名称** | `spiec_easi` |
| **方法学描述** | Sparse InversE Covariance Estimation for Ecological Association Inference。通过稀疏逆协方差估计（ graphical lasso / MB / 贝叶斯套索）从组成数据中推断微生物-微生物或微生物-代谢物的条件独立网络，克服 SparCC 仅处理边际相关的局限。 |
| **输入规格** | `df`: features × samples (微生物组) 或 `df`+`df2` (跨组学); `metadata_df`: 可选; `method`: ["glasso", "mb", "slr"]; `lambda_min_ratio`: 正则化路径; `pulsar_params`: 稳定性选择参数 |
| **输出规格** | `adjacency_matrix`: 稀疏邻接矩阵; `network_data`: 节点/边列表 (供可视化); `plot_data`: 网络图 (Plotly 或导出至 Cytoscape); `stability`: 各边的稳定性分数 |
| **实现复杂度** | **复杂** |
| **推荐实现路径** | R 包 `SpiecEasi` via `rpy2`。该包已成熟且维护活跃，封装 `spiec.easi()` + `getRefit()` + `adj2igraph()` 即可。Python 原生实现（`sklearn.covariance.GraphicalLasso`）需自行处理组成数据转换和稳定性选择，成本过高。 |
| **优先级理由** | SparCC 仅能推断**边际相关**网络，而 SPIEC-EASI 推断**条件独立**网络（去除其他变量影响后的直接关联），是网络分析的方法学升级。在多组学语境下，SPIEC-EASI 可同时处理微生物组+代谢组两个数据块，填补跨组学网络推断空白。 |

---

### P5. mixed_effects_diversity — 混合效应多样性分析

| 属性 | 内容 |
|------|------|
| **积木名称** | `mixed_effects_diversity` |
| **方法学描述** | 对 Alpha 多样性（ richness, Shannon, Simpson 等）或 Beta 多样性距离拟合线性混合效应模型 (LMM)，支持时间×组别交互、随机截距/斜率、和多种协方差结构。对 Beta 多样性采用 PERMANOVA-with-strata 或 distance-based LMM (dbrda/adonis2)。 |
| **输入规格** | `df`: features × samples; `metadata_df`: 须含 `group_column`, `subject_column`, 可选 `time_column`; `diversity_type`: ["alpha", "beta"]; `alpha_metric`: ["shannon", "simpson", ...]; `beta_metric`: ["braycurtis", "unweighted_unifrac", ...]; `fixed_formula`: 如 "Group * Time + Age + BMI"; `random_formula`: 如 "(1\|Subject)" |
| **输出规格** | `model_summary`: 固定效应系数表 (estimate, SE, t/z, p); `random_effects_summary`: 随机效应方差分量; `plot_data`: 拟合值 vs 观测值图、残差诊断图; `icc`: 组内相关系数 |
| **实现复杂度** | **复杂** |
| **推荐实现路径** | Alpha: Python `statsmodels.MixedLM` 或 R `lme4::lmer` / `lmerTest::lmer` via `rpy2`。Beta: R `vegan::adonis2(..., strata=Subject)` 或 `mvabund::manyglm` / `PLNmodels`。推荐统一走 `rpy2` + `lme4` + `vegan` 路线。 |
| **优先级理由** | 纵向/重复测量设计在微生物组临床研究中极常见。当前 MaAsLin3 仅处理特征级关联，无多样性层面的混合效应建模。此模块可直接支撑"干预措施对菌群多样性随时间变化的影响"这一核心科学问题。 |

---

### P6. imputation — 缺失值插补

| 属性 | 内容 |
|------|------|
| **积木名称** | `imputation` |
| **方法学描述** | 针对代谢组学/蛋白质组学数据中常见的非随机缺失 (MNAR, 低于检测限) 和随机缺失 (MAR) 进行插补。支持 KNN 插补（适用于 MAR）、随机森林插补 missForest（适用于复杂非线性关系）、和基于检测限的 QRILC（适用于 MNAR）。 |
| **输入规格** | `df`: features × samples 矩阵 (含 NA/0); `data_type`: ["metabolome", "proteome", "microbiome"]; `method`: ["knn", "rf", "qrilc", "min", "half_min"]; `missing_threshold`: 特征最大允许缺失率 (默认 0.5) |
| **输出规格** | `imputed_matrix`: 插补后矩阵; `imputation_summary`: 各特征缺失率、插补方法分配、插补值分布; `plot_data`: 插补前后 PCA 对比、缺失模式热图 |
| **实现复杂度** | **中等** |
| **推荐实现路径** | Python `sklearn.impute.KNNImputer` + `missForest` 的 Python 移植 (`missforest`) 或 R `missForest::missForest` via `rpy2`。QRILC 可用 R `imputeLCMD::impute.QRILC`。代谢组学专用流程推荐封装 `metaboanalyst` 的插补策略子集。 |
| **优先级理由** | 代谢组学数据上传后几乎**必然存在缺失值**，当前系统无预处理模块，迫使所有下游分析依赖外部清洗。此模块是代谢组学端到端分析的关键前置步骤，且与 `batch_correction` 共同构成预处理层双支柱。 |

---

### P7. normalization — 标准化专用模块

| 属性 | 内容 |
|------|------|
| **积木名称** | `normalization` |
| **方法学描述** | 提供微生物组和代谢组数据的标准化统一入口，支持微生物组专用方法（TSS, CSS, Rarefaction, TMM, CLR, ILR）和代谢组学方法（z-score, Pareto scaling, Quantile normalization, Sum normalization）。输出标准化矩阵供下游分析直接消费。 |
| **输入规格** | `df`: features × samples; `data_type`: ["microbiome", "metabolome"]; `method`: 枚举（根据 data_type 动态可选）; `reference_samples`: 可选参考样本子集 (用于某些方法) |
| **输出规格** | `normalized_matrix`: 标准化后矩阵; `normalization_params`: 缩放因子/参考值 (用于新样本变换); `plot_data`: 标准化前后密度分布箱线图; `report`: 各样本读取数/总和摘要 |
| **实现复杂度** | **简单** |
| **推荐实现路径** | Python 自研。TSS/CLR/ILR 可用 `scipy` + `numpy` 直接实现。CSS 可移植 `metagenomeSeq::cumNorm` 逻辑（计算分位数 + 累积和缩放）。TMM 参考 `edgeR::calcNormFactors`。代谢组学方法更标准。整体逻辑清晰，无需依赖 R。 |
| **优先级理由** | 当前标准化逻辑**分散在 7+ 个分析模块内部**（microbiome_marker 强制 CLR、metabolome_pca 支持 zscore/log、MaAsLin3 有 TSS/CLR），用户无法显式控制标准化步骤，也无法复用标准化矩阵。统一入口可提升可组合性和分析可复现性。实现简单，收益明确。 |

---

### P8. spatial_gradient — 空间梯度分析

| 属性 | 内容 |
|------|------|
| **积木名称** | `spatial_gradient` |
| **方法学描述** | 针对人体多部位微生物组数据（口腔、胃、小肠、结肠、粪便等）分析群落组成沿解剖位点的空间梯度模式。包括距离衰减曲线（community similarity vs. anatomical distance）、Mantel correlogram（多距离等级相关）、和梯度森林（识别对环境梯度响应最强的特征）。 |
| **输入规格** | `df`: features × samples; `metadata_df`: 须含 `site_column` (解剖部位) 和/或 `spatial_distance_matrix` (部位间解剖距离矩阵); `method`: ["distance_decay", "mantel_correlogram", "gradient_forest"] |
| **输出规格** | `decay_plot`: 距离-相似性散点 + 拟合曲线; `correlogram_plot`: Mantel r 随距离等级变化; `gradient_forest_importance`: 各特征对空间梯度的重要性排序; `plot_data`: 综合可视化 |
| **实现复杂度** | **中等** |
| **推荐实现路径** | Python 自研。距离衰减可用 `scipy.stats` + `sklearn.metrics.pairwise_distances`。Mantel correlogram 可复用现有 `mantel_test` 逻辑在多距离切分上迭代。梯度森林需 R `extendedForest::gradientForest` via `rpy2` 或简化版用随机森林回归 (site index ~ feature abundance)。 |
| **优先级理由** | 多部位分析维度中**唯一完全空白**（0/5）的类别。人体微生物组研究的核心叙事之一是"不同解剖部位的菌群如何连续变化"，距离衰减和梯度分析是生态学标准范式。与现有 cross_site_permanova/concordance 形成"差异 vs 梯度"互补。 |

---

### P9. outlier_detection — 离群值检测

| 属性 | 内容 |
|------|------|
| **积木名称** | `outlier_detection` |
| **方法学描述** | 基于多种策略检测微生物组/代谢组样本离群值：(1) 基于 Aitchison 距离的组成数据离群检测；(2) 基于 PCA/PCoA 的马氏距离 + 卡方检验；(3) 孤立森林 (Isolation Forest) 无监督检测；(4) Cook's distance 用于有监督场景。输出离群样本标记和诊断图。 |
| **输入规格** | `df`: features × samples; `metadata_df`: 可选; `method`: ["aitchison", "mahalanobis_pca", "isolation_forest", "cooks_distance"]; `group_column`: 可选分组（用于分组内检测）; `threshold`: 离群判定阈值 |
| **输出规格** | `outlier_flags`: DataFrame (sample_id, score, is_outlier); `plot_data`: PCA/PCoA 离群标注图、得分分布直方图; `report`: 各方法检出的离群样本交集/并集 |
| **实现复杂度** | **简单** |
| **推荐实现路径** | Python 自研。Aitchison 距离 = CLR 后欧氏距离（可用现有 CLR 逻辑）。马氏距离 + 卡方检验可用 `scipy.stats`。孤立森林直接用 `sklearn.ensemble.IsolationForest`。整体无需外部依赖。 |
| **优先级理由** | 质控是分析可信度的**守门人**。当前 `data_validator` 仅有格式/维度/缺失检查，无统计离群检测。一个污染样本或错误标记样本可严重扭曲 PERMANOVA、Procrustes、MOFA 等所有下游结果。实现简单但系统级价值高。 |

---

### P10. bayesian_integration — 贝叶斯多组学整合

| 属性 | 内容 |
|------|------|
| **积木名称** | `bayesian_integration` |
| **方法学描述** | 基于贝叶斯层次模型整合微生物组与代谢组数据。采用贝叶斯典型相关分析 (Bayesian CCA) 或贝叶斯因子分析（如 Bhattacharya & Dunson 的稀疏因子模型）估计组学间的共享潜变量，同时提供后验不确定性量化。支持先验知识的融入（如已知代谢通路-微生物关联作为先验）。 |
| **输入规格** | `df`: 微生物组 features × samples; `df2`: 代谢组 features × samples; `metadata_df`: 可选; `n_factors`: 潜变量数; `prior_network`: 可选先验关联矩阵 (feature × feature); `n_samples`: MCMC 采样数 |
| **输出规格** | `posterior_factors`: 潜变量后验分布摘要 (mean, sd, HPD interval); `factor_loadings`: 各组学对潜因子的载荷; `plot_data`: 潜因子样本得分图、载荷热图; `model_fit`: LOO-CV / WAIC 模型比较指标 |
| **实现复杂度** | **复杂** |
| **推荐实现路径** | Python `numpyro` / `PyMC` 自研或 R `rstan` + `CCA` 贝叶斯实现。推荐 `numpyro`（基于 JAX，兼容现有 Python 栈）实现稀疏贝叶斯因子模型，参考 Bhattacharya & Dunson (2011) 的稀疏因子先验。Stan 模型代码可复用社区现有模板。 |
| **优先级理由** | 多组学整合维度中**唯一完全空白**（0/5）的类别。贝叶斯方法的核心优势在于**不确定性量化**——当前所有整合方法（MOFA/PLS/CCA）仅提供点估计，无法回答"组学关联的后验可信度是多少"。对于样本量有限（n<50）的研究尤其重要。虽实现复杂，但作为高端差异化功能具有战略价值。 |

---

## 五、补充建议与实施路线图

### 5.1 短期（1-2 个月，高 ROI）

| 优先级 | 模块 | 工作量 | 影响面 |
|--------|------|--------|--------|
| P7 | `normalization` | 简单 | 所有下游模块的基础依赖 |
| P9 | `outlier_detection` | 简单 | 质控守门人，全分析流程受益 |
| P1 | `batch_correction` | 中等 | 多批次研究的前置必要条件 |
| P6 | `imputation` | 中等 | 代谢组学分析的关键前置 |
| P2 | `paired_differential_test` | 中等 | 临床配对研究高频需求 |

> **建议优先实施 P7 + P9**：两者实现简单，共同构成"预处理 + 质控"层的最小可用集合。`normalization` 统一现有分散逻辑，`outlier_detection` 弥补当前质控盲区。

### 5.2 中期（3-4 个月，方法学纵深）

| 优先级 | 模块 | 工作量 | 战略价值 |
|--------|------|--------|----------|
| P3 | `ancom_bc` | 中等 | 差异分析方法学升级，协变量支持 |
| P5 | `mixed_effects_diversity` | 复杂 | 纵向研究核心统计框架 |
| P8 | `spatial_gradient` | 中等 | 多部位分析维度补全 |
| P4 | `spiec_easi` | 复杂 | 网络分析从边际相关升级到条件独立 |

### 5.3 长期（5-6 个月，差异化竞争力）

| 优先级 | 模块 | 工作量 | 差异化价值 |
|--------|------|--------|------------|
| P10 | `bayesian_integration` | 复杂 | 唯一性高端功能，不确定性量化 |
| — | `gee_longitudinal` | 中等 | 与 mixed_effects 形成方法学对照 |
| — | `source_tracker_bayesian` | 中等 | 来源追踪的贝叶斯升级（SourceTracker） |

### 5.4 架构层面的建议

1. **新建 `preprocessing` 类别**：将 `batch_correction`、`imputation`、`normalization`、`outlier_detection` 从 `individual_omics` 中剥离，组成独立预处理层，使分析 DAG 的语义更清晰（预处理 → 单组学 → 整合 → 可视化）。

2. **标准化与分析的解耦**：当前 `microbiome_marker` 强制 CLR、`metabolome_pca` 内置 zscore 的做法应逐步重构为依赖前置 `normalization` 模块的输出，使分析模块聚焦统计方法本身。

3. **R 服务化封装**：中期以上复杂模块（ANCOM-BC、SPIEC-EASI、mixed-effects）大量依赖 R 生态。建议将 `rpy2` 调用封装为独立的 `RService` 类（类似现有 `AnalysisEngine`），统一管理 R 会话、错误转换和临时文件，避免每个 wrapper 重复处理 R-Python 边界。

---

## 六、总结

Meta2bAnalyst 在多组学**潜变量/因子模型**维度已达领域先进水平（MOFA+/O2PLS/DIABLO 全覆盖），在**多部位关联分析**维度也有较完整布局（cross_site_permanova / network / concordance）。系统的核心缺口集中在：

1. **数据预处理层近乎空白**（批次校正、缺失值插补、离群检测）
2. **统计检验对复杂实验设计支持不足**（配对、协变量调整、通用混合效应）
3. **贝叶斯方法完全缺失**（不确定性量化、先验整合）
4. **网络推断停留在边际相关**（条件独立网络、跨组学网络推断）
5. **空间梯度维度未覆盖**（多部位分析的自然延伸）

通过按本报告优先级补充 **10 个分析单元**，系统可从"方法丰富但前置薄弱"的现状，演进为"端到端覆盖、统计严谨、可处理复杂实验设计"的生产级多组学分析平台。
