# Meta2bAnalyst 深度代码审查报告

> 审查日期：2026-08-14
> 审查范围：`backend/` (~33k 行 Python) + `frontend/src` (~12k 行 TS) + 部署配置 + 需求文档（poster / PROJECT_CONTEXT / GAP_ANALYSIS）
> 审查方式：静态阅读 + **实际启动后端、上传 Huang mBio 真实数据、逐个调用 API 复现**

---

> ## ⚠️ 本报告描述的是修复前的状态
>
> **阶段 0 与阶段 1 已于 2026-08-14 完成**，详见 [`FIXES_APPLIED_2026-08-14.md`](FIXES_APPLIED_2026-08-14.md)。
> 下文保留原始诊断作为记录；每一项的当前状态见修复报告。
> 阶段 2、3 仍未开始。

---

## 0. 一句话结论

**当前版本不能用于产出可发表的科学结果。** 问题不在"功能少"，而在三个层面同时失守：

1. **科学正确性**：多个统计量算错（实测 ANOSIM R 偏差 200 倍、Chao1 溢出到 4.5×10¹⁰）；多个"知名方法"（UniFrac / PICRUSt2 / DESeq2 / LEfSe / ANCOM-BC / MaAsLin3 / ALDEx2 / WGCNA / DIABLO）实际是近似或**伪造**实现，但 API 返回值仍然标注为原方法名。
2. **数据契约**：全系统没有统一的"行是样本还是特征"约定，每个函数各自用正则猜。**实测同一个 session 里 alpha 多样性算的是 261 个样本、PCoA 算的是 44 个属**——两张图并排展示，互相矛盾，且无任何报错。
3. **交付完整度**：前端 5 个主分析页面（约 4400 行）`sessionId` 硬编码为 `"mock-session"`，与上传流程完全断开；Agent 的 `data_validator` 和 `report_generator` 是空壳 lambda；`docker compose up` 因 requirements.txt 缺依赖而无法启动。

GAP_ANALYSIS.md 把重点放在"再补 19 个模块"，方向不对。**现有 22 个模块里能给出可信数字的不到一半**，继续叠加模块只会放大问题。

---

## 1. 复现记录（这些不是推测，是实测结果）

启动后端 → 创建 session → 上传 `Huang_mBio_microbiome.tsv` + `Huang_mBio_metadata.tsv` → 调用各分析端点：

| 端点 | 结果 |
|---|---|
| `POST /analyze/alpha-diversity` `{"analysis_type":"alpha"}` | 201，261 行（S000…）✅ |
| `POST /analyze/beta-diversity` `{"analysis_type":"beta"}` | 201，261 样本，**响应体 1.76 MB** |
| `POST /analyze/pcoa` | 201 "completed"，**只有 44 个点，标签是 `Genus_0…Genus_43`**，PC1=4.67% PC2=4.45%，`group_metadata` 为空 ❌ |
| `POST /analyze/permanova` | **201 "completed"**，`result_data = {"error": "Need at least 2 groups"}` ❌ |
| `POST /analyze/anosim` | 同上 ❌ |
| `POST /analyze/random-forest` | **500 Internal Server Error（空响应体）** ❌ |
| `POST /agent/plan` `{"query":"Find differential markers comparing visits"}` | 200，但只规划出 1 步 `data_validator`（空操作），`notes: ["Keyword-based planning detected: []"]` ❌ |
| `POST /agent/analyze` | **500** `The truth value of a DataFrame is ambiguous` ❌ |

上传时后端记录的元信息本身就是错的：

```json
{"sample_count": 44, "feature_count": 261,
 "sample_names": ["Genus_0","Genus_1","Genus_2", ...]}
```

——把 44 个菌属当成了 44 个样本存进数据库。而同一 session 的 metadata 文件明明写着样本是 `S000…S260`，系统没有做任何交叉校验。

