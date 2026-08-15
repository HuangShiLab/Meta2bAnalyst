# 阶段 0 + 阶段 1 修复报告

> 日期：2026-08-14
> 对应诊断：[`CODE_REVIEW_2026-08-14.md`](CODE_REVIEW_2026-08-14.md)
> 验证方式：`pytest`（266 passed）+ `tsc --noEmit`（0 error）+ `npm run build` + **真实数据端到端调用**

---

## 0. 验证结果对照

同一份 `Huang_mBio_microbiome.tsv`（261 samples × 44 genera，**样本在行**）+ `Huang_mBio_metadata.tsv`：

| 端点 | 修复前 | 修复后 |
|---|---|---|
| upload | `sample_count=44`，`sample_names=["Genus_0",...]` | `sample_count=261`，`sample_names=["S000",...]` |
| alpha-diversity | 201，261 samples | 201，261 samples |
| beta-diversity | 201，261×261 | 201，261×261 |
| **pcoa** | 201 "completed"，**44 个点（Genus_0…），group_metadata 为空** | 201，**261 点 / 261 已分组** |
| **nmds** | stress = 原始平方和（不可解读） | **stress-1 = 0.0041**（Kruskal） |
| **permanova** | **201 "completed"** + `{"error":"Need at least 2 groups"}` | 201，F=1.09 **R²=0.0250** p=0.2250 n=261 |
| **anosim** | 同上 | 201，**R=0.0184** p=0.0470 n=261 |
| **random-forest** | **500**（TypeError 崩溃） | 201，acc=0.127 folds=5 n=261 |
| heatmap | 201 | 201 |
| **rarefaction** | 单指标必崩；分组曲线全部相同 | 200，n_samples=261，各组曲线不同 |
| **taxonomy-bar** | **500**（把菌属当样本） | 200，n_samples=261 |
| core-microbiome | 200 | 200 |

统计量已对齐参考实现（`tests/test_statistics_reference.py`，36 项）：

| 量 | 修复前 | 修复后 | 参考 |
|---|---|---|---|
| ANOSIM R（完全分离两组） | **0.0046** | **1.0000000000** | scikit-bio，一致到 1e-12 |
| PERMANOVA pseudo-F | 130.633863（含 1e-10 偏置） | **130.6338648666** | scikit-bio，一致到 1e-9 |
| Chao1（F2=0 时） | **4.5×10¹⁰** | **7.0** | scikit-bio 偏差校正 Chao1 |
| ACE | 实为偏差校正 Chao1（名实不符） | 真 ACE；无定义时返回 NaN | scikit-bio |
| Jaccard（presence 相同的样本） | 0.825–1.0 | **0.0**；一半菌不同 → **0.5** | 定义 |
| Pielou（richness=1） | **inf** | **NaN** | scikit-bio |
| BH FDR | 手写、未做单调性修正 | 与 statsmodels 完全一致 | statsmodels |

---

## 1. 阶段 0

### 1.1 数据方向契约（原 §2.1）

新增 `backend/app/services/orientation.py`：

- `resolve_feature_table(df, metadata_df)` —— 用 metadata 的样本 ID 判定方向，返回统一的 **features × samples**；
  - 判定成功 → `confidence="determined"`；
  - 无 metadata → 按文档约定假设，并在 `warnings` 里明确说明"这是假设不是判定"；
  - **两轴都对不上 / 两轴同样匹配 → 抛 `OrientationError`（HTTP 400），不猜**。错误信息同时列出行标签、列标签和 metadata 样本 ID 的样例。
- `assert_sample_alignment(df, metadata_df, group_column)` —— 校验交集样本数、分组列存在性、分组数 ≥ 2。

接入点：`analysis.py` 的 `_orient()` 包住 `get_dataframe` / `get_dataframe_by_type` / `get_dataframe_by_name`，**所有端点自动生效，无需改 40 个调用点**；`upload.py` 的 `_describe_upload()` 在入库前解析方向。

