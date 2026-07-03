# Meta2bAnalyst

> **2bRAD 工具群统计分析平台** — 一站式微生物组数据分析与可视化解决方案。

[![React](https://img.shields.io/badge/React-19-blue)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8-purple)](https://vitejs.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-teal)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-yellow)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-ready-blue)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 核心功能

Meta2bAnalyst 提供多维度微生物组数据分析能力，覆盖物种、功能、菌株及多组学整合分析：

- **物种水平分析** — OTU/ASV 聚类、物种注释、多样性分析（α / β）、物种组成与差异检验
- **功能基因分析** — 功能基因预测（PICRUSt2 / Tax4Fun）、通路富集、功能差异检验
- **株水平分析** — 菌株追踪、同源株识别、株水平多样性、菌株来源与宿主关联分析
- **多组学整合** — 16S / 宏基因组 / 代谢组联合分析、相关性网络、多维可视化

---

## 快速开始（Docker 部署）

### 前置要求

- [Docker](https://docs.docker.com/get-docker/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/install/) 2.20+

### 一键启动

```bash
git clone <repository-url>
cd meta2bAnalyst

# 1. 复制环境配置（按需修改）
cp .env.example .env

# 2. 构建并启动所有服务
bash docker/build.sh
```

服务启动后访问：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost | 主应用界面 |
| 后端 API | http://localhost:8000 | REST API |
| 接口文档 | http://localhost:8000/docs | Swagger / OpenAPI |
| 备选文档 | http://localhost:8000/redoc | ReDoc 风格 |

### 停止服务

```bash
docker-compose -f docker/docker-compose.yml down
```

---

## 开发环境搭建

### 方式 1：一键开发脚本（推荐）

```bash
bash docker/dev.sh
```

脚本会自动启动：
- Redis 容器（端口 6379）
- FastAPI 后端（端口 8000，热重载）
- Vite 前端（端口 5173，热重载）

### 方式 2：手动启动

**终端 1 — 启动 Redis**
```bash
docker run -d --name meta2b-redis -p 6379:6379 redis:7-alpine
```

**终端 2 — 启动后端**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**终端 3 — 启动前端**
```bash
cd frontend
npm install
npm run dev
```

### 开发环境常用命令（Makefile）

```bash
make dev       # 启动开发环境（等同于 dev.sh）
make stop      # 停止开发服务
make test      # 运行后端测试
make build     # 构建 Docker 镜像
make up        # 生产环境启动（Docker）
make down      # 生产环境停止
make logs      # 查看 Docker 日志
make clean     # 清理 Docker 容器与镜像
```

---

## 项目结构

```
meta2bAnalyst/
├── frontend/               # React + Vite 前端
│   ├── src/               # 源码（组件、页面、状态管理）
│   ├── public/            # 静态资源
│   ├── nginx.conf         # Nginx 生产配置
│   ├── vite.config.ts     # Vite 配置（含开发代理）
│   └── package.json
├── backend/                # FastAPI 后端
│   ├── app/               # 应用代码
│   │   ├── main.py        # 入口与路由注册
│   │   ├── config.py      # 配置（Pydantic Settings）
│   │   ├── database.py    # SQLAlchemy 数据库
│   │   ├── models.py      # 数据模型
│   │   ├── schemas.py     # Pydantic 序列化
│   │   └── api/           # 业务路由（upload, data, analysis, strain, export, sessions）
│   ├── scripts/           # 工具脚本
│   ├── requirements.txt   # Python 依赖
│   ├── venv/              # 虚拟环境（开发）
│   └── uploads/           # 用户上传文件
├── docker/                 # Docker 部署配置
│   ├── docker-compose.yml # 编排定义（frontend + backend + redis）
│   ├── frontend.Dockerfile # 多阶段构建前端镜像
│   ├── backend.Dockerfile # 后端 slim 镜像
│   ├── nginx.conf         # Nginx 反向代理配置
│   ├── build.sh           # 一键构建与启动
│   └── dev.sh             # 开发环境一键启动
├── .env.example           # 环境变量模板
├── Makefile               # 常用命令封装
└── README.md              # 本文件
```

---

## 支持的输入格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| CSV | `.csv` | 通用丰度表（样本 × 物种/功能） |
| TSV | `.tsv` | 制表符分隔的丰度表 |
| BIOM | `.biom` | 微生物组标准 BIOM 格式（HDF5 / JSON） |
| Mothur Shared | `.shared` | Mothur OTU 共享文件 |
| Mothur Taxonomy | `.taxonomy` | Mothur 物种注释文件 |
| HDF5 | `.h5` | 大规模矩阵数据 |

---

## 技术栈

| 层级 | 技术 | 选型理由 |
|------|------|---------|
| **前端** | React 19 + Vite 8 + TypeScript | 现代组件化、极速 HMR、类型安全 |
| **UI** | Tailwind CSS + Radix UI + shadcn/ui | 原子化样式、无障碍、可定制 |
| **可视化** | Plotly.js + React-Plotly | 交互式科学图表、 publication-ready |
| **后端** | FastAPI + Python 3.11 | 高性能异步 API、自动文档、类型校验 |
| **数据库** | SQLite（默认）/ PostgreSQL（生产） | 开发零配置、生产可扩展 |
| **缓存 / 队列** | Redis + Celery | 任务队列、状态缓存、结果后端 |
| **数据科学** | Pandas + NumPy + SciPy + scikit-learn | 统计检验、矩阵运算、机器学习 |
| **容器** | Docker + Docker Compose | 环境一致性、一键部署、可扩展 |

---

## 截图

> 🚧 应用界面截图待补充，以下为预留位置：

| 页面 | 预览 | 说明 |
|------|------|------|
| 数据上传 | `![Upload](./docs/screenshots/upload.png)` | 支持拖拽上传、格式验证、进度条 |
| 物种分析 | `![Species](./docs/screenshots/species.png)` | 物种组成柱状图、多样性指数、PCoA |
| 功能分析 | `![Function](./docs/screenshots/function.png)` | KEGG / COG 通路富集、热图 |
| 株水平分析 | `![Strain](./docs/screenshots/strain.png)` | 菌株网络、来源追踪 |
| 多组学整合 | `![Multi-omics](./docs/screenshots/multiomics.png)` | 联合分析、相关性网络、桑基图 |

---

## 许可证

[MIT License](LICENSE) © Meta2bAnalyst Contributors

---

## 贡献与反馈

欢迎提交 Issue 和 Pull Request！如有问题或建议，请通过 GitHub Issues 联系。