后端测试：`212 passed, 1 failed`（失败的正是 Random Forest）。**212 个绿灯掩盖了上面全部问题**，原因见 §4.7。

---

## 2. P0 — 科学正确性缺陷（会产出错误结论）

### 2.1 【最高优先级】数据方向没有统一契约，各函数自行猜测

- `data_parser.parse_csv_tsv()` 无条件假设 **行=特征、列=样本**（`backend/app/services/data_parser.py:153`）
- `upload.py:363` 据此把第一行当样本名写进 DB
- `analysis_engine.run_alpha_diversity()` 用正则 `^[Ss]\d+$` 猜方向并转置（`analysis_engine.py:1178-1186`）
- `run_beta_diversity()` 用**另一套更弱的**启发式（`analysis_engine.py:1272-1276`）
- `run_pcoa()` / `permanova` / `anosim` / `random_forest` **完全没有**启发式

后果（已实测）：alpha 和 beta 转置了，PCoA 和 PERMANOVA 没转置。**同一份数据在同一个界面上得到互不相容的结果，且全部返回 HTTP 201 "completed"。**

启发式本身也脆弱：`^[Ss]\d+$` 匹配不了 `SRR1234567`、`Sample_01`、`P1-T4`；`first_col[0].isupper()` 在空列名时会 IndexError。

**修复方向**：把方向作为**数据契约**在入口一次性确定，而不是在 20 个分析函数里各猜一次。
1. 上传时用 metadata 的样本 ID 做交叉验证确定方向（这份数据里 100% 可判定）；
2. 判定不了就返回 400 让用户明确指定，**不要猜**；
3. 内部统一存成一种方向（建议 samples × features，与 pandas / sklearn 生态一致），落盘为 parquet；
4. 删除所有分析函数里的转置启发式；
5. 加一个 `assert_orientation()` 前置断言，任何函数拿到的 DataFrame 必须与 metadata 索引有交集，否则抛 400 而不是算出 44 个点。

### 2.2 【科研诚信风险】PaperWriter 编造实验方法与伦理声明

`backend/app/services/agent_engine.py:1098-1137` 的 Methods 段落，在用户未提供时直接填入**具体的、平台不可能知道的实验事实**：

- "Samples with fewer than 10,000 reads were excluded. Adapters and low-quality bases were trimmed using **Cutadapt**."
- "Taxonomic assignment was performed using the **DADA2** pipeline against the **SILVA 138** reference database."
- "The **V3-V4** hypervariable region ... sequenced on the **Illumina MiSeq** platform using paired-end **2 × 250 bp** chemistry."
- "A phylogenetic tree was constructed with **MAFFT and FastTree**."
- "All analyses were conducted in **QIIME 2 (v2024.2) and R (v4.3)** with phyloseq and vegan."
- "Samples were immediately frozen at **−80 °C**."
- **"This study was approved by the institutional ethics committee."**

对 2bRAD-M 用户，以上每一条都是错的（2bRAD 不是 16S 扩增子，没有 V3-V4，不用 DADA2/SILVA）。**自动生成一句伪造的伦理审批声明，是任何期刊都会视为学术不端的内容。**

Results 段同样有问题（`agent_engine.py:1139-1187`）：
- 无条件写 "Rarefaction curves indicated adequate sequencing depth (Figure S1)"，即使根本没跑稀疏曲线；
- `if alpha_result:` 为真就写 "revealed a **significant** difference"，**完全不看 p 值**——p=0.8 也会写成"显著"；
- beta 段 `R² = {r2:.3f}`，而本仓库的 PERMANOVA 根本不返回 `r2` 字段 → `None:.3f` 直接 TypeError。

**修复方向**：所有 Methods 事实字段改为**必填或留空占位符**（`[SEQUENCING PLATFORM]`），绝不给默认值；伦理声明整段删除；显著性措辞必须由 p 值驱动；生成物加显著水印"AI-drafted, requires author verification"。

### 2.3 【虚假标注】方法名与实际实现不符，且响应里不告知

