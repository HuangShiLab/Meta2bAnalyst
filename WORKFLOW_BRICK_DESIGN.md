# Meta2bAnalyst 积木式工作流架构改进方案

> **版本**: v1.0  
> **日期**: 2026-08-20  
> **基于**: 三份并行文献调研报告 + 42模块全量代码审计

---

## 一、执行摘要

Meta2bAnalyst 已具备 **Module Registry → Planner → Executor** 的积木式工作流基础架构，42 个分析模块全部完成 wiring。本次调研识别出 **4 个维度的覆盖缺口**，并基于 19 篇经典论文的方法学提取，设计了 **18 个新增分析积木** 和 **3 项架构增强**。

### 关键数字

| 指标 | 当前 | 目标（6个月后）|
|------|------|--------------|
| 分析模块数 | 42 | 60+ |
| 预处理层覆盖 | 1/5 | 4/5 |
| 统计检验覆盖 | 2.17/5 | 4/5 |
| 多组学整合覆盖 | 2.83/5 | 4/5 |
| 多部位分析覆盖 | 2.50/5 | 4/5 |
| 贝叶斯方法覆盖 | 0/5 | 2/5 |

### 设计原则

1. **显式预处理层**：标准化、校正、插补、检测作为独立积木，不再隐式内置
2. **实验设计感知**：Planner 根据配对/纵向/多批次等设计自动选择合适检验
3. **不确定性量化**：贝叶斯积木提供后验分布和可信度区间
4. **用户自定义组合**：支持拖拽式 DAG 编辑和自然语言描述的双向编辑

---

## 二、现有架构评估

### 2.1 架构优势（保持不变）

```
用户自然语言 → [Planner] → DAG (PlanStep[]) → [Executor]
                                      ↑
                              [Module Registry]
                              (ModuleSpec字典)
```

- **ModuleSpec 数据类**：name, description, category, input_requirements, parameters, output_spec, constraints, depends_on
- **模板 + 关键词双路由**：规则引擎离线可用，LLM 模式灵活扩展
- **DAG 执行**：拓扑排序 + 并行批处理 + SSE 流式事件
- **状态缓存**：step_id → result，支持断点续跑

### 2.2 四维度雷达图（当前 vs 目标）

```
                    当前              目标
预处理/质控          ████░░░░░░        ████████████
多组学整合           ██████████░░░░    ████████████████
多部位分析           ████████░░░░░░    ████████████████
高级统计检验         ██████░░░░░░░░    ██████████████
贝叶斯方法           ░░░░░░░░░░░░░░    ████████
网络推断             █████░░░░░░░░░    ████████████
纵向/时序            █████░░░░░░░░░    ██████████
```

---

## 三、新增分析积木设计

### 3.1 预处理层（5个新模块）

#### `normalization` — 统一标准化入口

```python
ModuleSpec(
    name="normalization",
    description="统一标准化入口，支持微生物组专用方法（TSS/CSS/CLR/ILR/TMM）和代谢组学方法（z-score/Pareto/Quantile）",
    category="preprocessing",
    input_requirements={"data": "required"},
    parameters={
        "data_type": {"type": "enum", "options": ["microbiome", "metabolome"]},
        "method": {"type": "enum", "options": {
            "microbiome": ["tss", "css", "clr", "ilr", "tmm", "rarefaction", "none"],
            "metabolome": ["zscore", "pareto", "quantile", "sum", "log1p", "none"]
        }},
        "reference_samples": {"type": "array", "default": None},
    },
    output_spec={"normalized_matrix": "dataframe", "scaling_factors": "array", "plot_data": "plotly"},
    constraints=["Must run before any analysis that requires standardized data"],
)
```

**关键设计决策**：
- 将现有分散在 7+ 模块中的标准化逻辑集中于此
- `microbiome_marker` 等模块的强制 CLR 重构为依赖此模块的输出
- 输出 `scaling_factors` 支持新样本的在线变换

#### `batch_correction` — 批次效应校正

```python
ModuleSpec(
    name="batch_correction",
    description="ComBat-seq/ComBat/MMUPHin 批次效应校正，保留生物学协变量",
    category="preprocessing",
    input_requirements={"data": "required", "metadata": "required"},
    parameters={
        "batch_column": {"type": "string", "required": True},
        "biological_covariates": {"type": "array", "default": []},
        "method": {"type": "enum", "options": ["combat_seq", "combat", "mmuphin", "harmony"], "default": "combat_seq"},
        "data_type": {"type": "enum", "options": ["microbiome", "metabolome"]},
    },
    output_spec={"corrected_matrix": "dataframe", "combat_params": "dict", "plot_data": "plotly"},
    constraints=["Requires metadata with batch_column"],
    depends_on=["normalization"],
)
```

