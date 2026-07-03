# Meta2bAnalyst

## 项目简介
Meta2bAnalyst 是面向 2bRAD 工具群的一站式下游统计分析平台，为微生物组研究者提供从数据上传、预处理、统计分析到结果导出的完整工作流。平台支持物种水平、功能基因水平、株水平及多组学整合分析，兼容 2bRAD-M、Strain2bScan、Tag2bMap、QIIME、Mothur 等多种主流工具的输出格式，旨在降低微生物组数据分析的技术门槛，让研究者专注于生物学发现。

---

## 核心功能

### 1. 数据兼容性
- 支持 **2bRAD-M** 物种丰度与功能基因输出
- 支持 **Strain2bScan** 株水平分析结果
- 支持 **Tag2bMap** 标签映射与 ANI 数据
- 支持 **QIIME / BIOM** 标准微生物组格式
- 支持 **Mothur** 共享文件与分类注释
- 支持通用 **TSV/CSV** 丰度矩阵

### 2. 物种水平分析
- **Alpha 多样性**: Shannon, Simpson, Chao1, ACE, Observed, Pielou
- **Beta 多样性**: Bray-Curtis, Jaccard, Euclidean, Manhattan + PCoA/NMDS
- **差异分析**: t-test, Wilcoxon, ANOVA, Kruskal-Wallis
- **生物标志物**: LEfSe 线性判别分析
- **机器学习**: Random Forest 分类与特征重要性
- **可视化**: 热图、火山图、箱线图、散点图、网络图

### 3. 功能基因分析
- **功能预测**: KO, COG, KEGG 通路注释
- **通路富集**: 超几何检验 / Fisher 精确检验
- **功能差异**: 组间功能基因差异检验
- **通路可视化**: KEGG 通路映射、热图、气泡图

### 4. 株水平分析 ⭐（特色功能）
- **株组成分析**: 每个物种的株水平组成谱
- **株多样性**: Strain Richness, Strain Alpha Diversity
- **株差异分析**: 组间株组成差异检验
- **株网络分析**: 株共现/互斥网络（Co-occurrence / Mutual exclusion）
- **株替代分析**: Strain Replacement Score 量化组间株替换程度
- **株优势度**: Strain Dominance Index 识别主导株

### 5. 多组学整合
- **物种-功能联合**: 物种丰度与功能基因关联分析
- **物种-株联合**: 物种组成与株水平多样性联合可视化
- **功能-株联合**: 功能通路与株水平贡献分解
- **三层整合**: 物种-功能-株三层联合热图与网络

---

## 快速开始

### 使用 Docker 部署（推荐）

```bash
git clone https://github.com/your-org/meta2banalyst.git
cd meta2banalyst
cp .env.example .env
# 按需编辑 .env 配置文件
bash docker/build.sh
```

服务启动后访问 http://localhost 即可使用主界面。

### 本地开发环境

```bash
# 后端（终端 1）
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（终端 2）
cd frontend
npm install
npm run dev
```

前端开发服务器默认地址 http://localhost:5173。

---

## 使用指南

### 1. 数据上传

1. 在主界面选择分析模块：**物种水平 / 功能基因 / 株水平 / 多组学整合**
2. 选择您的数据格式（2bRAD-M / QIIME / Mothur / 通用 CSV 等）
3. 上传对应的输入文件（支持拖拽上传和点击选择）
4. 点击**"开始验证"**按钮

[Screenshot: 数据上传页面，显示四个分析模块卡片和文件上传区域]

### 2. 数据检查（Inspect）

验证完成后，系统显示数据检查结果：
- **样本名匹配状态**: 检查特征表与元数据中的样本名是否一一对应
- **数据概览统计**: 特征数、样本数、总读数、稀疏度
- **Library Size 分布**: 各样本的测序量分布柱状图
- **分组变量预览**: 元数据中的分组变量及各组样本数

确认数据无误后，点击 **"Proceed to Filter"** 进入下一步。

[Screenshot: 数据检查页面，显示样本匹配表格和 Library Size 分布图]

### 3. 数据过滤（Filter）

根据数据特征设置过滤参数，去除低质量特征：
- **低计数过滤**: 设置最小计数阈值（默认: 4）和 Prevalence 阈值（默认: 20%，即至少出现在 20% 样本中）
- **低方差过滤**: 移除低方差特征（默认: 移除 10% 最低方差特征）
- **Top N 筛选**: 仅保留丰度最高的 N 个特征（可选）

点击 **Submit** 应用过滤，查看过滤前后对比统计。

