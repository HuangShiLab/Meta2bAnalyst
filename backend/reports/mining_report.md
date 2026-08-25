# Meta2bAnalyst 文献挖掘管线 — 质量审查与统计汇总报告

> 生成时间: 2026-08-20
> 数据来源: `knowledge_staging/associations.jsonl` + `knowledge_staging/papers/*.json`

---

## 一、质量审查 (Quality Audit)

### 1.1 整体指标

| 指标 | 数值 |
|------|------|
| 总关联数 | **918** |
| 引文验证通过 | **694** (75.6%) |
| 引文验证失败 | **224** (24.4%) |
| 问题关联数 | **224** (24.4%) |
| 处理问题总数 | **224** |
| 已处理论文 | **99** 篇 |
| 每篇论文平均关联 | **9.3** |
| 每篇论文中位数关联 | **9** |

### 1.2 验证率最低的 5 篇论文（需人工复核）

| PMID | 验证率 | 提取关联 | 论文标题 |
|------|--------|----------|----------|
| 25973398 | 0% | 0 | Editorial: The oral microbiome in an ecological perspective... |
| 26413427 | 0% | 0 | Characterizing Diversity of Lactobacilli Associated with Sev... |
| 29959351 | 0% | 0 | Differential preservation of endogenous human and microbial ... |
| 34886820 | 0% | 7 | Functional screening of a human saliva metagenomic DNA revea... |
| 36171634 | 0% | 0 | Functional changes in the oral microbiome after use of fluor... |

### 1.3 验证率最高的 5 篇论文

| PMID | 验证率 | 提取关联 | 论文标题 |
|------|--------|----------|----------|
| 41479542 | 100% | 10 | The sociobiome – oral microbiome mediates dental caries amon... |
| 41568136 | 100% | 8 | Oral microbiota in an aging Swedish population with high den... |
| 41661350 | 100% | 1 | A clinical next-generation sequencing study on the microbial... |
| 41728109 | 100% | 15 | Peri-implantitis biofilm from explanted implants in Korean p... |
| 41800013 | 100% | 10 | Metagenomics as an Effective Diagnostic Approach for Explori... |

---

## 二、统计汇总 (Statistical Summary)

### 2.1 关联方向分布

| 方向 | 数量 | 占比 |
|------|------|------|
| enriched | 646 | 70.4% |
| depleted | 269 | 29.3% |
| mixed | 3 | 0.3% |

### 2.2 分类阶元分布

| 阶元 | 数量 | 占比 |
|------|------|------|
| species | 398 | 43.4% |
| genus | 365 | 39.8% |
| phylum | 82 | 8.9% |
| family | 29 | 3.2% |
| other | 17 | 1.9% |
| class | 17 | 1.9% |
| order | 10 | 1.1% |

### 2.3 Top 20 物种

| 排名 | 物种 | 关联数 |
|------|------|--------|
| 1 | Streptococcus | 27 |
| 2 | Prevotella | 23 |
| 3 | Porphyromonas gingivalis | 21 |
| 4 | Neisseria | 20 |
| 5 | Veillonella | 18 |
| 6 | Streptococcus mutans | 17 |
| 7 | Actinomyces | 16 |
| 8 | Firmicutes | 14 |
| 9 | Capnocytophaga | 14 |
| 10 | Fusobacterium | 14 |
| 11 | Treponema | 12 |
| 12 | Porphyromonas | 12 |
| 13 | Leptotrichia | 12 |
| 14 | Bacteroidetes | 11 |
| 15 | Tannerella forsythia | 11 |
| 16 | Treponema denticola | 10 |
| 17 | Proteobacteria | 9 |
| 18 | Corynebacterium | 9 |
| 19 | Haemophilus | 8 |
| 20 | Campylobacter | 8 |

### 2.4 Top 20 疾病/表型

| 排名 | 疾病/表型 | 关联数 |
|------|-----------|--------|
| 1 | periodontitis | 105 |
| 2 | dental caries | 53 |
| 3 | molar incisor pattern periodontitis | 45 |
| 4 | peri implantitis | 38 |
| 5 | stage iii periodontitis | 34 |
| 6 | high sugar beverage consumption | 34 |
| 7 | chronic periodontitis | 29 |
| 8 | healthy | 28 |
| 9 | rampant caries | 27 |
| 10 | odontogenic sinusitis | 26 |
| 11 | visual impairment | 24 |
| 12 | oral squamous cell carcinoma | 22 |
| 13 | periodontal disease | 19 |
| 14 | early childhood caries | 16 |
| 15 | cigarette smoking | 15 |
| 16 | elane associated neutropenia | 14 |
| 17 | elderly non diabetic | 13 |
| 18 | dental fluorosis | 13 |
| 19 | increased carotid intima media thickness | 13 |
| 20 | resolved periodontitis | 12 |

### 2.5 研究类型分布

| 研究类型 | 论文数 |
|----------|--------|
| case_control | 51 |
| cohort | 19 |
| review | 9 |
| other | 9 |
| animal | 6 |
| in_vitro | 2 |
| RCT | 2 |
| unknown | 1 |

### 2.6 发表年份分布

| 年份 | 论文数 |
|------|--------|
| 2012 | 1 |
| 2014 | 2 |
| 2015 | 2 |
| 2016 | 2 |
| 2017 | 3 |
| 2018 | 2 |
| 2019 | 4 |
| 2020 | 2 |
| 2021 | 12 |
| 2022 | 8 |
| 2023 | 10 |
| 2024 | 21 |
| 2025 | 21 |
| 2026 | 8 |

---

## 三、知识库合并结果

本次合并产生：
- **4 个新分类单元** 添加到 `taxon_db.json`
- **4 个新关联** 添加到现有分类单元
- **6 条文献证据记录** 添加
- **58 个非疾病条件** 被过滤（如饮食、年龄、健康对照等）
- **12 个方向冲突** 需要人工审核（保留 KB 原有方向）

### 方向冲突清单（需人工复核）

| 分类单元 | 疾病 | KB方向 | 文献方向 |
|----------|------|--------|----------|
| Fusobacterium nucleatum | periodontal_disease | pathogenic | enriched |
| Capnocytophaga | dental_caries | mixed | enriched |
| Granulicatella adiacens | periodontal_disease | mixed | depleted |
| Leptotrichia | periodontal_disease | depleted | mixed |
| Leptotrichia hofstadii | periodontal_disease | mixed | depleted |
| Neisseria | rampant_caries | depleted | mixed |
| Neisseria meningitidis | periodontal_disease | associated | enriched |
| Streptococcus | periodontal_disease | enriched | mixed |
| Streptococcus | rampant_caries | enriched | mixed |
| Veillonella dispar | dental_caries | mixed | depleted |
| Veillonella dispar | periodontal_disease | enriched | depleted |
| Veillonella parvula | periodontal_disease | enriched | depleted |

---

*报告由 Meta2bAnalyst 自动管线生成*