`analysis.py:743` 无条件写死 `'test_method': 'DESeq2'`，即使实际跑的是 Python 回退：

```python
# r_analysis.py:64  _python_deseq2_fallback
"""Python fallback: log2 fold-change + t-test as a DESeq2-like approximation."""
```

**DESeq2 回退 = Welch t 检验；edgeR 回退 = 同一份 Welch t 检验代码**，只是列名改成 `logFC/logCPM/PValue/FDR`。用户在 UI 里选 "DESeq2"，拿到的是 t 检验，响应里写着 "DESeq2"，日志里只有一行 warning。

本机实测 R 包安装情况：

| R 包 | 已安装 | 实际执行 |
|---|---|---|
| DESeq2 / edgeR / vegan / phyloseq | ✅ | R |
| **ANCOMBC** | ❌ | Python 近似 |
| **MaAsLin3 / Maaslin2** | ❌ | Python 近似 |
| **mixOmics (DIABLO)** | ❌ | Python 近似 |
| **WGCNA** | ❌ | Python 近似 |
| **ALDEx2** | ❌ | Python 近似 |

更严重的两个"完全虚构"：

- **UniFrac / PD 用的是模拟系统发育树**（`phylogenetic_analysis.py:51-103`）：
  ```
  """Here we create a deterministic pseudo-phylogeny based on taxonomic name similarity."""
  ...
  noise = np.random.RandomState(seed=42).normal(0, 0.05, ...)   # "Add some noise to make it more realistic"
  ```
  距离来自**物种名字符串前缀相似度 + 随机噪声**，与真实进化关系无关。poster 里"UniFrac beta diversity"与"Phylogenetic Diversity"两项宣传均无实现支撑。

- **PICRUSt2 用的是源码里手写的假参考库**（`functional_prediction.py:53-64`）：
  ```
  # ─── Reference Database (Mock / Pre-computed)
  # This is a simplified reference. In production, load from picrust2/default_files/
  ```

- **LEfSe**（`r_analysis.py:173-243`）三处错：
  1. `'group': str(sample_groups.mode()[0])` —— 每个 biomarker 的富集分组都取**全体样本的众数分组**，即所有 biomarker 分组相同，而 LEfSe 的核心输出就是"哪个组富集"；
  2. `lda_score = max_diff / pooled_std` 是 Cohen's d，不是 LDA 效应量，因此界面上默认阈值 2.0 的含义完全不同；
  3. 先按 p>0.05 过滤再算，**全程没有多重检验校正**。

**修复方向**：
1. 建立"方法执行凭证"机制——每个结果强制带 `engine: "R::DESeq2" | "python-approx"` + `engine_version`，前端对 `python-approx` 显著高亮警示；
2. 没装真包时**默认拒绝执行并提示安装命令**，把回退改成用户显式选择（`allow_approximation=true`）；
3. UniFrac / PICRUSt2 在接入真实树 / 真实参考库前，**从 UI 和 poster 中下线**；
4. 把近似实现改名（`lefse_like` / `deseq2_like`），不要复用原方法名。

### 2.4 具体统计量 bug（已用代码实测）