同时**删除了各服务里所有自行猜测的启发式**：
- `analysis_engine.run_alpha_diversity` 的 `^[Ss]\d+$` 正则（删除）
- `analysis_engine.run_beta_diversity` 的另一套启发式（删除）
- `taxonomy_bar.py` 两处 `if '|' in first_idx or '__' in first_idx: df = df.T`（改为按契约无条件转置）
- `rarefaction` 调用点补上 `.T`（该服务按样本行工作）

回归测试：`tests/test_orientation_contract.py`（16 项），含 **"两种方向输入必须得到完全相同结果"** 和 **"PCoA 不得把 Genus_* 当样本"**。

### 1.2 删除伪造内容（原 §2.2）

`agent_engine.py` `PaperWriter`：

- Methods 段的 12 个实验事实默认值（DADA2 / SILVA 138 / MiSeq / V3-V4 / 2×250bp / Cutadapt / MAFFT+FastTree / QIIME2 v2024.2 / −80 °C …）→ 全部改为 `[BRACKETED]` 占位符；
- **伦理声明不再自动生成**，未提供时输出 `[ETHICS APPROVAL — 填写审批委员会与编号，或删除本节]`；
- 正文顶部加固定 NOTE：本稿由机器生成、括号字段需作者填写、其余需核对；
- Results 段措辞改为**由 p 值驱动**——`p ≥ 0.05` 输出 "did not differ significantly"（此前只要结果对象存在就写 "revealed a significant difference"）；
- 无条件的 "Rarefaction curves indicated adequate sequencing depth (Figure S1)" → 仅在真的跑过稀疏曲线时输出；
- `PaperSection` 新增 `ai_generated` / `requires_author_verification` / `unfilled_placeholders`；
- `_significance_badge`：`p=None` 由 "not significant" 改为 "not reported"；`p<0.05` 由 "marginally significant" 改为 "significant"。

验证：不提供任何字段时，全文中 DADA2 / SILVA / MiSeq / V3-V4 / Cutadapt / MAFFT / FastTree / QIIME 2 / 伦理声明 / −80 均已消失，12 个占位符正确列出。

### 1.3 崩溃与静默错误（原 §2.4、§3.1）

| 位置 | 修复 |
|---|---|
| `main.py:63` | `jsonable_encoder(exc.errors())` —— **所有校验错误从"空 body 的 500"变回可读 422** |
| `analysis_engine.py` ANOSIM | 分母改为 `n(n-1)/4`（n = 样本数） |
| `analysis_engine.py` Chao1 | 改为偏差校正式 `S_obs + F1(F1-1)/(2(F2+1))` |
| `analysis_engine.py` ACE | 实现真正的 ACE（含 coverage 与 γ²） |
| `analysis_engine.py` Jaccard | `pdist` 前二值化 |
| `analysis_engine.py` Pielou | richness ≤ 1 → NaN |
| `analysis_engine.py` RF | `confusion_matrix` 用编码后的整数标签；CV 折数由**最小类样本数**决定；样本不对齐时抛错 |
| `analysis_engine.py` PERMANOVA/ANOSIM | 加 `random_seed`（默认 42，**p 值可复现**）；PERMANOVA 返回 **R²**；去掉 F 统计量分母的 1e-10 偏置 |
| `analysis_engine.py` NMDS | 报告 **Kruskal stress-1**，同时保留 `raw_stress` |
| `analysis_engine.py:1437` | lefse 分支 `engine` 未定义（NameError） |
| `r_analysis.py` ANCOM-BC 回退 | `padj` 未定义（NameError）；显著性判定改用**校正后**的 p |
| `rarefaction.py` | 单指标时 `go.Figure()` + `row/col` 必崩 → 统一用 `make_subplots`；**分组曲线此前全部相同**（按样本重新聚合）；8 位 hex `fillcolor` 改 `rgba()` |
| `analysis.py` volcano | `padj → pvalue` 重命名在 DESeq2 结果上产生重复列名并崩溃 → 改为显式列映射 |
| `analysis.py` `_submit_async_task` | `session_id` 位置参数与关键字参数冲突（**该异步路径此前从未被执行过**） |
| `planner.py:422` | `"moafa"` 拼写错误 + `"mofa\+"` 非法转义 |

新增全局 `_jsonify()`：numpy / pandas 标量与数组、NaN/Inf 在落库和响应前统一转换（此前 RF 结果直接 500）。