[Screenshot: 过滤参数设置面板和过滤结果对比]

### 4. 标准化（Normalize）

选择数据标准化方法，消除测序深度差异：
- **TSS** (Total Sum Scaling): 总和标准化，将每个样本缩放至相同总数
- **CSS** (Cumulative Sum Scaling): 累积和标准化，适合有偏分布
- **UQ** (Upper Quartile): 上四分位数标准化
- **CLR** (Centered Log-Ratio): 对数比转换，适合成分数据
- **RLE** (Relative Log Expression): 相对对数表达，参考 DESeq2
- **TMM** (Trimmed Mean of M-values): 截尾 M 值均值，参考 edgeR

> ⚠️ **注意**: Scaling（缩放）和 Transformation（转换）方法互斥，请根据分析类型选择：
> - 差异分析（DESeq2/edgeR）通常使用原始计数或 TMM/RLE
> - 多样性分析通常使用 TSS/CSS
> - 相关性/网络分析推荐使用 CLR

点击 **Submit** 应用标准化，点击 **"Proceed to Analysis"** 进入分析。

[Screenshot: 标准化方法选择界面，显示各方法说明和警告提示]

### 5. 分析（Analysis）

选择分析类型并配置参数：
- **群落分析**: Alpha 多样性、Beta 多样性、PCoA、NMDS、热图
- **差异分析**: 组间差异检验、火山图、LEfSe
- **聚类与网络**: 层次聚类、相关性网络、共现网络
- **机器学习**: Random Forest、特征重要性排序

设置分析参数（如分组变量、检验方法、阈值等），点击 **"运行分析"**。系统异步执行分析，完成后展示：
- 交互式图表（Plotly.js 驱动，支持缩放、平移、导出）
- 统计结果表格（支持排序、搜索、分页）
- 分析参数摘要

[Screenshot: 分析结果页面，显示箱线图和统计表格]

### 6. 结果导出

分析结果支持多种格式导出：
- **图表导出**: PNG（高分辨率）、SVG（矢量图）、PDF（出版级）
- **数据表格**: CSV 格式，包含完整统计量（均值、标准差、P 值、效应量等）
- **完整报告**: Markdown 格式，包含分析流程、参数、结果图表和解读建议

点击图表上方的下载按钮或表格下方的 **"Export Report"** 按钮即可。

[Screenshot: 结果导出按钮和报告预览]

---

## 支持的输入格式详解

### 2bRAD-M 输出

| 文件 | 必需 | 说明 |
|------|------|------|
| `species_abundance.csv` | 是 | 物种丰度矩阵，列为样本，行为物种 |
| `metadata.csv` | 是 | 样本元数据，包含分组变量和协变量 |
| `functional_genes.csv` | 否 | 功能基因预测矩阵（KO/COG/KEGG） |
| `strain_profile.csv` | 否 | 株水平组成矩阵（Strain2bScan 输出） |

### QIIME / BIOM 格式

| 文件 | 必需 | 说明 |
|------|------|------|
| `feature-table.biom` | 是 | BIOM 格式特征表（HDF5 或 JSON） |
| `metadata.csv` | 是 | 样本元数据（QIIME 元数据格式） |
| `taxonomy.tsv` | 否 | 特征分类注释（如 QIIME 2 `taxonomy.qza` 导出） |

### Mothur 格式

| 文件 | 必需 | 说明 |
|------|------|------|
| `*.shared` | 是 | Mothur 共享文件（OTU 表） |
| `*.taxonomy` | 是 | Mothur 分类注释文件 |
| `metadata.csv` | 是 | 样本元数据 |

### 通用 TSV/CSV 格式

| 文件 | 必需 | 说明 |
|------|------|------|
| `feature_table.csv` | 是 | 特征丰度矩阵（行为特征，列为样本） |
| `metadata.csv` | 是 | 样本元数据（行为样本，列为变量） |
| `taxonomy.csv` | 否 | 分类注释（特征名对应层级） |

### 数据格式要求

1. **特征表格式**:
   - 第一行以 `#NAME` 开头，后接样本名（制表符或逗号分隔）
   - 第一列为特征名（如 OTU ID、物种名、KO 编号）
   - 值为丰度计数（整数），非负
   - 示例:
     ```csv
     #NAME,Sample1,Sample2,Sample3
     OTU_1,100,150,80
     OTU_2,50,0,120
     ```