| 位置 | 问题 | 实测 |
|---|---|---|
| `analysis_engine.py:668` | ANOSIM `R=(rb-rw)/(n_ranks·(n_ranks-1)/4)`，分母误用**配对数**，正确应为**样本数** `N(N-1)/4` | 构造完全分离的两组：**报告 R=0.0046，正确值 R=1.0** |
| `analysis_engine.py:90` | Chao1 = `S_obs + F1²/(2·(F2+1e-10))`，F2=0 时被 1e-10 放大 | 3 个 singleton、0 个 doubleton：**报告 4.5×10¹⁰，教科书值 ≈7**。2bRAD-M 稀疏表极常见 |
| `analysis_engine.py:93-100` | `_calculate_ace` 实为偏差校正 Chao1 公式，**不是 ACE**，同样有 1e-10 溢出 | 名实不符 |
| `analysis_engine.py:246` | Jaccard 直接把丰度矩阵喂给 `pdist(metric='jaccard')`，scipy 对连续值不二值化 | 40 个共有菌的样本对，Jaccard **0.825–1.0**（正确应为 0） |
| `analysis_engine.py:110` | Pielou = `shannon/log(richness+1e-10)`，richness=1 时分母≈0 | 返回 inf |
| `analysis_engine.py:419` 等 6 处 | 手写 BH：`p·n/rank`，**未做单调性修正**（cummin），且 `rankdata(method='max')` | statsmodels 已在 venv 里却没用 |
| `analysis_engine.py:603` | PERMANOVA/ANOSIM 用全局 `np.random.permutation`，**无 seed 参数** | 同一份数据每次跑出不同 p 值，无法复现 |
| `analysis_engine.py:611` | PERMANOVA 不返回 R²（`SSB/SST`），而 R² 是论文里最常报告的量 | — |
| `analysis_engine.py:335` | NMDS 直接报 sklearn 的 `stress_`（原始平方和），**不是 Kruskal stress-1** | 生态学界按 <0.2 判读，此处数值不可比 |
| `analysis_engine.py:757` | `confusion_matrix(y_encoded, y_pred, labels=le.classes_)` 整数与字符串混用 | **TypeError 崩溃**，即 1 个失败测试 |
| `analysis_engine.py:752` | `cross_val_score(cv=min(5, n_classes))` —— 折数应由**最小类样本数**决定，与类别数无关 | 二分类时 cv=2 |
| `analysis.py:737` | `g1, g2 = groups[0], groups[1]` —— 差异分析的对比组是 metadata 里**前两个出现的值**，用户无法指定 | 7 个 Visit 的数据只比 T1 vs T4，其余静默丢弃；fold-change 方向随文件行序漂移 |

### 2.5 缺失的质量门禁

没有任何地方检查：测序深度差异、库大小离群、稀疏度、样本量是否足够、组间样本数是否极端不平衡、metadata 与丰度表样本是否对齐。而 `data_validator.py`（550 行，写得不错）**根本没有被任何路由或 Agent 调用**——Agent 里它被一个 `lambda: {"valid": True}` 顶替了（见 §3.4）。

---

## 3. P1 — 工程可用性缺陷（当前跑不通）

### 3.1 全局校验异常处理器自己会崩溃 → 所有 422 变成不可读的 500

`backend/app/main.py:63-73`：

```python
return JSONResponse(status_code=422, content={"detail": ..., "errors": exc.errors()})
```

Pydantic v2 的 `exc.errors()` 里含 `ctx.error` = 原始 `ValueError` 对象，不可 JSON 序列化 →
`TypeError: Object of type ValueError is not JSON serializable` → 客户端收到**空 body 的 500**。

这就是实测中 alpha/beta/random-forest 报 500 的真实原因。**整个 API 的参数错误全部不可诊断。**
修复：`exc.errors()` 改为 `jsonable_encoder(exc.errors())` 或 `exc.errors(include_context=False)`。

### 3.2 URL 命名与 `analysis_type` 枚举不一致，且该字段冗余

路由是 `/analyze/random-forest`，schema 要求 `analysis_type ∈ {..., "random_forest", ...}`（下划线）；
`/analyze/alpha-diversity` 要求 `"alpha"`；`/analyze/beta-diversity` 要求 `"beta"`。

路径已经唯一确定了分析类型，body 里再要一个必填、命名规则还不同的 `analysis_type`，纯属设计冗余。
修复：从 body 中删除该字段，由路由注入。

### 3.3 失败被当成成功返回

PERMANOVA / ANOSIM 失败时返回 **HTTP 201 + `status: "completed"` + `result_data: {"error": ...}`**（实测）。前端按 `status === "completed"` 判断成功，会把错误当结果渲染。
修复：service 层失败抛异常，路由层统一映射成 4xx/5xx；`job.status` 必须置 `failed` 且写 `error_message`。