#### `imputation` — 缺失值插补

```python
ModuleSpec(
    name="imputation",
    description="KNN/随机森林/QRILC/half-min 缺失值插补，支持 MNAR 和 MAR",
    category="preprocessing",
    input_requirements={"data": "required"},
    parameters={
        "method": {"type": "enum", "options": ["knn", "rf", "qrilc", "half_min", "min"], "default": "knn"},
        "missing_threshold": {"type": "float", "default": 0.5, "range": [0.1, 0.9]},
        "data_type": {"type": "enum", "options": ["microbiome", "metabolome"]},
    },
    output_spec={"imputed_matrix": "dataframe", "imputation_summary": "dict", "plot_data": "plotly"},
    constraints=["Features with missing rate > threshold are removed"],
)
```

#### `outlier_detection` — 离群值检测

```python
ModuleSpec(
    name="outlier_detection",
    description="Aitchison距离/马氏距离/孤立森林/Cook距离多策略离群检测",
    category="preprocessing",
    input_requirements={"data": "required", "metadata": "optional"},
    parameters={
        "method": {"type": "enum", "options": ["aitchison", "mahalanobis_pca", "isolation_forest", "cooks_distance"]},
        "group_column": {"type": "string", "default": None},
        "threshold": {"type": "float", "default": 0.05},
    },
    output_spec={"outlier_flags": "dataframe", "plot_data": "plotly", "report": "dict"},
)
```

#### `data_validator_v2` — 增强数据验证

```python
ModuleSpec(
    name="data_validator_v2",
    description="增强版数据验证：格式检查 + 维度 + 缺失 + 稀疏性 + 离群标记",
    category="preprocessing",
    input_requirements={"microbiome": "optional", "metabolome": "optional", "metadata": "optional"},
    parameters={
        "check_outliers": {"type": "bool", "default": True},
        "check_batch": {"type": "bool", "default": True},
        "sparse_threshold": {"type": "float", "default": 0.9},
    },
    output_spec={"report": "dict", "valid": "bool", "outlier_samples": "list", "batch_effects": "dict"},
    constraints=["Must run before any analysis module"],
)
```

---

### 3.2 高级统计检验（4个新模块）

#### `paired_differential_test` — 配对差异检验

```python
ModuleSpec(
    name="paired_differential_test",
    description="配对/自身前后对照设计的组成数据差异检验：paired Wilcoxon on CLR 或 paired ALDEx2",
    category="marker",
    input_requirements={"microbiome": "required", "metadata": "required"},
    parameters={
        "group_column": {"type": "string", "required": True},
        "subject_column": {"type": "string", "required": True},
        "method": {"type": "enum", "options": ["paired_wilcoxon", "paired_aldex2", "deseq2_paired"], "default": "paired_wilcoxon"},
        "transformation": {"type": "enum", "options": ["clr", "ilr"], "default": "clr"},
    },
    output_spec={"significant_features": "dataframe", "volcano_plot": "plotly", "statistics": "dict"},
    constraints=["Requires exactly 2 groups and subject_column for pairing"],
    depends_on=["normalization"],
)
```

#### `ancom_bc` — ANCOM-BC 协变量调整差异分析

```python
ModuleSpec(
    name="ancom_bc",
    description="ANCOM-BC: Bias-corrected differential abundance with covariate adjustment and multi-group support",
    category="marker",
    input_requirements={"microbiome": "required", "metadata": "required"},
    parameters={
        "group_column": {"type": "string", "required": True},
        "covariates": {"type": "array", "default": []},
        "random_effects": {"type": "string", "default": None},
        "pvalue_threshold": {"type": "float", "default": 0.05},
    },
    output_spec={"significant_features": "dataframe", "volcano_plot": "plotly", "sensitivity_plot": "plotly"},
    constraints=["Requires raw count matrix (not normalized)"],
    depends_on=["normalization"],
)
```

#### `mixed_effects_diversity` — 混合效应多样性分析