2. **元数据格式**:
   - 第一行以 `#NAME` 开头，后接样本名
   - 第一列为样本名（需与特征表列名完全匹配，大小写敏感）
   - 后续列为分组变量（如 Treatment, Group, Site）
   - 每组至少 **3 个重复样本**，否则无法进行统计检验
   - 示例:
     ```csv
     #NAME,Sample1,Sample2,Sample3
     Sample1,Control,SiteA
     Sample2,Treatment,SiteA
     Sample3,Control,SiteB
     ```

3. **分类注释格式**:
   - 分号分隔的层级（如 `k__Bacteria;p__Firmicutes;c__Bacilli;o__Lactobacillales;f__Lactobacillaceae;g__Lactobacillus;s__rhamnosus`）
   - 第一列为特征名，第二列为分类注释

4. **样本名匹配规则**:
   - 大小写敏感（`Sample1` ≠ `sample1`）
   - 特征表与元数据中的样本名必须完全对应
   - 未匹配的样本将被排除或报错（取决于配置）

---

## 统计方法说明

### Alpha 多样性

| 指标 | 说明 | 适用场景 |
|------|------|---------|
| **Shannon** | 丰富度和均匀度综合指数，值越高多样性越高 | 通用指标，推荐默认使用 |
| **Simpson** | 优势度指数，值越高优势种越明显 | 关注群落优势度 |
| **Chao1** | 基于稀有物种的丰富度估计 | 样本量较小时估计真实丰富度 |
| **ACE** | 基于覆盖度的丰富度估计，类似 Chao1 | 样本量较小时 |
| **Observed** | 实际观测到的特征（OTU/ASV/物种）数量 | 直观丰富度 |
| **Pielou** | 均匀度指数（Shannon / ln(Richness)），范围 0-1 | 评估群落均匀程度 |

### Beta 多样性

| 距离/指数 | 说明 | 适用场景 |
|------|------|---------|
| **Bray-Curtis** | 最常用的生态学距离，考虑丰度差异，范围 0-1 | 默认推荐，适用于群落组成比较 |
| **Jaccard** | 只考虑特征存在/缺失，不考虑丰度 | 关注群落成员组成而非丰度 |
| **Euclidean** | 欧氏距离，对异常值敏感 | 标准化后使用 |
| **Manhattan** | 曼哈顿距离，绝对差之和 | 对异常值较稳健 |

### 差异分析

| 方法 | 类型 | 说明 | 适用场景 |
|------|------|------|---------|
| **t-test** | 参数检验 | 两组比较，假设正态分布和方差齐性 | 大样本、近似正态分布 |
| **Wilcoxon** | 非参数检验 | 两组比较，不假设分布 | 小样本、非正态分布，推荐默认 |
| **ANOVA** | 参数检验 | 多组比较，假设正态分布 | 大样本、多组比较 |
| **Kruskal-Wallis** | 非参数检验 | 多组比较，不假设分布 | 小样本、多组比较 |
| **DESeq2** | 广义线性模型 | 基于负二项分布，保守，控制 FDR | 原始计数数据，严格统计 |
| **edgeR** | 广义线性模型 | 基于负二项分布，较敏感，检验效能高 | 原始计数数据，探索性分析 |
| **LEfSe** | 线性判别 + 效应大小 | 两步骤：Kruskal-Wallis + LDA | 生物标志物发现，多组比较 |

> **方法选择建议**:
> - 两组比较，样本量 < 30: 优先 Wilcoxon
> - 两组比较，样本量 ≥ 30: t-test 或 Wilcoxon 均可
> - 多组比较，探索性: Kruskal-Wallis + 事后检验
> - 多组比较，生物标志物: LEfSe
> - 原始计数，严格控制假阳性: DESeq2
> - 原始计数，高检验效能: edgeR

### 株水平统计 ⭐

| 指标 | 说明 | 计算方式 |
|------|------|---------|
| **Strain Richness** | 每个物种检测到的株数量 | 物种内不同株的计数 |
| **Strain Alpha Diversity** | 物种内株的多样性 | Shannon / Simpson 指数应用于株组成 |
| **Strain Dominance Index** | 某株在物种内的优势程度 | 该株丰度 / 物种总丰度 |
| **Strain Replacement Score** | 组间株组成替换程度 | 1 - 组间株组成的 Jaccard 相似度 |
| **Strain Co-occurrence Network** | 株共现/互斥网络 | 基于 SparCC 或 Pearson 相关性构建网络 |

---

## 项目结构