### 1.4 下线未验证方法（原 §2.3）

新增 `_guard_unvalidated()`：**UniFrac/Faith PD** 与 **PICRUSt2/Tax4Fun** 默认返回 400，错误信息直接点明原因（模拟系统发育树 / 源码内 mock KO 库）与文件位置，并声明"结果不得以该方法名报告"。需显式传 `acknowledge_unvalidated: true` 才运行，且结果带 `engine: "unvalidated::..."`。

### 1.5 依赖与部署（原 §3.7）

- `requirements.txt` 补齐并分组注释：`networkx`、`PyYAML`、`statsmodels`、`scikit-bio`、`pyarrow`、`reportlab`、`kaleido`（此前 `networkx` 和 `yaml` 是 `app.main` 可达的模块级导入，**容器必然启动失败**）；
- `rpy2` 从硬依赖改为**可选**（需要可用的 R 环境；缺失时相关方法拒绝执行而不是静默近似），连同 `umap-learn` / `scikit-learn-extra` / `openai` 一起作为注释中的可选项列出；
- **全新环境安装已验证通过**：`python -m venv` + `pip install -r requirements.txt`（80 个包，无需 rpy2/R）→ `import app.main` 成功，`GET /api/v1/sessions` 返回 200。详见下节。
  > `docker compose build` 本身未执行（本机网络约 20 kB/s），但等价的干净环境安装+启动+端到端已完成。
- `docker-compose.yml` **新增 celery worker 服务**（此前完全没有，任务投递后无人消费）；
- `backend.Dockerfile` 注明 R 未安装及启用方式。

---

## 2. 阶段 1

### 2.1 参考实现替换 + 黄金值测试（原 §4.7）

- 新增 `adjust_pvalues()` 统一走 `statsmodels.multipletests`，**替换了全仓库 8 处**手写 BH（`analysis_engine` ×3、`r_analysis` ×3、`functional_analysis`、`advanced_dimred`、`functional_prediction`、`strain_analyzer`、`correlation_analysis`）。其中 `correlation_analysis._bh_fdr` 的单调性修正作用在未排序数组上，结果依赖输入行序。
- 新增 `tests/test_statistics_reference.py`（36 项）：Shannon / Chao1 / ACE / Pielou / ANOSIM / PERMANOVA 全部 `assert_approx` 对齐 scikit-bio；BH 对齐 statsmodels；含"排列检验可复现""行序无关""转置输入必须报错"等契约测试。
- 新增 `tests/test_orientation_contract.py`（16 项）。

原有 3 个测试断言的是**错误行为**，已按新契约更新：
- `test_permanova_single_group` / `test_anosim_single_group`：原本断言返回 `{'error':...}`，改为断言抛错；
- `test_analysis_invalid_type`：原 docstring 直接写明"validation handler 有 JSON 序列化 bug"并断言抛异常 → 改为断言 422 且 body 可读；
- `test_taxonomy_bar_analysis`：原本接受 `404, 500` 作为通过 → 改为断言 200 且样本数正确。

### 2.2 方法执行凭证（原 §2.3）

`r_analysis.engine_for(method, allow_approximation)`：

- R 包可用 → `{"engine": "R::DESeq2", "is_approximation": false}`；
- R 包缺失且**未显式授权** → 抛 `ApproximationRefused` → HTTP 400，信息包含：缺哪个 R 包、**Python 替代品实际算的是什么**（如"DESeq2 回退 = Welch t 检验，没有负二项模型/离散度收缩/size factor"）、以及"结果不得以 DESeq2 报告"；
- 显式传 `allow_approximation: true` → 运行，结果带 `engine: "python-approx::ancombc"`、`is_approximation: true`、`approximation_note`、`reporting_guidance`。

覆盖 deseq2 / edger / ancombc / maaslin3 / aldex2 / lefse / wgcna / diablo。同时**移除了 `len(groups)==2` 的隐式门控**——此前选 DESeq2 但分组数不是 2 时会静默落到通用 Wilcoxon 分支并仍标注为 DESeq2。

