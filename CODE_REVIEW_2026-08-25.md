# Meta2bAnalyst 代码回顾与任务梳理 — 2026-08-25

> 前序文档：[`CODE_REVIEW_2026-08-14.md`](CODE_REVIEW_2026-08-14.md)、[`REPORT_2026-08-15.md`](REPORT_2026-08-15.md)、[`analysis_gap_report.md`](analysis_gap_report.md)、[`WORKFLOW_BRICK_DESIGN.md`](WORKFLOW_BRICK_DESIGN.md)
> 本次范围：48 commits 全量静态回顾（后端 ~39.3k 行 / 前端 React+TS）+ KB 文献挖掘管线遗留盘点
> 说明：本次审查时 shell 执行审批未通过，测试套件未能实际运行，结论基于静态审查 + 既有验证记录（08-15 矩阵：pytest 325 passed / pipeline_smoke 62 PASS）。**提交前必须重跑验证矩阵**。

---

## 一、项目现状总览

| 维度 | 状态 |
|---|---|
| 最新提交 | `a6d35a3` — Workflow Builder 拖拽式 DAG 编辑器（56 模块） |
| 模块注册表 | 宣称 56，实际 **55 个唯一模块**（`data_validator` 键重复，见问题 1） |
| 后端 | 73 个 service 模块，agent 体系（planner/executor/registry/integrator）完整 |
| 前端 | 18 个页面/组件文件 + shadcn/ui；oxlint 严格门禁已在 CI |
| CI | backend pytest + frontend lint/build + Playwright 全路由截图冒烟 |
| Docker | 真实 R 后端镜像，63/63 冒烟通过（08-20 验证） |
| KB | disease_db **49 条目**、taxon_db ~507 键（341 个 auto_generated 待审校） |

未提交工作（工作区）：
- `disease_db.json` / `taxon_db.json`：文献挖掘合并结果（+22,924 / −2,621 行）
- `merge_staging_kb.py`：别名表大幅扩充（牙周/龋齿/癌症/糖尿病/精神健康/IBD 等）+ 黑名单扩充
- `literature_mine.py`：移除 `response_format: json_object`（适配网关）
- ~30 个未跟踪的一次性 `check_*/debug_*/*.bak` 文件（卫生债）

---

## 二、代码审查发现

### 2.1 需要修复的问题

| # | 严重度 | 位置 | 问题 |
|---|---|---|---|
| 1 | 低 | `backend/app/agent/module_registry.py:61` 与 `:97` | **`data_validator` 重复定义**：dict 字面量中同键出现两次，后者静默覆盖前者。内容相同故无运行时影响，但"56 模块"表述不准（实为 55），且是合并事故的信号 |
| 2 | 低 | `backend/app/agent/executor.py:25-53` | **导入块重复 3–4 次**：`ExecutionPlan/PlanStep` ×3、`run_normalization` ×3、`run_outlier_detection` ×3、Phase 1b/2 服务导入 ×2。Phase 提交叠加时未清理 |
| 3 | 低 | `backend/app/agent/planner.py:21,23` | 同一行 import 重复两次 |
| 4 | 低 | `backend/app/services/r_analysis.py:787-825` | **死代码**：`run_ancom` / `run_maaslin2` / `run_aldex2` 三个 placeholder 函数无任何调用方（API 实际走 `run_ancombc` / `run_maaslin3` 与 `services/aldex2.py`）。删除避免误导 |
| 5 | 中 | `backend/app/services/multisite_analysis.py:124` | 占位特征值 `ev = np.array([50.0, 30.0])`，若该路径对用户可见需确认影响面 |
| 6 | 中 | `backend/app/services/icc_stability.py:255-331` | "Temporal Trend" 子图是 placeholder——用户给了 time_column 时会看到标注为占位符的图，应实现或隐藏 |
| 7 | 中 | 未跟踪文件 | ~30 个 `check_*.py` / `debug_*.py` / `_tmp_*.py` / `*.bak.20260822` 散落 `backend/` 根目录。按 08-15 的惯例归档到 `scripts/legacy/` 或删除 |

### 2.2 架构性观察（非阻塞）

1. **R 边界未统一**：`r_analysis.py`（subprocess + rpy2 混合）、各 Phase 2/3 wrapper 各自处理 R 会话。gap 报告 5.4 建议的统一 `RService` 中间层仍未做，模块越多维护成本越高。
2. **标准化解耦未完成**：`normalization` 模块已上线，但 `microbiome_marker` 强制 CLR、`metabolome_pca` 内置 zscore 等旧逻辑仍在，存在双路径。设计文档建议 feature flag 渐进切换。
3. **Workflow Builder 功能缺口**（对比 `WORKFLOW_BRICK_DESIGN.md` Phase 5）：
   - 无工作流**保存/加载**（`Save` 图标已 import 但未接线，无后端持久化端点）
   - Session ID 需手动输入，未与 sessionStore / 上传流程联动
   - `/agent/custom_plan` 自定义组合端点、依赖关系自动推导未实现
   - 执行结果只有状态栏计数，无结果面板/图表回显（执行产物没有回流到 Results 页）