```python
ModuleSpec(
    name="mixed_effects_diversity",
    description="Linear Mixed Effects Models for alpha/beta diversity: lmer for alpha, adonis2-with-strata for beta",
    category="individual_omics",
    input_requirements={"microbiome": "required", "metadata": "required"},
    parameters={
        "diversity_type": {"type": "enum", "options": ["alpha", "beta"], "required": True},
        "alpha_metric": {"type": "enum", "options": ["shannon", "simpson", "richness", "observed"]},
        "beta_metric": {"type": "enum", "options": ["braycurtis", "unweighted_unifrac", "weighted_unifrac"]},
        "fixed_formula": {"type": "string", "default": "Group * Time + Age + BMI"},
        "random_formula": {"type": "string", "default": "(1|Subject)"},
        "subject_column": {"type": "string", "required": True},
    },
    output_spec={"model_summary": "dataframe", "random_effects": "dict", "icc": "float", "plot_data": "plotly"},
    constraints=["Requires longitudinal/repeated measures design with subject_column"],
)
```

#### `permanova_strata` — 分层 PERMANOVA

```python
ModuleSpec(
    name="permanova_strata",
    description="PERMANOVA with strata for paired/block designs (adonis2-style), supporting multiple covariates",
    category="individual_omics",
    input_requirements={"data": "required", "metadata": "required"},
    parameters={
        "group_column": {"type": "string", "required": True},
        "strata_column": {"type": "string", "default": None},
        "covariates": {"type": "array", "default": []},
        "distance_metric": {"type": "enum", "options": ["braycurtis", "euclidean", "unweighted_unifrac", "weighted_unifrac"]},
        "n_permutations": {"type": "int", "default": 999},
    },
    output_spec={"statistics": "dict", "significant_variables": "list", "plot_data": "plotly"},
    constraints=["strata_column enables paired/block design correction"],
)
```

---

### 3.3 多组学整合增强（4个新模块）

#### `rgcca` — 正则化广义典型相关分析

```python
ModuleSpec(
    name="rgcca",
    description="Regularized Generalized CCA for >2 omics blocks with user-defined design matrix and sparse variable selection",
    category="integration",
    input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "optional"},
    parameters={
        "blocks": {"type": "dict", "description": "{'microbiome': df1, 'metabolome': df2, ...}"},
        "design_matrix": {"type": "array", "default": None, "description": "C matrix: 1=associate, 0=independent"},
        "sparsity": {"type": "bool", "default": True},
        "n_components": {"type": "int", "default": 2, "range": [1, 10]},
    },
    output_spec={"components": "dict", "loadings": "dict", "plot_data": "plotly", "circos": "plotly"},
    constraints=["Requires >=2 omics blocks with aligned samples"],
    depends_on=["normalization"],
)
```

#### `mmvec` — 微生物-代谢物神经网络嵌入

```python
ModuleSpec(
    name="mmvec",
    description="Neural network estimation of microbe-metabolite conditional co-occurrence probabilities (compositionally safe)",
    category="integration",
    input_requirements={"microbiome": "required", "metabolome": "required"},
    parameters={
        "epochs": {"type": "int", "default": 1000},
        "latent_dim": {"type": "int", "default": 50},
        "learning_rate": {"type": "float", "default": 0.001},
    },
    output_spec={"conditional_prob_matrix": "dataframe", "embeddings_u": "dataframe", "embeddings_v": "dataframe", "biplot": "plotly"},
    constraints=["Requires aligned microbiome + metabolome samples"],
    depends_on=["normalization"],
)
```

#### `mefisto` — 时空因子分析

```python
ModuleSpec(
    name="mefisto",
    description="MEFISTO: Spatiotemporal extension of MOFA+ for longitudinal multi-omics with continuous covariates",
    category="integration",
    input_requirements={"microbiome": "required", "metabolome": "required", "metadata": "required"},
    parameters={
        "time_column": {"type": "string", "required": True},
        "subject_column": {"type": "string", "required": True},
        "n_factors": {"type": "int", "default": 5},
        "smoothness": {"type": "float", "default": 0.5},
    },
    output_spec={"factors": "dataframe", "time_trends": "plotly", "variance_explained": "dict"},
    constraints=["Requires longitudinal design with time_column and subject_column"],
    depends_on=["normalization"],
)
```

#### `bayesian_integration` — 贝叶斯多组学整合