实测：DESeq2 → `engine=R::DESeq2, is_approximation=False`；ANCOM-BC → 400 并给出安装指引；加 `allow_approximation:true` → 200 且标注 `python-approx::ancombc`。

### 2.3 前端接真实 session（原 §3.5）

- 新增 `useRequiredSession()`；`Microbiome / AnalysisSpecies / AnalysisStrain / MultiSite / Results` 五个页面的 `"mock-session"` 全部替换（含 `x ? "mock-session" : "mock-session"` 这种恒等三元）；
- `useAnalysis.runAnalysis` 与 `useSectionAnalysis.run` 增加**统一拦截**：session 为空时抛出可读错误，不再请求 `/sessions//analyze/...`；
- 新增 `NoSessionBanner`，未上传数据时页面顶部明确提示并链接到上传页；
- 新增后端 `GET /sessions/{id}/metadata/columns` + 前端 `useMetadataColumns()`，**分组变量从上传的 metadata 动态获取**，替换硬编码的 `["Visit","Treatment","Group","Site","Timepoint","Gender","Age"]`。实测返回 `Visit(7 levels) / Plaque(2) / Bleeding(连续) / Subject(24)`。

### 2.4 错误语义统一（原 §3.3）

- `_save_result()` 检测到 `{'error': ...}` → 置 `job.status='failed'`、写 `error_message`、抛 **HTTP 400**；一处修改覆盖全部 37 个调用点；
- 为 22 个路由补上 `except HTTPException: raise` 直通分支，避免故意抛出的 4xx 被通用 `except Exception` 吞成 500。

### 2.5 差异分析可指定对比组（原 §2.4 末行）

- 新增 `resolve_comparison_groups()`，`AnalysisRequest` 新增 `comparisons` / `reference_group`；
- 分组数 > 2 且未指定时**返回 400 并列出所有可选分组和示例请求体**，不再静默取前两个；
- 两组时按**字典序**取（不再依赖 metadata 行序，fold-change 方向稳定）；
- 结果新增 `reference_group` 与 `fold_change_direction`（如 `"T9 vs T4"`）。

实测：7 个 Visit 未指定 → 400 + `Set comparisons to ... e.g. ["T1","T4"]`；指定 `["T4","T9"]` + `reference_group:"T4"` → 201，`T9 vs T4`，3/44 显著。

### 2.6 顺带修复

- `analysis_type` 改为**可选**（路径已唯一确定分析类型）。此前它必填且命名规则与路由不同（`/analyze/random-forest` 却要求 `"random_forest"`），叠加 1.3 的 handler 崩溃，导致最直观的请求返回不可诊断的 500；
- 分块上传路径穿越：`file_type` 与 `original_filename` 均经 `Path(...).name` + `sanitize_filename()`；
- `_save_result` 改用 `settings.UPLOAD_DIR`（此前硬编码 `./uploads`，容器里配置的是 `/app/uploads`）；
- `_workers_available()`：投递 Celery 前**探测活跃 worker**，无 worker 则同步执行，不再把任务投进永远无人消费的队列；
- 删除 `DataParser.parse_metaphlan` / `parse_humann3` 的重复定义（各定义两次，前一份是死代码）；
- 清理 `analysis.py` / `analysis_engine.py` 的重复 import。

---

## 2.7 现代依赖栈验证（追加）

`requirements.txt` 用的是 `>=` 下限，因此全新安装解析出的版本与开发 venv 差距很大：

| | 开发 venv | 全新安装 |
|---|---|---|
| Python | 3.9 | **3.12.4** |
| pandas / numpy | 2.3.3 / 2.0.2 | **3.0.5 / 2.5.2** |
| scipy / scikit-learn | 1.13 / 1.6.1 | **1.18 / 1.9.0** |
| plotly / fastapi / starlette | 5.x / 旧 / 旧 | **6.9 / 0.141 / 1.6** |

本次全部结论此前**只在旧栈上测过**。在新栈上重跑后发现并修复了 2 个问题：

**① `taxonomy_bar.py:79` `groupby(axis=1)` —— pandas 3.0 已移除**（真实应用 bug）
`DataFrame.groupby() got an unexpected keyword argument 'axis'` → taxonomy-bar 端点在任何全新安装上直接 500。改为 `rel_abund.T.groupby(grouping).sum().T`，pandas 2/3 均可用。

