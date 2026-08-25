# Meta2bAnalyst 文献挖掘管线 — 最终报告

## 一、挖掘执行概况

| 指标 | 数值 |
|------|------|
| 总 PDF 论文 | 101 篇 |
| 成功处理 | ~99 篇 |
| 失败/损坏 PDF | ~2 篇 (HTTP 429 / 非真实 PDF) |
| 提取 associations | 918 条 (staging) |
| quote-verified | 694 条 (75.6%) |

## 二、知识库规模

| 指标 | 数值 |
|------|------|
| 总 taxa | 421 |
| 有文献证据的 taxa | 361 (85.7%) |
| auto_generated (待审校) | 341 |
| 总 diseases | 25 |
| 有文献证据的 diseases | 5 |
| 总 evidence records | 940 |
| quote-verified evidence | 940 (100.0%) |

## 三、证据方向分布

| 方向 | 数量 | 占比 |
|------|------|------|
| enriched | 694 | 73.8% |
| depleted | 241 | 25.6% |
| mixed | 5 | 0.5% |
| associated | 0 | 0.0% |
| pathogenic | 0 | 0.0% |

## 四、研究类型分布

- **case_control**: 497
- **cohort**: 146
- **review**: 103
- **other**: 87
- **animal**: 54
- **RCT**: 36
- **in_vitro**: 17

## 五、疾病/条件分布 (Top 10)

- **periodontal_disease**: 304 条证据
- **dental_caries**: 97 条证据
- **rampant_caries**: 27 条证据
- **molar_incisor_pattern_periodontitis**: 25 条证据
- **visual_impairment**: 24 条证据
- **dental_fluorosis**: 23 条证据
- **type_1_diabetes**: 18 条证据
- **cerebral_palsy**: 16 条证据
- **carotid_intima_media_thickness**: 13 条证据
- **cigarette_smoking**: 13 条证据

## 六、高证据量 Taxa (Top 10)

- **Porphyromonas_gingivalis**: 23 条证据
- **streptococcus**: 21 条证据
- **neisseria**: 19 条证据
- **prevotella**: 19 条证据
- **actinomyces**: 18 条证据
- **Fusobacterium_nucleatum**: 17 条证据
- **Streptococcus_mutans**: 17 条证据
- **Prevotella_copri**: 16 条证据
- **veillonella**: 15 条证据
- **capnocytophaga**: 14 条证据

## 七、数据质量备注

1. **冲突未解决**: 12 个 (taxon, condition) 组合存在 KB 与文献方向冲突，已保留 KB 方向待人工审校
2. **Blocklist 过滤**: 58 条非疾病条件（如 diet、gender、clinical measures）已自动排除
3. **未映射疾病**: 约 70 个条件不在 disease_db 中，未建立反向索引
4. **待审校条目**: 341 个 taxon 标记为 auto_generated，需补充 gram_stain / oxygen / functions

## 八、文件路径

- 主 taxon 数据库: `app/knowledge/taxon_db.json` (592 KB)
- 主 disease 数据库: `app/knowledge/disease_db.json` (59 KB)
- Staging 关联数据: `knowledge_staging/associations.jsonl` (918 行)
- 处理日志: `logs/batch_mine_loop.log`
