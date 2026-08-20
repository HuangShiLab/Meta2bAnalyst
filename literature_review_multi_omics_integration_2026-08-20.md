# Meta2bAnalyst 多组学整合分析文献调研报告

> **调研日期**: 2026-08-20
> **调研人**: 多组学整合分析文献调研员
> **项目**: Meta2bAnalyst — 微生物组多组学分析平台
> **任务**: 搜集和整理多组学整合分析的典型方法学论文，提取可复用的"分析积木"

---

## 目录

1. [方向1：多组学整合统计方法](#方向1多组学整合统计方法)
2. [方向2：微生物组-代谢组整合](#方向2微生物组-代谢组整合)
3. [方向3：时间序列/纵向多组学](#方向3时间序列纵向多组学)
4. [方向4：多组学网络推断](#方向4多组学网络推断)
5. [缺失分析单元汇总表](#缺失分析单元汇总表)
6. [参考文献](#参考文献)

---

## 方向1：多组学整合统计方法

### 论文1: MOFA+: a statistical framework for comprehensive integration of multi-modal single-cell data

- **引用**: Argelaguet R, Arnol D, Bredikhin D, Deloro Y, Velten B, Marioni JC, Stegle O. *Genome Biology*, 2020, 21(1):111. (被引 >4000次)
- **组学**: 不限定具体组学类型；已应用于：DNA甲基化、RNA-seq、基因突变、药物反应、scRNA-seq + scATAC-seq + surface protein (CITE-seq)
- **方法学摘要**: MOFA+ 是贝叶斯组因子分析的扩展版本，用于无监督整合多模态数据。核心思想是将每个数据矩阵分解为共享的样本因子矩阵（N×F）和各模态特异的权重矩阵（F×Dm）。通过变分推断学习潜在因子，每个因子可解释不同组学层面的变异。MOFA+ 明确区分跨模态共享的变异轴和各模态私有的变异轴，支持缺失数据（某些样本缺少某些模态），并通过 ARD（Automatic Relevance Determination）自动剪枝不活跃的因子。
- **分析流程**:
  1. **数据预处理**: 每个组学层独立进行 log 变换、标准化、去批次效应
  2. **模型设定**: 指定因子数 K（默认10），选择各模态的似然函数（Gaussian/Poisson/Bernoulli）
  3. **变分推断**: 使用 mofapy2 (Python) 或 MOFA2 (R) 进行训练，默认1000次迭代
  4. **因子解读**: 计算每个因子在各模态解释的方差比例 (R²)，识别主导模态
  5. **下游分析**: 样本聚类、异常值检测、数据补全、与临床变量关联
- **可提取积木**:
  - 积木名: MOFA+ 因子分解 | 输入: 2+ 组学矩阵（行=样本，列=特征） | 输出: 样本因子得分矩阵、各模态特征载荷、方差解释率 | 依赖: 数据预处理（标准化、log变换）
  - 积木名: 跨模态方差分解 | 输入: MOFA+ 训练结果 | 输出: 各因子在各模态的方差解释百分比 | 依赖: MOFA+ 因子分解
  - 积木名: 多模态样本聚类 | 输入: 样本因子得分 | 输出: 样本亚群标签 | 依赖: MOFA+ 因子分解

---

### 论文2: Regularized Generalized Canonical Correlation Analysis (RGCCA)

- **引用**: Tenenhaus A, Tenenhaus M. *Psychometrika*, 2011, 76(2):257-284; Tenenhaus A et al. *European Journal of Operational Research*, 2014, 238(2):391-403. (RGCCA框架系列论文)
- **组学**: 通用多组学框架；已应用于：mRNA-miRNA-甲基化整合、多平台基因表达整合
- **方法学摘要**: RGCCA 是 Canonical Correlation Analysis (CCA) 向多块数据（>2个数据集）的推广。给定 J 个数据矩阵 X₁, X₂, ..., X_J（行均为相同样本），RGCCA 通过用户定义的设计矩阵 C 指定哪些数据块之间需要建立关联，然后迭代寻找每块数据的线性组合（成分），使得相连块之间的协方差（或相关系数）之和最大化。通过调节 τ（正则化参数）可控制成分的方差，τ=1 对应 PCA 模式，τ=0 对应 CCA 模式。SGCCA（Sparse RGCCA）进一步引入 L1 惩罚实现变量选择。
- **分析流程**:
  1. **数据准备**: 各组学数据矩阵中心化/标准化，确保行（样本）对齐
  2. **设计矩阵构建**: 定义 C 矩阵，Cⱼₖ=1 表示块 j 和块 k 需要关联，0 表示不关联
  3. **方案选择**: 选择优化方案（centroid/factorial/horst），centroid 方案最大化协方差绝对值之和
  4. **正则化参数估计**: 使用 Schafer-Strimmer 收缩估计法估计各块的 τ 参数（当 n < p 时自动启用 dual algorithm）
  5. **成分提取**: 迭代算法提取多组成分，计算 inner AVE（Average Variance Explained）评估模型质量
  6. **可视化与解读**: 样本投影图、特征载荷图、circos 图展示跨块关联
- **可提取积木**:
  - 积木名: RGCCA 多块关联分析 | 输入: 2+ 数据块 + 设计矩阵 C | 输出: 每块的成分得分、特征载荷、块间协方差结构 | 依赖: 数据标准化
  - 积木名: 稀疏多块变量选择 (SGCCA) | 输入: 数据块 + 每块期望选择的变量数 | 输出: 稀疏成分、被选中的关键特征列表 | 依赖: RGCCA 框架
  - 积木名: 跨组学 circos 关联图 | 输入: RGCCA 成分载荷 | 输出: 可视化跨组学特征关联网络 | 依赖: RGCCA 成分提取

---

### 论文3: DIABLO — Data Integration Analysis for Biomarker discovery using Latent cOmponents

- **引用**: Singh A, Shannon CP, Gautier B, Rohart F, Vacher M, Tebbutt SJ, K-A Lê Cao. *Bioinformatics*, 2019, 35(17):3055-3062. (mixOmics框架)
- **组学**: 已应用于：转录组+蛋白组+代谢物、RNA-seq + miRNA + CpG甲基化 + 蛋白
- **方法学摘要**: DIABLO 是有监督的多组学整合框架，基于 Sparse Generalized Canonical Correlation Analysis (sGCCA) 和 sparse PLS-DA 的扩展。与 MOFA+ 的无监督探索不同，DIABLO 以表型/分组信息 Y 为响应变量，同时整合多个组学数据块 X₁, X₂, ..., X_Q，目标是找到能最好区分表型组的稀疏多组学特征面板。通过设计矩阵（通常设为0.1以平衡分类性能和块间相关性）控制各块之间的关联强度。使用 block.splsda 函数实现，支持 keepX 参数指定每块每成分保留的特征数，内置 predict() 可对新样本分类。
- **分析流程**:
  1. **数据预处理**: 缺失值处理、log变换、中心化；若数据量不平衡需先筛选高变异特征
  2. **设计矩阵设定**: 通常设为0.1（强调分类），或0（仅利用Y做监督）
  3. **交叉验证调参**: 使用 tune.block.splsda 进行10次10折交叉验证，依次优化成分数、每块每成分的 keepX（保留特征数）
  4. **模型训练**: block.splsda 训练最终模型，提取稀疏成分
  5. **性能评估**: 计算分类错误率、auroc、各块的 ROC 曲线
  6. **结果可视化**: plotIndiv（样本散点图）、plotVar（变量相关性 circos 图）、cim（聚类热图）
- **可提取积木**:
  - 积木名: DIABLO 多组学分类器 | 输入: 多组学矩阵 + 表型标签 Y | 输出: 分类模型、预测性能指标、各块关键特征 | 依赖: 数据预处理、特征预筛选
  - 积木名: 多组学特征选择 | 输入: DIABLO 模型 | 输出: 每块每成分的 top 特征列表及载荷 | 依赖: DIABLO 模型训练
  - 积木名: 跨组学关联 circos 图 | 输入: DIABLO 成分的变量载荷 | 输出: 跨组学特征关联 circos 可视化 | 依赖: DIABLO 特征选择

---

## 方向2：微生物组-代谢组整合

### 论文1: Learning representations of microbe–metabolite interactions (mmvec)

- **引用**: Morton JT, Aksenov AA, Nothias LF, Foulds JR, Quinn RA, Badri MH, ... Knight R. *Nature Methods*, 2019, 16(12):1306-1314. (被引 >360次)
- **组学**: 16S rRNA/宏基因组（微生物） + LC-MS/GC-MS 代谢组（代谢物）
- **方法学摘要**: mmvec 是一种基于神经网络的微生物-代谢物共现概率估计方法。模型假设：给定一个微生物样本 xₖ，从中随机抽取一个微生物 μ，通过嵌入向量 u_μ 和 v_ν 计算该微生物存在条件下各代谢物 ν 的条件概率 p(ν|μ) = softmax(v_ν·u_μ + biases)。然后以该概率向量从多项分布中抽取代谢物丰度 yₖ。通过 MAP 估计（ADAM 优化器）学习嵌入矩阵 U（微生物）和 V（代谢物）。该模型天然处理组成性数据（softmax 等价于逆CLR变换），在F1 score、precision、recall上显著优于 Pearson/Spearman/SparCC。已在 TensorFlow 中实现，支持GPU加速。
- **分析流程**:
  1. **数据输入**: 微生物丰度表（counts或相对丰度）+ 代谢物丰度表（连续值，视为近似计数）
  2. **模型训练**: 每次随机从样本中抽取一个微生物 read，预测该样本完整代谢物谱；运行多个 epoch 至收敛
  3. **交叉验证**: 留出部分样本，计算预测代谢物丰度与观测值的 SSE 评估泛化性能
  4. **条件概率矩阵提取**: 从学习到的 U 和 V 计算所有微生物-代谢物对的条件概率
  5. **排序与可视化**: 对每对微生物-代谢物计算共现概率排序，使用 biplot 展示微生物和代谢物在共享嵌入空间中的位置
- **可提取积木**:
  - 积木名: mmvec 微生物-代谢物共现概率估计 | 输入: 微生物丰度表 + 代谢物丰度表 | 输出: 微生物-代谢物条件概率矩阵、嵌入向量 U/V | 依赖: 数据对齐（相同样本）
  - 积木名: mmvec Biplot 可视化 | 输入: mmvec 嵌入矩阵 | 输出: 微生物和代谢物的共享空间投影图 | 依赖: mmvec 模型训练
  - 积木名: 微生物-代谢物关联排序 | 输入: mmvec 条件概率矩阵 | 输出: 按概率排序的微生物-代谢物对列表 | 依赖: mmvec 概率估计

---

### 论文2: MIMOSA2: a metabolic network-based tool for inferring mechanism-supported relationships in microbiome-metabolome data

- **引用**: Noecker C, Eng A, Muller E, Borenstein E. *Bioinformatics*, 2022, 38(6):1615-1623. (MIMOSA1: Noecker et al. *mSystems*, 2016)
- **组学**: 16S rRNA（ASV/OTU）或宏基因组 KO + 代谢组（需代谢物鉴定为 KEGG/HMDB ID）
- **方法学摘要**: MIMOSA2 是一种基于代谢网络模型的知识驱动整合方法。其工作流程：(1) 使用 PICRUSt/PICRUSt2 或 HUMAnN2 从微生物组成数据推断功能基因（KO）丰度；(2) 基于 KEGG 代谢网络模型，将 KO 丰度转换为 Community Metabolic Potential (CMP) 分数，即群落产生/消耗各代谢物的预估能力；(3) 将 CMP 与实测代谢物丰度进行回归比较，评估代谢物变异中可被微生物代谢潜力解释的比例；(4) 识别对特定代谢物变异贡献最大的物种/ASV。MIMOSA2 提供 web 工具（Shiny app）和 R 包，可生成有机制支持的假设。
- **分析流程**:
  1. **数据输入**: 微生物特征表（16S ASV/OTU 或 KO 表）+ 代谢物丰度表（需含代谢物名称/HMDB/KEGG ID）
  2. **功能基因推断**: 16S 数据通过 PICRUSt2 推断 KO 丰度；宏基因组数据可直接提供 KO 或通路丰度
  3. **CMP 计算**: 基于 KEGG 代谢反应数据库，将 KO 丰度映射为代谢物层面的 community metabolic potential
  4. **回归验证**: 对每个代谢物，用 CMP 预测其丰度，计算 R² 和显著性（FDR < 0.1）
  5. **贡献分解**: 对显著可预测的代谢物，计算每个物种/ASV 对其变异的贡献比例
  6. **结果输出**: 可预测的代谢物列表、各代谢物的关键贡献物种、代谢通路富集
- **可提取积木**:
  - 积木名: MIMOSA2 代谢潜力-实测代谢物整合 | 输入: 微生物组成表 + 代谢物丰度表 + 参考数据库（KEGG/Greengenes/SILVA） | 输出: CMP 分数、代谢物可预测性评分、物种贡献度 | 依赖: PICRUSt2/HUMAnN 功能注释
  - 积木名: 群落代谢潜力计算 | 输入: KO 丰度表 + KEGG 代谢网络 | 输出: 各样本各代谢物的 CMP 分数 | 依赖: 功能基因注释
  - 积木名: 代谢物-物种贡献分解 | 输入: MIMOSA2 回归结果 | 输出: 每个代谢物的 top 贡献物种及其解释比例 | 依赖: MIMOSA2 代谢潜力整合

---

## 方向3：时间序列/纵向多组学

### 论文1: Dynamic Bayesian Networks for Integrating Multi-omics Time Series Microbiome Data (PALM)

- **引用**: Ruiz-Perez D, Lugo-Martinez J, Bourguignon N, Mathee K, Lerner B, Bar-Joseph Z, Narasimhan G. *mSystems*, 2021, 6(2):e01105-20. (被引 >77次)
- **组学**: 宏基因组（微生物分类）+ 宏转录组（基因表达）+ 代谢组 + 宿主转录组（IBD纵向队列，iHMP项目）
- **方法学摘要**: PALM（Pipeline for Analysis of Longitudinal Multi-omics）是针对纵向多组学微生物组数据的计算流程。核心步骤：(1) 对每个个体的每个组学层，使用 cubic B-spline 拟合时间曲线并进行插值；(2) 使用动态时间规整（DTW）或曲线对齐将不同个体的时间序列对齐到参考个体，解决采样间隔不一致和个体进度差异问题；(3) 构建生物学启发的骨架约束（skeleton constraints），限制 DBN 中允许的边方向（如：宿主基因 → 微生物分类 → 微生物基因 → 代谢物 → 下一时刻微生物分类）；(4) 使用两阶段 DBN 学习结构（intra-slice 边 + inter-slice 边）和参数，通过 bootstrap 评估边稳定性。该流程可预测未来微生物组成，且预测精度优于静态方法和 gLV 模型。
- **分析流程**:
  1. **时间曲线拟合**: 对每个个体的每个特征（微生物/基因/代谢物）用 cubic B-spline 拟合，插值到统一时间网格
  2. **时间对齐**: 选择一个参考个体，将其余个体的时间曲线通过 DTW 对齐到参考曲线，得到 warping function
  3. **对齐传播**: 将 warping function 应用到该个体的所有其他组学层（假设组学间时间同步）
  4. **对齐质量过滤**: 计算对齐误差，剔除对齐质量差的样本
  5. **骨架约束定义**: 根据生物学先验定义允许的边类型和方向（宿主→微生物→基因→代谢物→微生物(t+1)）
  6. **DBN 结构学习**: 使用 hill-climbing 等搜索算法，在约束下学习两阶段 DBN 结构
  7. **参数学习与 bootstrap 验证**: 学习回归系数，用 bootstrap（如30次重复）评估边的稳定性
  8. **预测验证**: 用学习到的 DBN 预测未来时间点的微生物组成，与观测值比较 MAE
- **可提取积木**:
  - 积木名: PALM 纵向多组学对齐 | 输入: 多组学时间序列（不同个体、不同采样间隔） | 输出: 对齐后的统一时间网格数据、warping functions | 依赖: 每个组学层的独立时间曲线拟合
  - 积木名: 骨架约束 DBN 网络推断 | 输入: 对齐后的多组学数据 + 骨架约束矩阵 | 输出: 时序 DBN 结构（intra-edge + inter-edge）、边稳定性评分 | 依赖: PALM 时间对齐
  - 积木名: 纵向微生物组成预测 | 输入: 学习到的 DBN + 当前状态 | 输出: 未来时间点的微生物组成预测 | 依赖: DBN 参数学习

---

### 论文2: Multi-omics time-series analysis in microbiome research (综述)

- **引用**: Sherwani MK, et al. *Frontiers in Bioinformatics*, 2025. (被引 >37次)
- **组学**: 综述，涵盖所有组学类型
- **方法学摘要**: 该综述系统总结了纵向多组学分析的方法学全景。关键方法分类：(1) **降维**: PCA/PCoA（最常用）、t-SNE/UMAP（非线性）、MOFA/MEFISTO（时序扩展）；(2) **回归与分类**: 线性混合模型（LMM，考虑个体内相关性）、sPLS-DA（时间演化判别特征）；(3) **时序建模**: 动态贝叶斯网络（DBN，如 PALM）、向量自回归模型（VAR，假设线性关系）、状态空间模型、RNN/LSTM（深度学习）、时间网络/多层网络；(4) **标准化框架**: 强调各组学独立预处理（转录组标准化+特征选择、代谢组 log 变换+降维、微生物组 CLR 变换+稀疏过滤、蛋白组缩放+缺失值填补），然后整合分析。提出 MEFISTO（MOFA 的时空扩展）作为处理纵向数据的无监督替代方案。
- **分析流程**:
  1. **研究设计**: 同时采集宿主和微生物样本，时间分辨率匹配生物事件（如疾病进展、治疗响应）
  2. **各组学独立预处理**: 转录组（标准化+特征选择）、代谢组（log 变换+降维）、微生物组（CLR 变换+稀疏过滤）、蛋白组（缩放+缺失值填补）
  3. **整合分析**: 降维（PCA/MOFA/MEFISTO）、潜在因子建模（DIABLO）、网络方法
  4. **预测建模**: 经典 ML（随机森林、SVM）或 DL（CNN、GNN），使用 SHAP/LIME 解释
  5. **可视化**: 热图、网络图、时间因子图
- **可提取积木**:
  - 积木名: MEFISTO 时空因子分析 | 输入: 多组学时间序列 | 输出: 时间相关的潜在因子、各因子的时间趋势、方差分解 | 依赖: 各组学预处理
  - 积木名: 纵向 LMM 关联分析 | 输入: 多组学特征 + 时间 + 个体随机效应 | 输出: 时间趋势显著性、组学间动态关联 | 依赖: 数据预处理
  - 积木名: 时序网络（多层网络） | 输入: 多个时间点的网络 | 输出: 网络结构动态变化、关键时间窗口 | 依赖: 各时间点的网络推断

---

## 方向4：多组学网络推断

### 论文1: Sparse Inverse Covariance Estimation for Ecological Association Inference (SPIEC-EASI)

- **引用**: Kurtz ZD, Müller CL, Miraldi ER, Littman DR, Blaser MJ, Bonneau RA. *PLOS Computational Biology*, 2015, 11(5):e1004226. (被引 >4000次)
- **组学**: 16S rRNA / 宏基因组（微生物组成数据）
- **方法学摘要**: SPIEC-EASI 是微生物生态网络推断的金标准方法。核心创新：(1) 使用 Centered Log-Ratio (CLR) 变换处理组成性数据：z_ij = log(x_ij) - (1/p)Σ_k log(x_ik)，将组成数据转换到近似高斯空间；(2) 使用稀疏逆协方差估计（Graphical Lasso 或 Neighborhood Selection/MB）推断条件依赖网络，即两个类群在控制所有其他类群后的直接关联；(3) 使用 StARS（Stability Approach to Regularization Selection）自动选择稀疏化参数 λ，确保网络的稳定性。与 SparCC（边际相关）不同，SPIEC-EASI 推断的是条件依赖，边代表"直接"生态关联。MB 方法比 glasso 更快、更稀疏。
- **分析流程**:
  1. **数据过滤**: 去除低丰度/低频类群（如保留在 >10% 样本中出现的类群）
  2. **CLR 变换**: 对原始计数加伪计数后取 log，减去每样本的 log 几何均值
  3. **协方差估计**: 计算 CLR 变换后数据的样本协方差矩阵
  4. **正则化路径**: 在 λ 序列上拟合 glasso 或 MB 模型（默认 nlambda=100）
  5. **StARS 选参**: 通过子采样（默认 rep.num=20-30）评估各 λ 下的边稳定性，选择最稳定且最稀疏的模型
  6. **网络构建**: 非零精度矩阵元素对应网络边，构建稀疏邻接矩阵
  7. **下游分析**: 度分布分析、hub 类群识别、模块检测（如 fast greedy）
- **可提取积木**:
  - 积木名: SPIEC-EASI 条件依赖网络推断 | 输入: 微生物计数/丰度表 | 输出: 稀疏邻接矩阵（无向）、边的稳定性评分 | 依赖: 数据过滤、CLR 变换
  - 积木名: StARS 正则化参数选择 | 输入: 正则化路径结果 + 子采样重复数 | 输出: 最优 λ 值、稳定性评分 | 依赖: glasso/MB 正则化路径
  - 积木名: CLR 组成性数据变换 | 输入: 微生物计数矩阵 | 输出: CLR 变换矩阵 | 依赖: 伪计数添加

---

### 论文2: FlashWeave — Rapid Inference of Direct Interactions in Large-Scale Ecological Networks

- **引用**: Tackmann J, Matias Rodrigues JF, von Mering C. *Cell Systems*, 2019, 9(3):286-296.e8. (被引 >500次)
- **组学**: 16S / 宏基因组 + 可选元数据（环境因子、临床变量）
- **方法学摘要**: FlashWeave 是基于概率图模型的可扩展网络推断方法，采用 local-to-global 学习框架（约束式因果推断）。对每个目标变量 T（类群或元数据），通过一系列条件独立性测试迭代推断其直接关联变量集（Markov blanket），然后组合各局部邻域构建全局网络。关键特性：(1) 显式处理组成性效应和稀疏性中的结构零值，防止相似缺失模式类群之间的虚假边；(2) 可将元数据（环境因子）作为额外节点纳入网络，区分直接关联和由共享环境驱动的间接关联；(3) 在 Julia 中实现，可处理数十万样本规模的数据，速度远超 SPIEC-EASI；(4) 支持 sensitive 和 heterogeneous 模式，适应不同数据特性。
- **分析流程**:
  1. **数据预处理**: 去除罕见类群（如 <10% 样本出现），评估环境因子影响（如通过 PERMANOVA）
  2. **条件独立性测试序列**: 对每个目标变量 T，执行优化的统计测试序列，迭代移除间接边
  3. **局部邻域推断**: 得到每个 T 的 Markov blanket（直接关联变量集）
  4. **全局网络组合**: 若 A 在 B 的邻域中或 B 在 A 的邻域中，则在全局网络中创建 A-B 边
  5. **元数据整合**: 环境/临床变量作为普通节点参与推断，可识别与表型直接关联的类群
  6. **网络分析**: 模块检测（fast greedy）、hub 识别（Zi/Pi 统计量）、与随机网络比较
- **可提取积木**:
  - 积木名: FlashWeave 大规模网络推断 | 输入: 微生物丰度表 + 可选元数据 | 输出: 全局稀疏网络（无向）、元数据-类群关联 | 依赖: 数据过滤
  - 积木名: 元数据感知网络去混杂 | 输入: 微生物数据 + 环境/临床元数据 | 输出: 去除环境混杂后的纯微生物关联网络 | 依赖: FlashWeave 网络推断
  - 积木名: 网络模块与 Keystone 识别 | 输入: FlashWeave 网络 | 输出: 模块划分、Zi/Pi hub 评分、网络拓扑统计 | 依赖: FlashWeave 网络构建

---

## 缺失分析单元汇总表

| 缺失方法 | 方法类别 | 核心功能 | 与 Meta2bAnalyst 现有模块的对比 | 建议优先级 |
|---------|---------|---------|------------------------------|-----------|
| **MOFA+ / MEFISTO** | 无监督整合 | 多组学潜在因子分解，区分共享/私有变异 | 现有：Sparse CCA, RDA, O2PLS 均为两两整合；MOFA+ 支持 ≥2 组学同时整合，且自动处理缺失模态 | 🔴 高 |
| **RGCCA / SGCCA** | 多块关联 | 多块 CCA 推广，用户自定义块间关联结构 | 现有：Sparse CCA 仅支持两块；RGCCA 支持多块 + 设计矩阵 + 稀疏变量选择 | 🔴 高 |
| **DIABLO** | 有监督整合 | 多组学稀疏分类/特征选择，预测新样本 | 现有：跨组学 GBDT/LASSO 预测；DIABLO 提供内置的多块 sPLS-DA 框架和可视化 | 🟡 中 |
| **mmvec** | 微生物-代谢物整合 | 神经网络估计微生物-代谢物共现条件概率 | 现有：交叉相关（Spearman）；mmvec 处理组成性、捕捉非线性、输出概率解释 | 🔴 高 |
| **MIMOSA2** | 知识驱动整合 | 基于代谢网络模型推断微生物对代谢物的机制贡献 | 现有：无类似方法；MIMOSA2 提供机制假设生成功能 | 🟡 中 |
| **PALM / DBN** | 纵向时序 | 动态贝叶斯网络整合纵向多组学，推断时序关联 | 现有：无纵向分析模块；PALM 填补关键空白 | 🔴 高 |
| **MEFISTO** | 时空因子 | MOFA+ 的时空扩展，建模时间/空间连续协变量 | 现有：无；对纵向数据可替代静态 MOFA+ | 🟡 中 |
| **SPIEC-EASI** | 单组学网络 | 条件依赖网络（precision matrix），组成性安全 | 现有：SparCC 网络；SPIEC-EASI 推断条件依赖（非边际），更稀疏、更生态可解释 | 🟡 中 |
| **FlashWeave** | 单组学网络 | 大规模可扩展网络推断，支持元数据整合 | 现有：SparCC 网络；FlashWeave 速度快、可处理异质性数据、去环境混杂 | 🟡 中 |
| **NetCoMi** | 网络比较 | 多方法网络构建 + 组间网络统计比较 | 现有：SparCC 网络；NetCoMi 提供统一的网络构建和差异比较框架 | 🟢 低 |
| **LMM 纵向分析** | 纵向统计 | 线性混合模型分析多组学时间趋势 | 现有：无纵向模块；可作为纵向差异分析的基础 | 🟡 中 |
| **相似性网络融合 (SNF)** | 网络整合 | 融合多层相似性网络为共识网络 | 现有：无；可用于患者聚类和亚型发现 | 🟢 低 |
| **Joint NMF (iNMF)** | 矩阵分解 | 非负矩阵分解发现跨组学共享模式 | 现有：MOFA+ 可替代；但 iNMF 对计数数据更自然 | 🟢 低 |
| **gCoda / mLDM** | 单组学网络 | 基于对数正态分布的组成性网络推断 | 现有：SparCC；gCoda/mLDM 提供替代统计框架 | 🟢 低 |

---

## 参考文献

1. Argelaguet R, et al. (2020). MOFA+: a statistical framework for comprehensive integration of multi-modal single-cell data. *Genome Biology*, 21(1):111.
2. Argelaguet R, et al. (2018). Multi-omics factor analysis—a framework for unsupervised integration of multi-omics data sets. *Mol Syst Biol*, 14:e8124.
3. Tenenhaus A, Tenenhaus M. (2011). Regularized generalized canonical correlation analysis. *Psychometrika*, 76(2):257-284.
4. Singh A, et al. (2019). DIABLO: an integrative, multi-omics, multivariate method for multi-group classification. *Bioinformatics*, 35(17):3055-3062.
5. Morton JT, et al. (2019). Learning representations of microbe-metabolite interactions. *Nature Methods*, 16(12):1306-1314.
6. Noecker C, et al. (2022). MIMOSA2: a metabolic network-based tool for inferring mechanism-supported relationships in microbiome-metabolome data. *Bioinformatics*, 38(6):1615-1623.
7. Noecker C, et al. (2016). Metabolic model-based integration of microbiome taxonomic and metabolomic profiles elucidates mechanistic links between ecological and metabolic variation. *mSystems*, 1(1):e00013-15.
8. Ruiz-Perez D, et al. (2021). Dynamic Bayesian Networks for Integrating Multi-omics Time Series Microbiome Data. *mSystems*, 6(2):e01105-20.
9. Sherwani MK, et al. (2025). Multi-omics time-series analysis in microbiome research. *Frontiers in Bioinformatics*.
10. Kurtz ZD, et al. (2015). Sparse and Compositionally Robust Inference of Microbial Ecological Networks. *PLOS Computational Biology*, 11(5):e1004226.
11. Tackmann J, et al. (2019). Rapid Inference of Direct Interactions in Large-Scale Ecological Networks from Heterogeneous Microbial Sequencing Data. *Cell Systems*, 9(3):286-296.e8.
12. Jiang D, et al. (2019). Microbiome Multi-Omics Network Analysis: Statistical Considerations, Limitations, and Opportunities. *Frontiers in Genetics*, 10:995.
13. Duan D, et al. (2025). Advances in multi-omics integrated analysis methods based on the gut microbiome and their applications. *Frontiers in Microbiology*, 15:1509117.
14. Chetty A, et al. (2024). Multi-omic approaches for host-microbiome data integration. *Briefings in Bioinformatics*, 25(1):bbaad424.
15. Meng C, et al. (2014). A multivariate approach to the integration of multi-omics datasets. *BMC Bioinformatics*, 15:162.
16. Velten B, et al. (2022). Identifying temporal and spatial patterns of variation from multi-modal data using MEFISTO. *Nature Methods*, 19(12):1554-1562.
17. Rohart F, et al. (2017). mixOmics: An R package for 'omics feature selection and multiple data integration. *PLOS Computational Biology*, 13(11):e1005752.
18. Friedman J, Alm EJ. (2012). Inferring correlation networks from genomic survey data. *PLOS Computational Biology*, 8(9):e1002687.

---

> **报告生成时间**: 2026-08-20 07:13 HKT
> **搜索工具**: kimi_search_v2
> **总搜索轮次**: 7轮并行搜索，覆盖 4 个方向