**② NMDS stress 依赖 sklearn 内部语义 —— 跨环境数值不一致**（真实科学 bug）
`sklearn.manifold.MDS.stress_` 的含义在 1.6 与 1.9 之间变了（原始平方和 → 已归一化），而代码用 `sqrt(stress_/Σd²)` 二次归一化。同一份数据：

| | sklearn 1.6.1 | sklearn 1.9.0 |
|---|---|---|
| 修复前上报 | 0.0871 | 0.0080 |
| 该嵌入真实 stress-1 | **0.3928** | **0.0023** |

即两个环境都报错了，且错法不同——旧栈把"较差的排序（0.39，按 Kruskal 判读属于可疑）"报成"0.087（良好）"。现改为**直接从返回的坐标用保序回归重算 stress-1**，不再依赖 `mds.stress_`。新增回归测试 `test_nmds_stress_describes_the_returned_embedding` 断言上报值可由坐标复现。

> ⚠️ 需要知道：**NMDS 的嵌入结果本身是 sklearn 版本相关的**——1.9 的优化器在同一输入上找到明显更优的解（stress-1 0.0023 vs 0.39）。这不是本仓库能修的，上报的 stress 现在会如实反映你实际得到的那个嵌入。若需跨环境可比的 NMDS 图，应把 `scikit-learn` 钉到固定版本。

**其余全部一致。** 固定种子下逐项比对两个环境（20 组量、含 4 个完整 30×30 距离矩阵）：

| 量 | 差异 |
|---|---|
| Shannon / Simpson / Chao1 / ACE / observed / Pielou | 0 |
| Bray-Curtis / Jaccard / Euclidean / Manhattan 距离矩阵 | 0 |
| PCoA 特征值与解释方差 | 0 |
| PERMANOVA pseudo-F / R² / p / SSB / SSW / SST | 0 |
| ANOSIM R / p / 组内外平均秩 | 0 |
| BH FDR、t 检验与 Wilcoxon 的 padj | 0 |
| Random Forest 准确率 / CV / 混淆矩阵 | 0 |
| **NMDS stress**（修复前） | **唯一不一致项，已修** |

新栈端到端复跑（真实 Huang 数据）：上传方向 261×44 正确、11 个端点全部 2xx 且均为 261 样本、7 组时差异分析 400 并列出分组、显式对比组 201、UniFrac 400、校验错误 422 可读。两栈测试均为 **267 passed**。

**另注**：`len(app.routes)` 在 FastAPI 0.141 上从 89 降到 14，是因为 `include_router` 改为存放惰性 `_IncludedRouter` 而非展平子路由；请求路由正常，不是问题。

---

## 2.8 全流程排查（追加）

新增 `backend/scripts/pipeline_smoke.py`：对着真实运行的服务器、用真实数据跑通**每一条分析流水线**，逐条断言 HTTP 状态与样本数，退出码等于失败条数（可直接接 CI）。

```bash
python scripts/pipeline_smoke.py --base http://127.0.0.1:8000
```

首次运行：**63 条里 47 条通过、16 条失败**。这些失败此前全部没被任何测试覆盖过。修复如下。

### 方向契约的漏网之鱼（7 条）

阶段 0 只改了当时测过的端点。全量排查发现另外 5 个服务同样按**样本行**工作，却拿到了规范的 features × samples：

| 服务 | 症状 | 修复 |
|---|---|---|
| `songbird` | 500 `No matching sample IDs` | 调用点 `.T` |
| `mofa` | 500 `No common samples between microbiome and metabolome` | 调用点 `.T`（两个组学都要） |
| `enterotype` | 500 `index 0 is out of bounds` | 调用点 `.T` |
| `multisite-*`（5 个端点） | 500 `No matching samples` / `IDs must be at least 1 in size` | `multisite.py` 载入处统一 `.T` |
| `aldex2` | 被近似守卫挡住，从未真正执行过；实际方向也是反的 | 调用点 `.T` |

并加了 `tests/test_orientation_contract.py::TestServiceOrientationContracts` 把每个服务被调用的方向钉死。