```python
ModuleSpec(
    name="bayesian_integration",
    description="Bayesian hierarchical model for multi-omics integration with posterior uncertainty quantification",
    category="integration",
    input_requirements={"microbiome": "required", "metabolome": "required"},
    parameters={
        "n_factors": {"type": "int", "default": 5},
        "prior_network": {"type": "array", "default": None},
        "n_mcmc_samples": {"type": "int", "default": 1000},
    },
    output_spec={"posterior_factors": "dict", "factor_loadings": "dict", "hpd_intervals": "dataframe", "model_fit": "dict"},
    constraints=["Computationally intensive; n_mcmc_samples > 500 recommended"],
    depends_on=["normalization"],
)
```

---

### 3.4 网络推断升级（2个新模块）

#### `spiec_easi` — 条件独立网络推断

```python
ModuleSpec(
    name="spiec_easi",
    description="Sparse Inverse Covariance Estimation for Ecological Association Inference (CLR + glasso/MB + StARS)",
    category="individual_omics",
    input_requirements={"microbiome": "required"},
    parameters={
        "method": {"type": "enum", "options": ["glasso", "mb", "slr"], "default": "mb"},
        "lambda_min_ratio": {"type": "float", "default": 0.01},
        "nlambda": {"type": "int", "default": 100},
        "rep_num": {"type": "int", "default": 20},
    },
    output_spec={"adjacency_matrix": "dataframe", "network_data": "dict", "stability_scores": "array", "plot_data": "plotly"},
    constraints=["More robust than SparCC - infers conditional dependencies, not marginal correlations"],
    depends_on=["normalization"],
)
```

#### `flashweave` — 大规模元数据感知网络

```python
ModuleSpec(
    name="flashweave",
    description="FlashWeave: Local-to-global probabilistic graphical model for large-scale ecological networks with metadata de-confounding",
    category="individual_omics",
    input_requirements={"microbiome": "required", "metadata": "optional"},
    parameters={
        "sensitive": {"type": "bool", "default": False},
        "heterogeneous": {"type": "bool", "default": False},
        "metadata_columns": {"type": "array", "default": []},
    },
    output_spec={"network_data": "dict", "metadata_associations": "dataframe", "plot_data": "plotly"},
    constraints=["Julia implementation; requires FlashWeave.jl installation"],
    depends_on=["normalization"],
)
```

---

### 3.5 多部位分析增强（3个新模块）

#### `spatial_gradient` — 空间梯度分析

```python
ModuleSpec(
    name="spatial_gradient",
    description="Distance-decay curves, Mantel correlograms, and gradient forest for anatomical site gradients",
    category="integration",
    input_requirements={"microbiome": "required", "metadata": "required"},
    parameters={
        "site_column": {"type": "string", "required": True},
        "spatial_distance_matrix": {"type": "array", "default": None},
        "method": {"type": "enum", "options": ["distance_decay", "mantel_correlogram", "gradient_forest"]},
    },
    output_spec={"decay_plot": "plotly", "correlogram_plot": "plotly", "gradient_importance": "dataframe"},
    constraints=["Requires multi-site data with site_column or explicit distance matrix"],
)
```

#### `dmi` — 微生物个体化指数

```python
ModuleSpec(
    name="dmi",
    description="DMI (Degree of Microbial Individuality): Quantify per-taxon individual specificity from longitudinal paired distances",
    category="individual_omics",
    input_requirements={"microbiome": "required", "metadata": "required"},
    parameters={
        "subject_column": {"type": "string", "required": True},
        "time_column": {"type": "string", "default": None},
        "n_bootstrap": {"type": "int", "default": 20},
    },
    output_spec={"dmi_values": "dataframe", "bootstrap_ci": "dataframe", "plot_data": "plotly"},
    constraints=["Requires longitudinal data with repeated measures per subject"],
)
```

#### `icc_stability` — ICC 时间稳定性

```python
ModuleSpec(
    name="icc_stability",
    description="Intraclass Correlation Coefficient for microbiome temporal stability: decomposes variance into between-subject and within-subject components",
    category="individual_omics",
    input_requirements={"microbiome": "required", "metadata": "required"},
    parameters={
        "subject_column": {"type": "string", "required": True},
        "time_column": {"type": "string", "default": None},
        "transformation": {"type": "enum", "options": ["clr", "ilr", "log"], "default": "clr"},
    },
    output_spec={"icc_values": "dataframe", "stability_grade": "dict", "plot_data": "plotly"},
    constraints=["Requires >=2 timepoints per subject"],
    depends_on=["normalization"],
)
```

---

## 四、Planner 增强设计

### 4.1 实验设计感知规划

当前 Planner 仅通过关键词匹配选择模块。增强后，Planner 应：