---

## 三、KB 文献挖掘管线遗留盘点

| 事项 | 数量 | 位置/依据 |
|---|---|---|
| 无 OA 全文、待补充的文献 | **11 篇** | `knowledge_staging/redownload_pmids_remaining.txt`（可走 HKU Library 或 `mine_no_oa_abstracts.py` 摘要降级挖掘） |
| 新发现 OA 文献待下载 | **131 篇** | `backend/new_papers_download_list.md`（2026-08-21 生成，在库 140 篇之外） |
| auto_generated taxa 待人工审校 | **341 个** | 需补 gram_stain / oxygen / functions 字段 |
| 方向冲突待复核 | 12 个组合保留 KB 方向（其中 2 个已经微生物学审查手动修正） | `reports/mining_report.md` 冲突清单 |
| 非标准方向（pathogenic/associated 等） | 93 个已有 auto-resolve 逻辑覆盖 | `merge_staging_kb.py:357` |
| 未映射进 disease_db 的条件 | ~70 个 | 挖掘报告第七节；部分应入别名表，部分应入黑名单 |
| staging 合并未提交 | 整个 diff | 见第一节 |

---

## 四、任务计划（按优先级）

### P0 — 收尾与卫生（本周）

1. **提交 KB 合并批次**：`disease_db.json` + `taxon_db.json` + `merge_staging_kb.py` + `literature_mine.py`，一个语义化 commit（先 dry-run 复核再提交）。
2. **清理卫生债**：修复问题 1–4（重复键、重复导入、死代码），归档/删除 ~30 个一次性脚本与 `.bak`。
3. **重跑验证矩阵**：`pytest tests/` + `pipeline_smoke.py` + `tsc -b` / `oxlint` / `vite build`，确认 56 模块时代无回归（本次审查未能执行，是硬性前置）。

### P1 — KB 管线继续推进

4. **131 篇新 OA 下载 → 挖掘 → 合并**：按 `MACSTUDIO_PIPELINE.md` 流程跑一轮（collector `download_oa_fulltext.py` → `literature_mine.py` → `merge_staging_kb.py`）。
5. **11 篇无 OA 文献补全**：优先 HKU Library 批量下载；下载不到的走摘要降级挖掘并标注 `evidence_level=abstract_only`。
6. **341 个 auto_generated taxa 审校**：建议先做 Top 50 高证据量 taxa（P. gingivalis / Streptococcus / Neisseria 等已覆盖 80% 证据），不必一次清完。
7. **~70 个未映射条件归并**：扩充 `CONDITION_ALIASES` / `CONDITION_BLOCKLIST`，让下一批合并的漏网率下降。

### P2 — 设计文档未竟事项（WORKFLOW_BRICK_DESIGN 剩余）

8. `mixed_effects_diversity`（Phase 2 唯一剩余，复杂，rpy2 + lme4/vegan）
9. `bayesian_integration`（Phase 3 剩余，numpyro/PyMC，差异化功能）
10. **Workflow Builder 补全**：保存/加载工作流 + session 联动 + 结果面板回显（设计文档 Phase 5 的自定义组合接口）
11. **RService 统一封装** + 标准化解耦（feature flag 渐进切换）

### P3 — 文档与工程

12. README 更新至 56 模块现实；`analysis_gap_report.md` 标注"已落地/剩余"，避免按过时缺口重复规划。
13. 根目录积压的分析产物（20+ 张 PNG、Huang_mBio TSV、报告 md）考虑移入 `examples/` 或 `docs/` 子目录。

---

## 五、结论

代码库整体健康：架构契约（ModuleSpec + executor 映射）经受住了 22 → 56 模块的批量扩张，CI 门禁（pytest + 严格 lint + 截图冒烟）在防回归上发挥了作用。当前最大的风险不在代码质量，而在**未提交状态的体量**——KB 合并结果和管线脚本改进都只在工作区，加上一批散落的一次性脚本，建议先做 P0 提交与清理再推进新功能。

功能主线清晰：预处理层、统计检验、多组学整合、网络与多部位四个 Phase 已基本落地，剩余 `mixed_effects_diversity` 与 `bayesian_integration` 两个复杂模块 + Workflow Builder 的持久化/结果回显，是下一阶段的自然候选。