> **WGCNA 是最危险的一个**：它两种方向都不报错，但算出来的东西不同——features × samples 得到 44 个基因模块（正确），转置后得到 261 个"样本模块"（无意义）。当前调用方向是对的，已用测试锁定，避免以后重构时被静默改掉。

### 退化距离矩阵导致的 500（2 处）

Jaccard 作用在"每个样本都含全部菌属"的稠密表上 → 所有距离为 0 → PCoA 没有正特征值：

- `analysis_engine.pcoa` 返回 0 列坐标，下游 `plotly_pcoa_scatter` 抛 `KeyError('PC1')`；
- `enterotype._pcoa` 同样返回空数组，调用方 `pcoa_coords[:, 0]` 抛 `IndexError`。

现在两者都至少返回 PC1/PC2（零填充）并带 `degenerate: true` + 说明性 warning；`run_enterotype` 直接给出可操作的报错（"改用 braycurtis"）。正常数据结果不变（已加回归测试）。

### ANCOM-BC 无法用于多分组数据

`len(groups) != 2` 是对**整列**取值判断的，所以 7 个时间点的研究即使显式指定 `comparisons: ["T4","T9"]` 也被拒。改为先解析对比组、再把数据裁到这两组。

### 近似守卫对类型化请求模型不可见

`ALDEx2Request` / `WGCNARequest` / `DIABLORequest` 没有 `parameters` 字段，而 `_guard_approximation` 从那里读 `allow_approximation` —— 于是这三个端点**无论如何都无法опt-in**，永远 400。已在这三个模型上加 `allow_approximation: bool = False`。

### 其他

- **删除 session 现在真的删文件**（`sessions.py` 里那句 `# TODO: Delete uploaded files from disk`）。此前磁盘 230 个目录 vs 数据库 65 个 session。
- **知识库三个 bug**：
  - `sqlite3.connect(":memory:")` 改 `check_same_thread=False` + `RLock`（实测工作线程调用会抛 `ProgrammingError`）；
  - 物种名匹配方向反了（`KB.name LIKE '%query%'`）。新增 `normalize_taxon_name()`，现在 `s__X` / `X Y`（空格）/ 全谱系 / 属名 全部命中；
  - `_row_to_taxon` 从不返回 `disease_associations`（存在另一张表且从未 join），使得 `interpretation_engine` 里的疾病注释分支是**死代码**。已 join 回来。
  - 仍未解决：知识库内容全是肠道方向，`Streptococcus_mutans` / `Porphyromonas_gingivalis` 等口腔菌不在库中（内容缺口，非代码缺陷）。

---

## 3. 未做（属阶段 2/3，按原路线图）

1. **Agent 层空壳**：`data_validator` 仍是 `lambda: {"valid": True}`，`report_generator` 仍返回硬编码 `/tmp/report.pdf`；`/agent/analyze` 的 DataFrame 真值判断错误未修；SSE 仍是批次屏障而非真流式。
2. **Agent 关键字表与模块注册表脱节**：本次加了防护（未注册模块会被跳过并告警，不再产出无法执行的计划），但 `MODULE_KEYWORDS` 里 **16 个键在 `MODULE_REGISTRY` 中不存在**（`mofa`/`diablo`/`wgcna`/`aldex2`/`songbird`/`enterotype`/`rarefaction`/`taxonomy_bar`/`heatmap`/`volcano`/`anosim`/`random_forest`/`unifrac`/`upset`/`source_tracking`/`strain_analyzer`）——注册表只有 22 个模块，需要补齐。
3. **认证 / 授权 / 限流**：仍然完全没有。对外发布前必须解决。
4. **删除 session 不清磁盘**；每请求重复解析文件；beta-diversity 仍返回完整 O(n²) 距离矩阵（261 样本 ≈ 1.76 MB）。
5. **知识库**：线程不安全（`check_same_thread=True`）、`s__`/空格/全谱系命名匹配失败、`disease_associations` 分支是死代码、内容全为肠道方向。
6. **2bRAD 原生能力**：仍然没有。

---

## 4. 复现

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -q
```

```bash
cd frontend && npx tsc --noEmit -p tsconfig.app.json && npm run build
```