### 3.4 Agent 层是空壳

| 位置 | 问题 |
|---|---|
| `agent/executor.py:94` | `def validate_data(...): return {"valid": True, "report": {}}` —— **每个模板的第 1 步都是它**，永远返回"数据没问题"，而真正的 `data_validator.py` 无人调用 |
| `agent/executor.py:255` | `"report_generator": lambda results, **kw: {"report_path": "/tmp/report.pdf"}` —— 返回一个**不存在的硬编码路径**，而它是旗舰模板 `full_multiomics_pipeline` 的终点 |
| `agent/executor.py:107-127` | 硬编码 `group_column="Visit"`、`reference_group="T4"` —— 只对 Huang 这一份数据成立 |
| `agent/executor.py:448` | `"has_plot": "plot_data" in str(result) or "plot" in str(result).lower()` —— 为了判断一个 bool，把整个结果（含 261×261 距离矩阵、完整 Plotly JSON）**字符串化两次** |
| `agent/executor.py:416` | `asyncio.gather(return_exceptions=True)` 之后再调 `traceback.format_exc()`，此时已无活跃异常，记录的 traceback 是错的 |
| `agent/executor.py:402-423` | `_execute_batch` 先 `await gather` 整批再返回事件 —— **SSE 不是真流式**，`step_start` 事件在该步已经跑完后才发出 |
| `agent/planner.py:88` | 模板正则 `marker.*discover\|differential.*abundance`，实测 "Find differential markers" **匹配不上**，返回只含空操作的 1 步计划，仍然 HTTP 200 |
| `api/routes/agent.py` | `/agent/analyze` 实测 500（DataFrame 真值判断） |

**修复方向**：先把 `data_validator` 和 `report_generator` 接到真实实现；planner 匹配失败时返回"需要澄清"而非假计划；改成真正的逐事件 `yield`。

### 3.5 前端主分析页面与上传流程完全断开

`sessionStore` 里有真实的 `sessionId`，`Agent.tsx` 和 `MultiOmics.tsx` 用了它，但：

```tsx
// Microbiome.tsx:279  (1579 行)
const sessionId = sessionStore.analysisResults?.summary ? "mock-session" : "mock-session";
// AnalysisSpecies.tsx:231 (1046 行)   同样
// MultiSite.tsx:219      (848 行)     同样
// Results.tsx:309/317    (445 行)     同样
// AnalysisStrain.tsx:228 (695 行)     const sessionId = "mock-session";
```

三元表达式两个分支是同一个字符串——占位符从未接线。**约 4400 行、占分析界面大部分的页面，上传真实数据后点分析必然 404。**

另外 `Microbiome.tsx:35` 把 metadata 列名写死成 `["Visit","Treatment","Group","Site","Timepoint","Gender","Age"]`，用户自己的分组变量选不到。应从 `/sessions/{id}/files` 返回的 metadata 列动态生成。

### 3.6 异步执行路径是个"静默挂起"陷阱

- `_should_use_async()`：**样本 >100 或特征 >1000 就走 Celery**（`analysis.py:75-93`）——Huang 数据 261 样本，所有分析都会走这条路；
- `_check_broker_available()` 定义了但**全仓库无人调用**（死代码）；
- Redis 不可用时 `celery_app.py` 回退到 SQLite broker，`.delay()` 会"成功"写入消息；
- **`docker/docker-compose.yml` 里只有 redis / backend / frontend，没有 celery worker 服务**；仓库内也没有任何启动 worker 的脚本。

合起来：任务被投递、无人消费、状态永远 `pending`，前端无限轮询。**比直接报错更糟。**
修复：投递前检查 worker 存活，无 worker 则同步执行或明确 503；compose 加 worker 服务。

