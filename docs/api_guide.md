# Meta2bAnalyst API 使用指南

> 本指南面向需要通过编程方式调用 Meta2bAnalyst 后端 API 的用户。涵盖会话创建、文件上传、数据检查、分析执行和结果导出的完整流程。

---

## 目录

1. [API 概述](#1-api-概述)
2. [认证与会话管理](#2-认证与会话管理)
3. [数据上传](#3-数据上传)
4. [数据检查与预处理](#4-数据检查与预处理)
5. [分析执行](#5-分析执行)
6. [结果获取与导出](#6-结果获取与导出)
7. [完整 Python 示例](#7-完整-python-示例)
8. [错误处理](#8-错误处理)
9. [API 端点参考](#9-api-端点参考)

---

## 1. API 概述

Meta2bAnalyst 后端基于 FastAPI 构建，提供 RESTful API 接口。所有 API 响应均为 JSON 格式。

### 基础信息

| 项目 | 说明 |
|------|------|
| 基础 URL | `http://localhost:8000`（开发环境） |
| API 前缀 | `/api/v1` |
| 完整基础 URL | `http://localhost:8000/api/v1` |
| 文档界面 | `http://localhost:8000/docs`（Swagger UI） |
| 数据格式 | JSON（请求/响应） |
| 文件上传 | `multipart/form-data` |

### HTTP 状态码

| 状态码 | 含义 | 处理方式 |
|-------|------|---------|
| 200 | 成功 | 正常处理响应数据 |
| 201 | 创建成功 | 新资源创建完成 |
| 400 | 请求参数错误 | 检查请求参数格式和必填项 |
| 404 | 资源未找到 | 检查会话 ID 或资源 ID 是否正确 |
| 422 | 验证错误 | 检查请求体是否符合 Pydantic 模型 |
| 500 | 服务器内部错误 | 查看后端日志，联系管理员 |

---

## 2. 认证与会话管理

### 2.1 认证说明

当前版本采用无状态会话管理，无需 API Key 或 Token 认证。所有操作基于会话 ID（Session ID）进行身份验证和权限控制。

> ⚠️ **注意**：请妥善保管会话 ID，拥有会话 ID 即可访问该会话的所有数据。在后续版本中可能会增加 API Key 认证。

### 2.2 创建会话

创建分析会话是调用 API 的第一步。会话用于隔离不同用户和分析任务的数据。

**请求：**

```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "data_format": "2brad_m",
    "analysis_level": "species"
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `data_format` | string | 是 | 数据格式：`2brad_m`, `qiime`, `mothur`, `csv` |
| `analysis_level` | string | 是 | 分析级别：`species`, `function`, `strain`, `multiomics` |

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "data_format": "2brad_m",
  "analysis_level": "species",
  "created_at": "2024-01-15T08:30:00Z",
  "status": "created",
  "expires_at": "2024-01-15T09:00:00Z"
}
```

**响应字段说明：**

| 字段 | 说明 |
|------|------|
| `session_id` | 会话唯一标识，后续操作均使用此 ID |
| `status` | 会话状态：`created`, `uploaded`, `inspected`, `filtered`, `normalized`, `analyzed`, `completed` |
| `expires_at` | 会话过期时间，默认 30 分钟 |

### 2.3 获取会话状态

```bash
curl http://localhost:8000/api/v1/sessions/{session_id}
```

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "status": "normalized",
  "data_format": "2brad_m",
  "analysis_level": "species",
  "files_uploaded": ["species_abundance.csv", "metadata.csv"],
  "filter_applied": true,
  "normalization_method": "tss",
  "created_at": "2024-01-15T08:30:00Z",
  "expires_at": "2024-01-15T09:00:00Z"
}
```

### 2.4 删除会话

```bash
curl -X DELETE http://localhost:8000/api/v1/sessions/{session_id}
```

---

## 3. 数据上传

### 3.1 上传文件

使用 `multipart/form-data` 格式上传数据文件。支持同时上传多个文件。

**请求：**

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/upload" \
  -F "files=@/path/to/species_abundance.csv" \
  -F "files=@/path/to/metadata.csv" \
  -F "files=@/path/to/functional_genes.csv"
```

**参数说明：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `files` | file | 是 | 文件列表，支持多个文件同时上传 |
| `session_id` | path | 是 | 会话 ID（URL 路径参数） |

> ⚠️ **文件大小限制**：单个文件最大 100MB，可通过环境变量 `MAX_UPLOAD_SIZE` 调整。

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "status": "uploaded",
  "files": [
    {
      "filename": "species_abundance.csv",
      "size": 154200,
      "rows": 200,
      "columns": 31,
      "status": "valid"
    },
    {
      "filename": "metadata.csv",
      "size": 3200,
      "rows": 30,
      "columns": 4,
      "status": "valid"
    }
  ],
  "message": "Upload successful. Proceed to inspect."
}
```

### 3.2 不同数据格式的上传要求

#### 2bRAD-M 格式

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/upload" \
  -F "files=@species_abundance.csv" \
  -F "files=@metadata.csv"
```

#### QIIME / BIOM 格式

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/upload" \
  -F "files=@feature-table.biom" \
  -F "files=@metadata.csv" \
  -F "files=@taxonomy.tsv"
```

#### Mothur 格式

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/upload" \
  -F "files=@final.shared" \
  -F "files=@final.taxonomy" \
  -F "files=@metadata.csv"
```

#### 通用 CSV 格式

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/upload" \
  -F "files=@feature_table.csv" \
  -F "files=@metadata.csv" \
  -F "files=@taxonomy.csv"
```

---

## 4. 数据检查与预处理

### 4.1 数据检查（Inspect）

上传完成后，调用数据检查接口获取数据概览和样本匹配状态。

```bash
curl http://localhost:8000/api/v1/sessions/{session_id}/inspect
```

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "status": "inspected",
  "feature_table": {
    "n_features": 200,
    "n_samples": 30,
    "total_reads": 1250000,
    "sparsity": 0.35,
    "mean_features_per_sample": 130
  },
  "metadata": {
    "n_samples": 30,
    "n_variables": 3,
    "grouping_variables": ["Treatment", "Site", "Time"]
  },
  "sample_matching": {
    "matched": 30,
    "unmatched_in_feature_table": 0,
    "unmatched_in_metadata": 0
  },
  "library_size": {
    "min": 35000,
    "max": 52000,
    "mean": 41667,
    "median": 41000
  },
  "group_summary": {
    "Treatment": {
      "Control": 15,
      "Treatment": 15
    }
  }
}
```

### 4.2 数据过滤（Filter）

根据数据特征设置过滤参数，去除低质量特征。

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/filter" \
  -H "Content-Type: application/json" \
  -d '{
    "min_count": 4,
    "prevalence": 0.20,
    "low_variance_filter": true,
    "low_variance_quantile": 0.10,
    "top_n": null
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|-------|------|
| `min_count` | integer | 否 | 4 | 最小计数阈值 |
| `prevalence` | float | 否 | 0.20 | Prevalence 阈值（0-1） |
| `low_variance_filter` | boolean | 否 | true | 是否启用低方差过滤 |
| `low_variance_quantile` | float | 否 | 0.10 | 移除最低方差的比例（0-1） |
| `top_n` | integer/null | 否 | null | 仅保留 Top N 特征，null 表示不启用 |

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "status": "filtered",
  "filter_summary": {
    "before": {
      "n_features": 200,
      "n_samples": 30
    },
    "after": {
      "n_features": 145,
      "n_samples": 30
    },
    "removed_features": 55,
    "removal_rate": 0.275
  }
}
```

### 4.3 数据标准化（Normalize）

选择标准化方法，消除测序深度差异。

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/normalize" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tss"
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `method` | string | 是 | — | `tss`, `css`, `uq`, `clr`, `rle`, `tmm` |

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "status": "normalized",
  "normalization_method": "tss",
  "preview": {
    "n_rows": 5,
    "n_cols": 5,
    "data": [
      ["OTU_1", "Sample1", "Sample2", "Sample3"],
      ["OTU_1", 0.0024, 0.0036, 0.0019],
      ["OTU_2", 0.0012, 0.0000, 0.0029],
      ["OTU_3", 0.0048, 0.0043, 0.0022]
    ]
  }
}
```

> ⚠️ **重要提示**：使用 DESeq2 或 edgeR 进行差异分析时，建议跳过标准化或直接使用 `rle`/`tmm` 方法。不要预先使用 TSS 或 CLR 后再输入 DESeq2/edgeR。

---

## 5. 分析执行

### 5.1 Alpha 多样性分析

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/analyze/alpha-diversity" \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": ["shannon", "simpson"],
    "grouping": "Treatment",
    "test_method": "wilcoxon"
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `metrics` | array[string] | 是 | — | `shannon`, `simpson`, `chao1`, `ace`, `observed`, `pielou` |
| `grouping` | string | 是 | — | 元数据中的分组变量名 |
| `test_method` | string | 否 | `wilcoxon` | `ttest`, `wilcoxon`, `anova`, `kruskal` |

**响应示例：**

```json
{
  "result_id": "res_alpha_001",
  "status": "completed",
  "analysis_type": "alpha_diversity",
  "metrics": ["shannon", "simpson"],
  "grouping": "Treatment",
  "test_method": "wilcoxon",
  "results": {
    "shannon": {
      "statistics": [
        {
          "group": "Control",
          "mean": 3.45,
          "median": 3.50,
          "sd": 0.42,
          "n": 15
        },
        {
          "group": "Treatment",
          "mean": 4.12,
          "median": 4.08,
          "sd": 0.38,
          "n": 15
        }
      ],
      "test_result": {
        "statistic": 52.0,
        "p_value": 0.003,
        "effect_size": 0.85
      }
    }
  },
  "plot_data": {
    "plot_type": "boxplot",
    "data": "..."
  }
}
```

### 5.2 Beta 多样性分析

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/analyze/beta-diversity" \
  -H "Content-Type: application/json" \
  -d '{
    "distance_method": "braycurtis",
    "grouping": "Treatment",
    "ordination": "pcoa"
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `distance_method` | string | 是 | — | `braycurtis`, `jaccard`, `euclidean`, `manhattan` |
| `grouping` | string | 是 | — | 元数据中的分组变量名 |
| `ordination` | string | 否 | `pcoa` | `pcoa`, `nmds`, `pca` |

### 5.3 差异分析（DESeq2）

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/analyze/differential" \
  -H "Content-Type: application/json" \
  -d '{
    "test_method": "deseq2",
    "grouping": "Treatment",
    "group_a": "Control",
    "group_b": "Treatment",
    "multiple_testing": "bh",
    "alpha": 0.05
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `test_method` | string | 是 | — | `ttest`, `wilcoxon`, `anova`, `kruskal`, `deseq2`, `edger`, `lefsе` |
| `grouping` | string | 是 | — | 分组变量名 |
| `group_a` | string | 是 | — | 对照组名称 |
| `group_b` | string | 是 | — | 处理组名称 |
| `multiple_testing` | string | 否 | `bh` | `bh`, `bonferroni`, `none` |
| `alpha` | float | 否 | 0.05 | 显著性阈值 |

> ⚠️ **注意**：使用 DESeq2 或 edgeR 时，建议数据使用原始计数或 `rle`/`tmm` 标准化，不要预先 TSS/CLR 转换。

### 5.4 LEfSe 生物标志物分析

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/analyze/lefsе" \
  -H "Content-Type: application/json" \
  -d '{
    "grouping": "Treatment",
    "lda_threshold": 2.0,
    "p_value_threshold": 0.05
  }'
```

### 5.5 Random Forest 机器学习

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/analyze/random-forest" \
  -H "Content-Type: application/json" \
  -d '{
    "grouping": "Treatment",
    "n_estimators": 500,
    "cv_folds": 5,
    "importance_metric": "gini"
  }'
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `grouping` | string | 是 | — | 目标分组变量 |
| `n_estimators` | integer | 否 | 500 | 树的数量（100-2000） |
| `cv_folds` | integer | 否 | 5 | 交叉验证折数（3, 5, 10, 0=LOOCV） |
| `importance_metric` | string | 否 | `gini` | `gini`, `accuracy` |

### 5.6 相关性网络分析

```bash
curl -X POST "http://localhost:8000/api/v1/sessions/{session_id}/analyze/correlation-network" \
  -H "Content-Type: application/json" \
  -d '{
    "correlation_method": "sparcc",
    "p_value_threshold": 0.05,
    "correlation_threshold": 0.3,
    "layout": "fruchterman"
  }'
```

> ⚠️ **注意**：构建网络前，数据应使用 `clr` 或 `tss` 标准化。

### 5.7 获取分析结果

```bash
curl "http://localhost:8000/api/v1/sessions/{session_id}/results/{result_id}"
```

**响应包含：**
- `plot_data`: Plotly.js 格式的图表数据
- `statistics`: 统计结果表格
- `parameters`: 分析参数摘要
- `status`: 分析状态（`running`, `completed`, `failed`）

---

## 6. 结果获取与导出

### 6.1 获取结果列表

```bash
curl "http://localhost:8000/api/v1/sessions/{session_id}/results"
```

**响应示例：**

```json
{
  "session_id": "sess_abc123def456",
  "results": [
    {
      "result_id": "res_alpha_001",
      "analysis_type": "alpha_diversity",
      "created_at": "2024-01-15T08:35:00Z",
      "status": "completed"
    },
    {
      "result_id": "res_beta_001",
      "analysis_type": "beta_diversity",
      "created_at": "2024-01-15T08:37:00Z",
      "status": "completed"
    }
  ]
}
```

### 6.2 导出图表

```bash
curl "http://localhost:8000/api/v1/sessions/{session_id}/results/{result_id}/plot?format=svg" \
  --output plot.svg
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `format` | query | 否 | `png` | `png`, `svg`, `pdf` |
| `width` | query | 否 | 1200 | 图像宽度（像素） |
| `height` | query | 否 | 800 | 图像高度（像素） |
| `dpi` | query | 否 | 300 | 分辨率（仅 PNG） |

### 6.3 导出数据表格

```bash
curl "http://localhost:8000/api/v1/sessions/{session_id}/results/{result_id}/table?format=csv" \
  --output results.csv
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `format` | query | 否 | `csv` | `csv`, `tsv`, `json` |

### 6.4 导出完整报告

```bash
curl "http://localhost:8000/api/v1/sessions/{session_id}/results/{result_id}/report?format=markdown" \
  --output report.md
```

**参数说明：**

| 参数 | 类型 | 必需 | 默认值 | 选项 |
|------|------|------|-------|------|
| `format` | query | 否 | `markdown` | `markdown`, `html`, `pdf` |

---

## 7. 完整 Python 示例

以下是一个完整的 Python 示例，演示从创建会话到导出结果的完整流程。

```python
import requests
import json
import time

# 配置
BASE_URL = "http://localhost:8000/api/v1"
DATA_DIR = "/path/to/your/data"

# 1. 创建会话
session_payload = {
    "data_format": "2brad_m",
    "analysis_level": "species"
}

response = requests.post(f"{BASE_URL}/sessions", json=session_payload)
session = response.json()
session_id = session["session_id"]

print(f"Session created: {session_id}")
print(f"Expires at: {session.get('expires_at')}")

# 2. 上传文件
upload_files = {
    "files": [
        ("files", open(f"{DATA_DIR}/species_abundance.csv", "rb")),
        ("files", open(f"{DATA_DIR}/metadata.csv", "rb"))
    ]
}

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/upload",
    files=upload_files
)

upload_result = response.json()
print(f"Upload status: {upload_result['status']}")
for f in upload_result.get("files", []):
    print(f"  - {f['filename']}: {f['rows']} rows × {f['columns']} cols")

# 3. 数据检查
response = requests.get(f"{BASE_URL}/sessions/{session_id}/inspect")
inspect = response.json()

print(f"\nData inspection:")
print(f"  Features: {inspect['feature_table']['n_features']}")
print(f"  Samples: {inspect['feature_table']['n_samples']}")
print(f"  Matched samples: {inspect['sample_matching']['matched']}")
print(f"  Grouping variables: {inspect['metadata']['grouping_variables']}")

# 4. 数据过滤
filter_payload = {
    "min_count": 4,
    "prevalence": 0.20,
    "low_variance_filter": True,
    "low_variance_quantile": 0.10
}

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/filter",
    json=filter_payload
)
filter_result = response.json()

print(f"\nFiltering:")
print(f"  Before: {filter_result['filter_summary']['before']}")
print(f"  After: {filter_result['filter_summary']['after']}")
print(f"  Removed: {filter_result['filter_summary']['removed_features']} features")

# 5. 数据标准化
normalize_payload = {
    "method": "tss"
}

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/normalize",
    json=normalize_payload
)

print(f"\nNormalization: {response.json()['normalization_method']}")

# 6. Alpha 多样性分析
alpha_payload = {
    "metrics": ["shannon", "simpson"],
    "grouping": "Treatment",
    "test_method": "wilcoxon"
}

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/analyze/alpha-diversity",
    json=alpha_payload
)
alpha_result = response.json()

