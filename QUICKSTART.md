# Meta2bAnalyst — 试用指南（Docker）

面向**本地单人试用**：每位测试者在自己机器上跑一个容器，只访问 `localhost`。

> ⚠️ **本版本没有任何身份验证。**
> `GET /api/v1/sessions` 会列出该服务器上的**全部** session，`DELETE /api/v1/sessions/{id}`
> 会连同磁盘文件一起删除。因此 compose 只把端口绑在 `127.0.0.1`。
> **不要把它暴露到局域网或公网**——需要多人共享时必须先加鉴权。

---

## 1. 前置条件

- Docker Desktop（或 Docker Engine）+ Docker Compose v2
- 磁盘约 **8 GB**（镜像含 R 与 Bioconductor，约 4–5 GB）
- 首次构建约 **30–60 分钟**（R 包从源码编译）。之后启动是秒级。

## 2. 启动

```bash
git clone https://github.com/HuangShiLab/meta2banalyst.git
cd meta2banalyst
docker compose -f docker/docker-compose.yml up --build
```

构建完成后打开 **<http://localhost:8080>**（API 文档在 <http://localhost:8000/docs>）。

停止：`Ctrl-C`；彻底清掉数据：

```bash
docker compose -f docker/docker-compose.yml down -v
```

## 3. 用自带的示例数据走一遍

仓库根目录里有 Huang mBio 2021 口腔数据（261 样本 × 44 属 + 1125 代谢物）：

| 文件 | 上传时选的类型 |
|---|---|
| `Huang_mBio_metadata.tsv` | `metadata` |
| `Huang_mBio_microbiome.tsv` | `feature_table` |
| `Huang_mBio_metabolome.tsv` | `metabolome` |

**请先传 metadata**：特征表的方向（样本在行还是在列）是靠 metadata 的样本 ID 判定的。这份数据是"样本在行"，上传后应显示 **261 samples / 44 features**；如果显示 44 samples 就说明方向判错了，请报 bug。

可用的分组变量：`Visit`（7 个时间点）、`Plaque`（2 个位点）、`Subject`（24 人）。

## 4. 一条命令自检

容器内置了全流程冒烟测试，覆盖 63 条流水线：

```bash
docker compose -f docker/docker-compose.yml exec backend python scripts/pipeline_smoke.py
```

退出码 = 失败条数。这是判断"环境是否正常"最快的方式。

## 5. 试用时请特别留意这些行为（都是有意为之）

| 现象 | 原因 |
|---|---|
| 差异分析对 7 个 `Visit` 返回 **400**，要求指定 `comparisons` | 不再默认"取前两组"静默比较。请显式传 `"comparisons": ["T4","T9"]` |
| UniFrac / PICRUSt2 返回 **400** | 这两个实现分别基于**模拟的系统发育树**和**源码内置的假 KO 库**，不是真方法，已默认停用 |
| 某些方法返回 `is_approximation: true` | 该结果来自 Python 近似而非原始 R 包，**不可以按原方法名报告** |
| 结果里有 `engine` 字段 | `R::DESeq2` 表示真的跑了 R 包；`python-approx::*` 表示是近似 |
| 用 `jaccard` 做 enterotype 报错 | 该数据每个样本都含全部菌属，Jaccard 距离全为 0；请用 `braycurtis` |

本镜像内置了 R，所以 **DESeq2 / edgeR / ANCOM-BC / ALDEx2 / WGCNA / mixOmics 是真实执行**的（可在结果的 `engine` 字段确认）。

## 6. Agent 功能的当前限制

Agent（`/agent` 页面）可以规划并执行分析，但请注意：

- 生成的论文段落里凡是 `[方括号]` 的字段都是**平台无法知道的实验事实**，必须自己填；伦理声明不会自动生成。
- 知识库只有 60 个菌种且**偏肠道**，对口腔数据命中率低。

## 7. 报 bug 时请附上

```bash
docker compose -f docker/docker-compose.yml logs backend --tail 200 > backend.log
docker compose -f docker/docker-compose.yml exec backend python scripts/pipeline_smoke.py --json smoke.json
```

连同 `backend.log`、`smoke.json`、以及触发问题的请求体一起提交。

---

## 附：不用 Docker 的本地开发方式

```bash
# 后端
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload           # http://localhost:8000

# 前端（需 Node >= 20.19）
cd frontend && npm ci && npm run dev    # http://localhost:5173
```

这种方式**不装 R**，因此 DESeq2 等方法会返回 400 说明未安装——这是预期行为，不是 bug。