### 3.7 `requirements.txt` 缺 10 个依赖 → Docker 镜像起不来

实测 `app/` 中被 import 但不在 requirements.txt 的包：
`networkx`、`PyYAML`、`statsmodels`、`scikit-bio`、`umap-learn`、`reportlab`、`scikit-learn-extra`、`openai`、`pyarrow`。

其中 **`networkx`（`services/network_analysis.py`）和 `yaml`（`knowledge/loader.py`）是从 `app.main` 可达的模块级 import** ——`docker/backend.Dockerfile` 只装 requirements.txt，容器启动即 ImportError。文档写的部署方式是坏的。

### 3.8 知识库两个硬伤（实测）

1. **非线程安全**：`loader.py:40` `sqlite3.connect(":memory:")` 用默认 `check_same_thread=True`。实测从工作线程调用：
   `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`。
   FastAPI 的同步路由（analysis.py 里 40 个路由有 31 个是 `def`）都跑在线程池里，一旦有同步路由碰 KB 就会随机失败。
   修复：`check_same_thread=False` + 一把锁，或改用普通 dict（60 条记录根本不需要 SQLite）。

2. **匹配规则与真实命名不兼容**。实测：

| 查询 | 结果 |
|---|---|
| `Faecalibacterium_prausnitzii` | HIT |
| `s__Faecalibacterium_prausnitzii`（MetaPhlAn/2bRAD-M 标准） | **miss** |
| `Faecalibacterium prausnitzii`（空格） | **miss** |
| `k__Bacteria\|p__...\|s__Faecalibacterium_prausnitzii`（全谱系） | **miss** |

原因：`fuzzy_lookup_taxon` 做的是 `KB.name LIKE '%query%'`，方向反了——应当先归一化（去 `s__`/`g__` 前缀、空格↔下划线、大小写、取最后一级）再双向匹配。

3. **`interpretation_engine.py:284` 的 `if "disease_associations" in info:` 是死代码**——`_row_to_taxon()` 返回的 dict 里从来没有这个 key（疾病关联存在另一张表且从未 join）。所以"菌种→疾病"注释永远不输出。

4. **领域错配**：60 个 taxa / 15 个疾病 100% 是肠道方向（Faecalibacterium、Akkermansia、IBD、肥胖、T2D……）。实验室的旗舰数据和 2bRAD 主战场是**口腔/唾液**——实测 `Streptococcus_mutans`、`Porphyromonas_gingivalis` 都不在库里。poster 把 KB 称为 "key innovation"，但它对本实验室自己的数据几乎不产生输出。

---

## 4. P2 — 架构、安全与运维

### 4.1 无任何认证/授权/限流
全仓库无 `OAuth2`/`APIKey`/`HTTPBearer`/鉴权依赖。session UUID 即凭证，知道 ID 就能读写他人数据、删除他人 session。同时 `allow_credentials=True` + 通配 methods/headers。作为对外 web server 发布前必须解决。

### 4.2 分块上传存在路径穿越
`upload.py:192`：`safe_name = f"{upload_state['file_type']}_{upload_state['original_filename']}"`
——`original_filename` 未做 `Path(...).name`，`file_type` 是自由 Form 字段，两者都可含 `../`。（普通上传路径 `upload.py:50` 做了 `.name`，分块路径漏了。）
另外 `file_storage.sanitize_filename()` 写好了却没在上传路径调用。

### 4.3 删除 session 不删磁盘文件
实测 `DELETE /sessions/{id}` → 204，DB 行删了，`uploads/{id}/` 原样保留。
当前仓库：**磁盘 230 个目录 vs DB 65 个 session，约 50 MB 孤儿数据**。对处理人体样本数据的平台，这是数据留存合规问题。