print(f"\nAlpha diversity analysis:")
print(f"  Result ID: {alpha_result['result_id']}")
print(f"  Status: {alpha_result['status']}")

# 7. Beta 多样性分析
beta_payload = {
    "distance_method": "braycurtis",
    "grouping": "Treatment",
    "ordination": "pcoa"
}

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/analyze/beta-diversity",
    json=beta_payload
)
beta_result = response.json()

print(f"\nBeta diversity analysis:")
print(f"  Result ID: {beta_result['result_id']}")

# 8. DESeq2 差异分析
# 注意：使用原始计数或 RLE/TMM 标准化，不要先用 TSS
diff_payload = {
    "test_method": "deseq2",
    "grouping": "Treatment",
    "group_a": "Control",
    "group_b": "Treatment",
    "multiple_testing": "bh",
    "alpha": 0.05
}

response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/analyze/differential",
    json=diff_payload
)
diff_result = response.json()

print(f"\nDifferential analysis:")
print(f"  Result ID: {diff_result['result_id']}")

# 等待分析完成（实际使用时建议轮询或异步回调）
time.sleep(5)

# 9. 获取结果列表
response = requests.get(f"{BASE_URL}/sessions/{session_id}/results")
results = response.json()

print(f"\nAll results:")
for r in results["results"]:
    print(f"  - {r['result_id']}: {r['analysis_type']} ({r['status']})")

