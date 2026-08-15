# 文献挖掘 → 知识库管线（Literature → Knowledge Base Pipeline）

本文档描述 meta2banalyst 如何把外部文献收集产物转化为平台知识库，
以及与 `oral-microbiome-data-collector` skill 的协作边界。

## 总体闭环

```
oral-microbiome-data-collector (skill, 独立目录)
    │  收集 / 下载文献 PDF  →  papers/pdfs/
    ▼
scripts/audit_papers.py         完整性校验（%PDF 头，识别 HTML 错误页）
    │  有效 PDF → sample_data/oral_papers_valid/（符号链接）
    ▼
scripts/literature_mine.py      pypdf 抽取正文 → Kimi 结构化抽取
    │  （taxon / rank / condition / direction / evidence_quote）
    │  引文逐字回查 PDF 原文校验（quote_verified）
    ▼
backend/knowledge_staging/      papers/<PMID>.json + associations.jsonl
    │  ★ 人工审核区，gitignore，永不自动入库
    ▼
scripts/merge_staging_kb.py     默认 dry-run；--apply 才写库
    │  证据分级投票（RCT>cohort>case_control>review>in_vitro）
    │  方向冲突 → "mixed"；与已有 KB 冲突 → 保留 KB，打印待审
    │  新物种 → 骨架条目（auto_generated + [CURATE] 占位）
    ▼
app/knowledge/taxon_db.json     disease_associations（聚合方向）
    app/knowledge/disease_db.json   + disease_evidence / literature_evidence
                                    （PMID/年份/研究类型 provenance）
```

## 为什么 collector skill 不并入本仓库

- **职责不同**：collector 是通用的"文献/数据生产者"（还能抓 SRA 测序数据），
  meta2banalyst 是"消费者"。生产者产物（PDF 目录）就是两者之间的接口。
- **可复用性**：collector 未来服务其他项目（肠道、皮肤微生物组）时不受本仓库牵制。
- **合规**：下载的 PDF 有版权属性，不应进入 git 仓库；staging 与 sample_data
  均已 gitignore。
- 若确实想在仓库里固定 collector 的版本，用 `git submodule` 引用，不要复制代码。

## 关键字搜索

- `GET /api/v1/agent/knowledge/search?q=<keyword>&limit=20`
- 检索范围：物种名 / known_functions / main_products / health_markers / notes
  + 疾病名 / 描述。
- Python 侧：`app.knowledge.loader.search_knowledge(keyword, limit=20)`。

## 损坏文献的重下（两阶段）

1. `scripts/redownload_oa.py`：Europe PMC 解析 PMCID → OA 全文 PDF
   （fullTextPdf 接口 + `?pdf=render` 回退），下载后校验 %PDF 头，
   存入 `sample_data/oral_papers_redownloaded/`，文件名与原 staging 一致。
2. 非 OA 文献（`knowledge_staging/redownload_report.json` 的 `no_open_access` 段）
   走 HKU Library 订阅链路：HKU 内网 + 已登录浏览器（可用 kimi-webbridge
   驱动真实浏览器访问出版商页面下载），保存到同一目录后重新跑
   `literature_mine.py`（自动断点续跑）。

## 常用命令

```bash
cd backend
# 挖掘（断点续跑，自动跳过已完成）
env -u KIMI_BASE_URL -u KIMI_API_KEY venv/bin/python3 -u scripts/literature_mine.py \
    --pdf-dir ../sample_data/oral_papers_valid --sleep 0.5
# 合并（先 dry-run 审，再 apply）
venv/bin/python3 scripts/merge_staging_kb.py            # dry-run
venv/bin/python3 scripts/merge_staging_kb.py --apply    # 写库
```