1. **检测实验设计特征**：
   - 配对设计：metadata 中有 `subject_column` + 2-level `group_column`
   - 纵向设计：metadata 中有 `time_column` + `subject_column`
   - 多批次：`batch_column` 存在且 >1 个唯一值
   - 多部位：`site_column` 存在且 >1 个唯一值

2. **自动注入前置模块**：

```python
# 伪代码：Planner 实验设计感知逻辑
def _infer_experimental_design(metadata_df):
    design = {"paired": False, "longitudinal": False, "multibatch": False, "multisite": False}
    
    if "subject" in metadata_df.columns and metadata_df.groupby("subject").size().max() > 1:
        if "time" in metadata_df.columns:
            design["longitudinal"] = True
        elif metadata_df["group"].nunique() == 2:
            design["paired"] = True
    
    if "batch" in metadata_df.columns and metadata_df["batch"].nunique() > 1:
        design["multibatch"] = True
    
    if "site" in metadata_df.columns and metadata_df["site"].nunique() > 1:
        design["multisite"] = True
    
    return design

def _apply_design_best_practices(steps, design):
    # 多批次 → 注入 batch_correction
    if design["multibatch"] and not any(s["module"] == "batch_correction" for s in steps):
        steps.insert(1, {"module": "batch_correction", "id": "step1b_batch", "depends_on": ["step1_validate"]})
    
    # 配对设计 → 替换非配对 marker 为 paired_differential_test
    if design["paired"]:
        for i, s in enumerate(steps):
            if s["module"] in ("microbiome_marker", "aldex2"):
                steps[i] = {"module": "paired_differential_test", "id": s["id"], "depends_on": s.get("depends_on", [])}
    
    # 纵向设计 → 注入 mixed_effects_diversity，替换 MaAsLin3 为 LMM 框架
    if design["longitudinal"]:
        if not any(s["module"] == "mixed_effects_diversity" for s in steps):
            steps.append({"module": "mixed_effects_diversity", "id": f"step{len(steps)+1}_lmm", "depends_on": ["step1_validate"]})
    
    return steps
```

### 4.2 用户自定义积木组合接口

新增 `/agent/custom_plan` API，支持两种输入模式：

**模式A：拖拽式模块列表**
```json
{
  "modules": ["data_validator", "normalization", "batch_correction", "microbiome_pcoa", "permanova_strata", "ancom_bc"],
  "parameters": {
    "normalization": {"method": "clr"},
    "permanova_strata": {"strata_column": "subject"},
    "ancom_bc": {"covariates": ["age", "bmi"]}
  }
}
```

**模式B：自然语言描述**
```
"先验证数据，然后CLR标准化，
 批次校正后用分层PERMANOVA检验组效应（按subject配对），
 再用ANCOM-BC找差异菌（调整age和bmi）"
```

Planner 将模式B解析为模式A，然后自动推导依赖关系。

### 4.3 依赖关系自动推导

新增 `_auto_resolve_dependencies()` 函数：

```python
DEPENDENCY_RULES = {
    "batch_correction": ["normalization"],  # 先标准化再校正
    "microbiome_marker": ["normalization"],  # 显式依赖标准化输出
    "paired_differential_test": ["normalization"],
    "ancom_bc": ["normalization"],
    "spiec_easi": ["normalization"],
    "procrustes": ["microbiome_pcoa", "metabolome_pca"],
    "mefisto": ["normalization"],
    "spatial_gradient": ["normalization"],
}

CATEGORY_ORDER = ["preprocessing", "individual_omics", "integration", "marker", "visualization"]
```

---

## 五、模块注册表更新

### 5.1 新增 `preprocessing` 类别

当前类别分布：
```
preprocessing: 1 (data_validator)
individual_omics: 23
integration: 12
marker: 4
visualization: 1
```

目标分布：
```
preprocessing: 6 (validator, normalization, batch_correction, imputation, outlier_detection, data_validator_v2)
individual_omics: 26 (+ mixed_effects_diversity, dmi, icc_stability)
integration: 17 (+ rgcca, mmvec, mefisto, bayesian_integration, spatial_gradient)
marker: 6 (+ paired_differential_test, ancom_bc)
visualization: 1
network: 2 (+ spiec_easi, flashweave)
```

### 5.2 重构建议：标准化解耦

当前问题：`microbiome_marker` 强制 CLR、`metabolome_pca` 内置 zscore。