# 10. 导出图表和数据
for r in results["results"]:
    result_id = r["result_id"]
    
    # 导出 SVG 图表
    plot_response = requests.get(
        f"{BASE_URL}/sessions/{session_id}/results/{result_id}/plot",
        params={"format": "svg"}
    )
    with open(f"{result_id}_plot.svg", "wb") as f:
        f.write(plot_response.content)
    
    # 导出 CSV 表格
    table_response = requests.get(
        f"{BASE_URL}/sessions/{session_id}/results/{result_id}/table",
        params={"format": "csv"}
    )
    with open(f"{result_id}_table.csv", "wb") as f:
        f.write(table_response.content)

print(f"\nExport completed!")

# 11. 导出完整报告
report_response = requests.get(
    f"{BASE_URL}/sessions/{session_id}/results/{alpha_result['result_id']}/report",
    params={"format": "markdown"}
)
with open("report.md", "wb") as f:
    f.write(report_response.content)

print(f"Report exported: report.md")

# 12. 删除会话（清理数据）
response = requests.delete(f"{BASE_URL}/sessions/{session_id}")
print(f"Session deleted: {response.status_code == 200}")
```

### 异步分析轮询示例

```python
def poll_analysis_result(session_id, result_id, timeout=300, interval=5):
    """轮询分析结果，直到完成或超时"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = requests.get(
            f"{BASE_URL}/sessions/{session_id}/results/{result_id}"
        )
        result = response.json()
        
        if result["status"] == "completed":
            return result
        elif result["status"] == "failed":
            raise Exception(f"Analysis failed: {result.get('error', 'Unknown error')}")
        
        print(f"Analysis running... ({int(time.time() - start_time)}s)")
        time.sleep(interval)
    
    raise TimeoutError("Analysis timed out")

# 使用
result = poll_analysis_result(session_id, diff_result["result_id"])
print(f"Analysis completed: {result['result_id']}")
```

---

## 8. 错误处理

### 8.1 常见错误及处理

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

def api_call(method, endpoint, **kwargs):
    """带错误处理的 API 调用"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        error_data = e.response.json()
        
        if e.response.status_code == 400:
            print(f"Bad Request: {error_data.get('detail', 'Invalid parameters')}")
            # 检查参数并重试
        elif e.response.status_code == 404:
            print(f"Not Found: {error_data.get('detail', 'Resource not found')}")
            # 检查会话 ID 或资源 ID
        elif e.response.status_code == 422:
            print(f"Validation Error: {error_data.get('detail', 'Invalid input')}")
            # 检查请求体格式
        elif e.response.status_code >= 500:
            print(f"Server Error: {error_data.get('detail', 'Internal server error')}")
            # 联系管理员或稍后重试
        
        raise
    except requests.exceptions.ConnectionError:
        print("Connection Error: Backend server is not running")
        raise
    except requests.exceptions.Timeout:
        print("Timeout: Request timed out, please retry")
        raise

