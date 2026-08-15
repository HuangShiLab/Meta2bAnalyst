#!/usr/bin/env python3
"""Batch translate Chinese UI text to English in frontend source files."""
import re

# Define translations for each file
TRANSLATIONS = {
    "pages/Home.tsx": {
        '2bRAD 工具群一站式统计分析平台': 'One-stop Statistical Analysis Platform for 2bRAD Toolkit',
        '兼容 QIIME, Mothur, 2bRAD-M, Strain2bScan 数据格式': 'Compatible with QIIME, Mothur, 2bRAD-M, Strain2bScan data formats',
        '物种水平分析': 'Species-Level Analysis',
        '群落分析': 'Community Analysis',
        '差异分析': 'Differential Analysis',
        '功能预测': 'Functional Prediction',
        '功能基因分析': 'Functional Gene Analysis',
        '通路富集': 'Pathway Enrichment',
        '功能差异': 'Functional Differential',
        '代谢网络': 'Metabolic Network',
        '株水平分析': 'Strain-Level Analysis',
        '株组成': 'Strain Composition',
        '株多样性': 'Strain Diversity',
        '株差异': 'Strain Differential',
        '多组学整合': 'Multi-Omics Integration',
        '物种-功能-株联合': 'Species-Function-Strain Integration',
        '跨组学关联': 'Cross-Omics Association',
        '联合可视化': 'Joint Visualization',
        '快速开始': 'Quick Start',
        '查看文档': 'Documentation',
        '支持的数据格式': 'Supported Data Formats',
        '1. 上传数据': '1. Upload Data',
        '支持多种微生物组数据格式，自动验证与解析': 'Supports multiple microbiome data formats with automatic validation and parsing',
        '2. 质控过滤': '2. QC & Filtering',
        '数据检查、过滤低计数特征、标准化处理': 'Data inspection, low-count feature filtering, normalization',
        '3. 分析与可视化': '3. Analysis & Visualization',
        '物种/功能/株水平分析，出版级图表导出': 'Species/Function/Strain-level analysis, publication-grade figure export',
    },
    "pages/Upload.tsx": {
        '数据上传': 'Data Upload',
        '选择数据格式并上传分析所需的文件': 'Select data format and upload files required for analysis',
        '数据格式': 'Data Format',
        '文件上传': 'File Upload',
        '拖拽文件到此处': 'Drag files here',
        '释放文件到此处': 'Drop files here',
        '或点击选择文件': 'or click to select files',
        '必需文件：': 'Required Files:',
        '可选文件：': 'Optional Files:',
        '已上传文件：': 'Uploaded Files:',
        '使用示例数据': 'Use Example Data',
        '加载中...': 'Loading...',
        '验证失败：请至少上传一个数据文件。': 'Validation failed: Please upload at least one data file.',
        '数据验证通过并已上传！': 'Data validation passed and uploaded!',
        '上传失败：': 'Upload failed: ',
        '加载示例数据失败：': 'Failed to load example data: ',
        '格式说明': 'Format Guide',
        '第一行为样本名，第一列为特征名，值为丰度计数。': 'First row: sample names; First column: feature names; Values: abundance counts.',
        '第一行为样本名，后续列为分组变量、实验条件等。': 'First row: sample names; Subsequent columns: grouping variables, experimental conditions, etc.',
        '包含特征名与分类学注释的对应关系。': 'Contains mapping between feature names and taxonomic annotations.',
        'QIIME 生成的 BIOM 格式丰度表，建议使用 JSON 格式。': 'QIIME-generated BIOM format abundance table; JSON format recommended.',
        '.shared 文件包含 OTU 丰度表，.taxonomy 文件包含分类注释。': '.shared file contains OTU abundance table; .taxonomy file contains taxonomic annotations.',
        '验证成功': 'Validation Success',
        '验证失败': 'Validation Failed',
    },
    "pages/Inspection.tsx": {
        '数据完整性检查': 'Data Integrity Check',
        '快速过滤': 'Quick Filter',
        '移除恒定特征（所有样本值相同）': 'Remove constant features (same value across all samples)',
        '数据类型': 'Data Type',
        '物种丰度': 'Species Abundance',
        '样本数': 'Samples',
        '特征数': 'Features',
        '总读数': 'Total Reads',
        '平均读数/样本': 'Avg Reads/Sample',
        '样本名匹配': 'Sample Name Matching',
        '已匹配': 'Matched',
        '未匹配': 'Not Matched',
        '标准化检测': 'Normalization Check',
        '已标准化': 'Normalized',
        '原始计数': 'Raw Counts',
        '实验因子': 'Experimental Factors',
        'Library Size 分布': 'Library Size Distribution',
        '元数据概览（前 5 行）': 'Metadata Overview (First 5 Rows)',
        '更新概览': 'Update Overview',
    },
    "pages/Filter.tsx": {
        '数据过滤': 'Data Filtering',
        '移除低计数和低方差特征，提升分析质量': 'Remove low-count and low-variance features to improve analysis quality',
        '低计数过滤': 'Low-Count Filtering',
        '最小计数': 'Minimum Count',
        '过滤方式': 'Filter Method',
        '特征必须至少在': 'Features must exceed the minimum count threshold in at least',
        '的样本中大于最小计数阈值才会被保留。': '% of samples to be retained.',
        '低方差过滤': 'Low-Variance Filtering',
        '移除比例': 'Removal Ratio',
        '将移除方差最低的': 'Will remove the lowest ',
        '% 特征。': '% variance features.',
        '基于': 'Based On',
        '应用过滤': 'Apply Filter',
        '重置': 'Reset',
        '过滤完成': 'Filtering Complete',
        '特征数变化:': 'Feature count changed:',
    },
    "pages/Normalize.tsx": {
        '数据标准化': 'Data Normalization',
        '标准化数据以消除测序深度差异的影响': 'Normalize data to eliminate sequencing depth bias',
        '标准化说明': 'Normalization Guide',
        '所有方法需要原始计数数据作为输入。缩放（Scaling）和变换（Transformation）为互斥操作，选择缩放后变换将被禁用。': 'All methods require raw count data as input. Scaling and Transformation are mutually exclusive; selecting Scaling will disable Transformation.',
        '稀疏化 (Rarefying)': 'Rarefying',
        '不稀疏化': 'No Rarefying',
        '稀疏化至': 'Rarefy to',
        '稀疏化将每个样本随机采样至相同读数，不推荐用于差异分析（会丢失信息）。': 'Rarefying randomly subsamples each sample to the same read count. Not recommended for differential analysis (information loss).',
        '缩放 (Scaling)': 'Scaling',
        '不缩放': 'No Scaling',
        '除以样本总读数（推荐）': 'Divide by total sample reads (Recommended)',
        '基于分位数的中值缩放': 'Median scaling based on quantiles',
        '使用上四分位数': 'Use upper quartile',
        '变换 (Transformation)': 'Transformation',
        '已选择缩放，变换已禁用（互斥操作）': 'Scaling selected, Transformation disabled (mutually exclusive)',
        '不变换': 'No Transformation',
        '适用于组成型数据': 'Suitable for compositional data',
        'DESeq2 标准化方法': 'DESeq2 normalization method',
        'edgeR 标准化方法': 'edgeR normalization method',
        '应用标准化': 'Apply Normalization',
        '标准化完成': 'Normalization Complete',
        '配置已保存：': 'Configuration saved: ',
    },
    "components/shared/AgentChat.tsx": {
        '综合分析我的数据': 'Comprehensive analysis of my data',
        '为什么Alpha不显著但LEfSe找到了差异？': 'Why is alpha not significant but LEfSe found differences?',
        '这些物种和什么疾病有关？': 'What diseases are these species related to?',
        '我应该下一步做什么？': 'What should I do next?',
        'Powered by structured knowledge base (50+ taxa, 17 methods, 10 disease signatures). No external LLM API required.': 'Powered by structured knowledge base (60+ taxa, 17 methods, 15 disease signatures). No external LLM API required.',
        '为什么': 'why',
        '怎么回事': 'what happened',
        '解释': 'explain',
        '矛盾': 'contradict',
        '物种': 'species',
        '菌': 'bacteria',
        '疾病': 'disease',
        '病': 'disease',
        '相关': 'related',
        '方法': 'method',
        '为什么用': 'why use',
        '假设': 'assumption',
        '综合分析': 'comprehensive analysis',
        '总结': 'summary',
    },
}

BASE_DIR = "/Users/shihuang/Documents/kimi/workspace/meta2banalyst/frontend/src"

def translate_file(rel_path: str, translations: dict):
    filepath = f"{BASE_DIR}/{rel_path}"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    for cn, en in translations.items():
        content = content.replace(cn, en)
    
    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        changed = sum(1 for cn in translations if cn in original)
        print(f"  {rel_path}: {changed} replacements")
    else:
        print(f"  {rel_path}: no changes")

def main():
    print("Translating frontend UI to English...")
    print("=" * 50)
    for rel_path, translations in TRANSLATIONS.items():
        translate_file(rel_path, translations)
    print("=" * 50)
    print("Done!")

if __name__ == "__main__":
    main()