```
meta2bAnalyst/
├── frontend/                 # React 18 + TypeScript + Vite 前端
│   ├── src/
│   │   ├── components/       # 可复用 UI 组件（shadcn/ui 定制）
│   │   ├── pages/            # 页面级组件（上传、分析、结果）
│   │   ├── hooks/            # 自定义 React Hooks
│   │   ├── services/         # API 调用封装
│   │   ├── stores/           # Zustand 状态管理
│   │   ├── types/            # TypeScript 类型定义
│   │   └── utils/            # 工具函数
│   ├── public/               # 静态资源
│   ├── nginx.conf            # Nginx 生产配置
│   ├── vite.config.ts        # Vite 配置（含开发代理）
│   └── package.json
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # 应用入口与路由注册
│   │   ├── config.py         # Pydantic Settings 配置
│   │   ├── database.py       # SQLAlchemy ORM 与数据库连接
│   │   ├── models.py         # 数据库模型定义
│   │   ├── schemas.py        # Pydantic 请求/响应模型
│   │   └── api/              # 业务路由模块
│   │       ├── upload.py     # 文件上传与验证
│   │       ├── data.py       # 数据预处理（过滤、标准化）
│   │       ├── analysis.py   # 统计分析接口
│   │       ├── strain.py     # 株水平分析接口
│   │       ├── export.py     # 结果导出
│   │       └── sessions.py   # 会话管理
│   ├── scripts/              # 工具脚本
│   │   ├── generate_example_data.py  # 生成示例数据
│   │   ├── run_dev.sh        # 开发服务器启动
│   │   └── run_worker.sh     # Celery Worker 启动
│   ├── requirements.txt      # Python 依赖
│   └── uploads/              # 用户上传文件临时存储
├── docker/                   # Docker 部署配置
│   ├── docker-compose.yml    # 服务编排（frontend + backend + redis + nginx）
│   ├── frontend.Dockerfile   # 前端多阶段构建
│   ├── backend.Dockerfile    # 后端 slim 镜像
│   ├── nginx.conf            # Nginx 反向代理与静态文件
│   ├── build.sh              # 一键构建与启动
│   └── dev.sh                # 开发环境一键启动
├── docs/                     # 文档目录
│   ├── user_manual.md        # 用户操作手册
│   ├── api_guide.md          # API 使用指南
│   ├── video_tutorials/      # 视频教程脚本
│   └── screenshots/          # 截图占位目录
├── examples/                 # 示例数据
│   ├── 2brad_m_species.csv   # 2bRAD-M 物种丰度示例
│   ├── 2brad_m_function.csv  # 2bRAD-M 功能基因示例
│   ├── strain2bscan_output.csv  # Strain2bScan 株水平示例
│   ├── tag2bmap_output.csv   # Tag2bMap 输出示例（含 ANI）
│   └── qiime_feature_table.biom # QIIME BIOM 格式示例
├── .env.example              # 环境变量模板
├── Makefile                  # 常用命令封装
├── CONTRIBUTING.md           # 贡献指南
└── README.md                 # 本文件
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 前端框架 | React 18 + TypeScript | 函数组件 + Hooks，类型安全 |
| 构建工具 | Vite 8 | 极速 HMR，生产优化打包 |
| UI 组件 | Tailwind CSS + shadcn/ui | 原子化样式，可定制主题 |
| 可视化 | Plotly.js + React-Plotly | 交互式科学图表，支持出版级导出 |
| 后端框架 | Python FastAPI | 异步 API，自动 OpenAPI 文档生成 |
| ORM | SQLAlchemy | 数据库模型与查询构建 |
| 数据库 | SQLite（默认）/ PostgreSQL | 开发零配置，生产可扩展 |
| 缓存/队列 | Redis + Celery | 异步任务处理，分析结果缓存 |
| 数据处理 | Pandas + NumPy | 数据清洗、矩阵运算 |
| 统计 | SciPy + scikit-learn | 统计检验、机器学习 |
| R 集成 | rpy2 / subprocess | DESeq2, edgeR, vegan, LEfSe 等 R 包 |
| 部署 | Docker + Docker Compose | 环境一致性，一键部署 |
| 反向代理 | Nginx | 静态文件服务、负载均衡、SSL 终端 |

---

## API 文档

后端基于 FastAPI 自动生成 OpenAPI 规范文档：

- **Swagger UI**: http://localhost:8000/docs — 交互式 API 测试界面
- **ReDoc**: http://localhost:8000/redoc — 简洁美观的参考文档

主要 API 模块：
- `POST /api/v1/sessions` — 创建分析会话
- `POST /api/v1/sessions/{id}/upload` — 上传数据文件
- `GET /api/v1/sessions/{id}/inspect` — 数据检查与预览
- `POST /api/v1/sessions/{id}/filter` — 数据过滤
- `POST /api/v1/sessions/{id}/normalize` — 数据标准化
- `POST /api/v1/sessions/{id}/analyze/{type}` — 运行分析
- `GET /api/v1/sessions/{id}/results/{result_id}` — 获取结果
- `GET /api/v1/sessions/{id}/export` — 导出报告

详见 [docs/api_guide.md](docs/api_guide.md) 获取完整的 API 使用示例（Python / cURL）。

---

## 示例数据

项目提供 5 组示例数据，位于 `examples/` 目录，可直接用于测试和学习：

1. **`2brad_m_species.csv`** — 2bRAD-M 物种丰度表（30 样本 × 200 物种）
2. **`2brad_m_function.csv`** — 2bRAD-M 功能基因表（KO 注释）
3. **`strain2bscan_output.csv`** — Strain2bScan 株水平数据（含 10 个核心物种）
4. **`tag2bmap_output.csv`** — Tag2bMap 输出（含 ANI 矩阵和株标签）
5. **`qiime_feature_table.biom`** — QIIME BIOM 格式示例（16S rRNA 数据）

配套元数据文件 `metadata.csv` 包含以下分组变量：
- `Treatment`: Control / Treatment（两组比较）
- `Site`: SiteA / SiteB / SiteC（多组比较）
- `Time`: T0 / T1 / T2 / T3（时间序列）

使用示例数据可在 5 分钟内完成一次完整的分析流程。

---

## 常见问题（FAQ）

### Q: 上传文件大小限制是多少？
A: 默认单文件最大 100MB，可通过环境变量 `MAX_UPLOAD_SIZE`（单位：字节）调整。例如设置 `MAX_UPLOAD_SIZE=209715200` 可将限制提升至 200MB。

### Q: 支持哪些浏览器？
A: 支持 Chrome、Firefox、Safari、Edge 的最新两个主版本。推荐使用 Chrome 或 Firefox 以获得最佳交互体验。IE 浏览器不支持。

### Q: 我的数据安全吗？
A: 分析数据保存在您的本地服务器或 Docker 容器中，不上传到任何云端服务。临时会话数据在 30 分钟无活动后自动清理。您可通过环境变量 `SESSION_TTL_MINUTES` 调整会话保留时间。

### Q: 株水平分析需要多少样本？
A: 建议每组至少 **10 个样本**，每个核心物种至少检出 **3 个株**（不同标签或 ANI 簇），以获得稳健的统计结果。样本量不足时，株多样性估计可能不可靠，差异分析检验效能不足。

### Q: 为什么样本名匹配失败？
A: 常见原因：
1. 大小写不一致（如 `Sample1` vs `sample1`）— 系统区分大小写
2. 额外空格或特殊字符（如 `Sample1 ` vs `Sample1`）— 建议清理样本名
3. 特征表与元数据样本顺序不同 — 系统会自动匹配，但样本名必须一致
4. 元数据包含特征表中没有的样本 — 未匹配样本将被排除

### Q: 标准化方法和分析类型如何搭配？
A: 推荐组合：
- Alpha / Beta 多样性: TSS 或 CSS
- 差异分析（DESeq2/edgeR）: 使用原始计数或 TMM/RLE，**不要**预先 CLR 转换
- 机器学习 / 聚类: TSS 或 CSS 或 CLR
- 相关性 / 网络分析: CLR 转换

### Q: 如何引用 Meta2bAnalyst？
A: 如果您在研究中使用了 Meta2bAnalyst，请引用：
> [引用信息待补充，请关注项目 GitHub 页面的 Citation 部分]

---

## 贡献指南

欢迎为 Meta2bAnalyst 贡献代码、文档、示例数据或问题反馈！

详细的贡献流程、代码规范、开发环境搭建和 Pull Request 指南请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

简要流程：
1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -m 'feat: add some feature'`)
4. 推送分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

Copyright © 2024 Meta2bAnalyst Contributors.

---

## 联系我们

- 问题反馈: [GitHub Issues](https://github.com/your-org/meta2banalyst/issues)
- 文档讨论: [GitHub Discussions](https://github.com/your-org/meta2banalyst/discussions)
- 邮件联系: [meta2banalyst@example.com](mailto:meta2banalyst@example.com)

> 🚀 **开始您的微生物组数据分析之旅，请访问 [快速开始](#快速开始) 部分！**