# 使用
result = api_call("POST", "/sessions", json={"data_format": "2brad_m", "analysis_level": "species"})
```

### 8.2 错误响应格式

```json
{
  "detail": "Sample names in feature table and metadata do not match",
  "error_code": "SAMPLE_MISMATCH",
  "suggestions": [
    "Check case sensitivity of sample names",
    "Remove extra spaces in sample names",
    "Ensure both files use the same sample identifiers"
  ]
}
```

---

## 9. API 端点参考

### 9.1 会话管理

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/sessions` | 创建会话 |
| GET | `/sessions/{session_id}` | 获取会话状态 |
| DELETE | `/sessions/{session_id}` | 删除会话 |
| GET | `/sessions/{session_id}/results` | 获取会话结果列表 |

### 9.2 数据上传与预处理

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/sessions/{session_id}/upload` | 上传文件 |
| GET | `/sessions/{session_id}/inspect` | 数据检查 |
| POST | `/sessions/{session_id}/filter` | 数据过滤 |
| POST | `/sessions/{session_id}/normalize` | 数据标准化 |

### 9.3 分析执行

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/sessions/{session_id}/analyze/alpha-diversity` | Alpha 多样性 |
| POST | `/sessions/{session_id}/analyze/beta-diversity` | Beta 多样性 |
| POST | `/sessions/{session_id}/analyze/differential` | 差异分析 |
| POST | `/sessions/{session_id}/analyze/lefsе` | LEfSe 分析 |
| POST | `/sessions/{session_id}/analyze/correlation-network` | 相关性网络 |
| POST | `/sessions/{session_id}/analyze/random-forest` | Random Forest |
| POST | `/sessions/{session_id}/analyze/heatmap` | 热图 |
| POST | `/sessions/{session_id}/analyze/pcoa` | PCoA 可视化 |
| POST | `/sessions/{session_id}/analyze/nmds` | NMDS 可视化 |

### 9.4 结果导出

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/sessions/{session_id}/results/{result_id}` | 获取结果详情 |
| GET | `/sessions/{session_id}/results/{result_id}/plot` | 导出图表 |
| GET | `/sessions/{session_id}/results/{result_id}/table` | 导出数据表格 |
| GET | `/sessions/{session_id}/results/{result_id}/report` | 导出完整报告 |

---

> 本 API 指南最后更新于 2024 年。API 可能会随版本更新而变化，请以 Swagger UI 文档 (`http://localhost:8000/docs`) 为准。