重构方案：
1. 移除各模块内置的标准化逻辑
2. 分析模块的 `input_requirements` 增加 `"normalized": "required"`
3. Planner 自动在分析模块前插入 `normalization`
4. 模块参数中保留 `transformation` 仅用于向后兼容的 override

---

## 六、实施路线图

### Phase 1：预处理层（Week 1-3）

| 模块 | 工作量 | 依赖 |
|------|--------|------|
| `normalization` | 简单 | Python自研 (numpy/scipy) |
| `outlier_detection` | 简单 | sklearn + scipy |
| `batch_correction` | 中等 | rpy2 + sva::ComBat/ComBat_seq |
| `imputation` | 中等 | sklearn.impute + rpy2 |

**交付物**：预处理层最小可用集合，端到端分析闭环打通。

### Phase 2：统计检验升级（Week 4-6）

| 模块 | 工作量 | 依赖 |
|------|--------|------|
| `paired_differential_test` | 中等 | scipy + rpy2 (ALDEx2) |
| `ancom_bc` | 中等 | rpy2 + ANCOMBC |
| `permanova_strata` | 简单 | rpy2 + vegan::adonis2 |
| `mixed_effects_diversity` | 复杂 | rpy2 + lme4/vegan |

**交付物**：支持配对、协变量调整、混合效应的完整统计检验框架。

### Phase 3：多组学整合增强（Week 7-10）

| 模块 | 工作量 | 依赖 |
|------|--------|------|
| `rgcca` | 中等 | rpy2 + RGCCA |
| `mmvec` | 复杂 | TensorFlow/PyTorch |
| `mefisto` | 复杂 | rpy2 + MOFA2/MEFISTO |
| `bayesian_integration` | 复杂 | numpyro/PyMC |

**交付物**：多块整合 + 时序整合 + 贝叶斯不确定性量化。

### Phase 4：网络与多部位（Week 11-14）

| 模块 | 工作量 | 依赖 |
|------|--------|------|
| `spiec_easi` | 复杂 | rpy2 + SpiecEasi |
| `spatial_gradient` | 中等 | Python自研 + rpy2 (gradientForest) |
| `dmi` | 简单 | Python自研 |
| `icc_stability` | 简单 | Python自研 |

**交付物**：条件独立网络 + 空间梯度 + 个体化/稳定性指标。

### Phase 5：Planner 增强（贯穿 Week 3-14）

- Week 3-4：实验设计感知逻辑
- Week 5-8：自定义组合接口 (/agent/custom_plan)
- Week 9-12：依赖关系自动推导
- Week 13-14：自然语言→积木 DAG 的端到端测试

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| R 依赖增加导致部署复杂度上升 | 高 | 封装统一 RService 中间层，Docker 镜像预装 R 包 |
| mmvec / MEFISTO 计算资源需求高 | 中 | 设置为可选模块，GPU 节点单独调度 |
| 贝叶斯积分 MCMC 收敛慢 | 中 | 默认 n_mcmc=500，提供收敛诊断（Rhat/Gelman）|
| 现有模块标准化逻辑重构引入回归 | 高 | 保留 backward compatibility，新逻辑通过 feature flag 切换 |

---

## 八、附录：完整模块全景图（目标态）

```
[预处理层]
  data_validator → normalization → [batch_correction] → [imputation] → [outlier_detection]

[单组学分析]
  microbiome: pcoa, nmds, alpha, tsne, umap, unifrac, rarefaction, taxonomy_bar
  metabolome: pca, alpha
  统计: permanova, permanova_strata, anosim
  网络: network_sparcc, spiec_easi, flashweave, wgcna
  功能: pathway_kegg, functional_prediction
  分型: enterotype, core_microbiome
  菌株: strain_analyzer
  稳定性: dmi, icc_stability

[标记发现]
  microbiome_marker, metabolome_marker, aldex2, songbird, maaslin3,
  paired_differential_test, ancom_bc, random_forest

[多组学整合]
  两两: procrustes, mantel_test, sparse_cca, rda, o2pls, cross_correlation
  多块: mofa, diablo, rgcca
  时序: mefisto
  贝叶斯: bayesian_integration
  代谢: mmvec, mimosa2
  预测: cross_omics_gbdt

[多部位分析]
  cross_site_permanova, cross_site_network, cross_site_concordance,
  source_tracking, spatial_gradient

[可视化/报告]
  report_generator, heatmap, volcano, upset
```

---

> **下一步行动**：请确认本方案优先级和范围，开始 Phase 1 开发。