### 4.4 性能
- **每次分析请求都从磁盘重新解析原始文件**（日志可见 `Parsing file ...` 每请求一次）；`SessionManager` 的缓存层写好了但这条路径上没用；
- beta-diversity 返回完整 261×261 距离矩阵，**1.76 MB**；1000 样本约 26 MB，且无分页/无下采样；
- `parse_csv_tsv` 全程 `engine='python'`（比 C engine 慢 10–30×）；
- `comment='#'` 会截断含 `#` 的特征名；
- 未处理重复索引（同名 taxon）——`df.loc[feature, ...]` 会返回 DataFrame 而非 Series，静默产生错误结果。

### 4.5 代码卫生
- `/sessions/{id}/analyze/metabolomics` **注册了两次**（`analysis.py:1778` 和 `:1980`，请求体 schema 还不同），第二个是死代码；
- `DataParser.parse_metaphlan` / `parse_humann3` **各定义两次**（`data_parser.py:78/460`、`118/504`）；
- `analysis.py` 里 `import pandas as pd` 两次，`analysis_engine.py` 里 `from typing import ...` 两次，`agent_engine.py` 同样；
- `_save_result()` 硬编码 `Path('./uploads')`，绕过 `settings.UPLOAD_DIR`（容器里配的是 `/app/uploads`）；
- `datetime.utcnow()`（naive）直接返回给前端 —— 实测返回 `20:32` 而本地是 `04:32`，界面时间差 8 小时；Python 3.12 起已废弃；
- 项目根目录混入 20+ 个临时脚本（`fix_agent_engine.py`、`fix_extract_taxa.py`、`test_deep_debug.py`…）、生成的 PNG/PDF（多个 500–860 KB 的图**已提交进 git**）、还有一个名为 `core,`（带逗号）的空目录。

### 4.6 前端
- `frontend` 类型检查干净（`tsc --noEmit` 无错），UI 组件体系（shadcn/Radix/Plotly）搭得规整，这是项目里质量最好的部分；
- 但 `MultiOmics.tsx` 里 microbiome marker 与 metabolome marker 共用同一个 `result` state（PROJECT_CONTEXT 已记录，仍未修）；
- `Results.tsx` 的报告下载指向 `mock-session`。

### 4.7 测试策略是"绿灯幻觉"
212 个测试全绿，却检测不出上面任何一个统计 bug，因为断言只到"跑得通"这一层：

```python
assert 'chao1' in result.columns
assert (result['chao1'] >= 0).all()      # chao1 = 4.5e10 也能通过
assert dist.shape == (10, 10)            # jaccard 全是 1.0 也能通过
assert 'pseudo_f' in result              # PERMANOVA 只查 key 存在
```

**缺的是**：
1. **黄金值测试**——对固定输入，Shannon/Chao1/Bray-Curtis/PERMANOVA/ANOSIM 的结果必须与 `scikit-bio`（已在 venv 里）或 R `vegan` 数值一致（`np.testing.assert_allclose`）；
2. **端到端测试**——上传真实 Huang 数据 → 跑全流程 → 断言 PCoA 点数 == 261、`group_metadata` 非空；
3. **契约测试**——每个 analyze 端点在方向错误/样本不对齐时必须返回 4xx，不许返回 201。

---

## 5. 需求与定位层面的问题

对照 `poster_tool_introduction.md`：

| poster 宣称 | 实际 |
|---|---|
| "UniFrac beta diversity" | 名字字符串相似度模拟树 + 随机噪声 |
| "Functional Profiling / PICRUSt2" | 源码内手写 mock KO 库 |
| "LEfSe, ANCOM, ALDEx2, DESeq2, MaAsLin2" | 除 DESeq2/edgeR 外本机 R 包均未装，全部走 Python 近似；LEfSe 分组标签逻辑错误 |
| "MOFA+ / sparse CCA / DIABLO" | 自写近似，未对照原实现验证 |
| "Knowledge-Augmented Agent … **without requiring external LLM APIs**" | 存在 `llm_client.py` 调用 Moonshot Kimi API；且 KB 对口腔数据几乎无命中 |
| "Publication-ready … one-click export to PNG/SVG/PDF" | Agent 的 report_generator 返回硬编码 `/tmp/report.pdf` |
| "Open source: https://github.com/meta2banalyst" | 实际仓库是 `HuangShiLab/meta2banalyst`，poster 链接错误 |
| "designed for the 2bRAD toolkit ecosystem" | 代码里没有任何 2bRAD 特有逻辑（2b 标签深度、参考基因组覆盖、Strain2bScan 的三维结构只在 parser 里转成 long format） |

**定位建议**：现在这个工具的差异化点写的是"什么都能做"，但每一项都做不深，正面对上 MicrobiomeAnalyst / QIIME2 View / Galaxy 没有胜算。真正的护城河应该是**2bRAD 特有的东西**——2bRAD-M 的种/株级定量特性、Strain2bScan 的株水平结构、标签深度与基因组覆盖的质控指标、2bRAD 与 16S/shotgun 的可比性校正。这些别人做不了，而现在代码里恰恰一点都没有。

---

## 6. 建议的改进路线

### 阶段 0（发布/投稿前必须做，1–2 周）

1. **下线不可信功能**：UniFrac/PD、PICRUSt2、Agent 的 write-paper，从 UI、poster、README 中移除或明确标注 "experimental / not validated"。
2. **删除伪造内容**：PaperWriter 的伦理声明、测序方法默认值、无条件"significant"措辞。
3. **修 5 个硬崩溃/静默错误**：`main.py` 异常处理器、ANOSIM 分母、Chao1/ACE、Jaccard 二值化、RF 混淆矩阵。
4. **统一数据方向契约**（§2.1 的 5 步），并加一条"样本不对齐必须 400"的前置断言。
5. **补全 requirements.txt**，验证 `docker compose up` 能起来。

### 阶段 1（可信度基线，3–4 周）

6. 引入 `scikit-bio` + `statsmodels` 替换手写的 PCoA/PERMANOVA/ANOSIM/BH，并写**黄金值测试**（对 vegan 结果）。
7. 建立"方法执行凭证"：每个结果带 `engine` / `engine_version` / `is_approximation`，前端强制展示；缺真包时默认拒绝而非静默降级。
8. 前端 5 个页面接真实 `sessionId`；metadata 列从后端动态获取。
9. 错误语义统一：失败即 4xx/5xx + `job.status="failed"`，禁止 201+error。
10. 差异分析允许用户指定对比组与参照组，支持多组。

### 阶段 2（工程化，1–2 月）

11. 加认证 + 每 session 配额 + 限流；修分块上传路径穿越；删 session 连带清磁盘。
12. 解析结果落盘 parquet 并缓存，端点不再重复解析；大矩阵改为按需/分页返回。
13. Celery worker 补进 compose，投递前探活；或先改成"同步 + 进度条"更简单可靠。
14. Agent：接真 validator 和真 report generator，planner 匹配失败要求澄清，SSE 改真流式。
15. 端到端回归测试（真实数据）纳入 CI。

### 阶段 3（差异化，持续）

16. 做 2bRAD 原生能力：2bRAD-M 种/株级质控指标、Strain2bScan 株水平可视化、标签深度稀疏曲线、2bRAD↔16S/shotgun 可比性校正。
17. 知识库转向**口腔/唾液**（本实验室主场），并解决命名归一化；或直接换成对接 NCBI Taxonomy / BacDive 的在线查询。

---

## 7. 一句话优先级

> 先把"**算错的**"和"**编造的**"清干净，再谈补模块。
> 当前 GAP_ANALYSIS 里列的 19 个待补方法，一个都不该在阶段 0/1 完成之前动手。

---

*附：本报告所有实测数据可复现——启动 `backend`，上传 `Huang_mBio_microbiome.tsv` + `Huang_mBio_metadata.tsv`，依次调用 §1 表中的端点即可。审查过程中创建的测试 session 已删除。*
