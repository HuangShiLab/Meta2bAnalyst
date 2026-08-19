# MacStudio 文献下载与挖掘一条龙管线

目标：在 HKU 内网 MacStudio 上持续扩充口腔微生物组文献库，并把挖掘结果回流到
Meta2bAnalyst 的知识库（KB）。

## 0. 一次性准备

```bash
# 两个仓库并排放在同一目录下（路径任意，脚本已参数化，不依赖固定位置）
cd ~/work
git clone git@github.com:HuangShiLab/meta2banalyst.git
# collector 建议同样 git 化后 clone（见文末「collector git 化」）；在此之前先整目录拷贝
cp -R <U盘或共享盘>/oral-microbiome-data-collector ~/work/

cd meta2banalyst
docker compose -f docker/docker-compose.yml up -d   # 后端 + worker（冒烟 63/63 已通过）

# 挖掘用 LLM 密钥（写入 backend/.env，或运行挖掘时注入）
echo 'KIMI_API_KEY=sk-kimi-...' >> backend/.env
```

约定下文环境变量：

```bash
export COLLECTOR_HOME=~/work/oral-microbiome-data-collector   # collector 根目录
export M2B=~/work/meta2banalyst                               # 主产品根目录
```

## 1. 增量搜索（新主题/新文献 → 待下载清单）

```bash
cd $COLLECTOR_HOME
# 搜索所有 enabled 主题（config/themes.json 控制开关与关键词）
python3 scripts/incremental_search.py
# 或只跑一个主题、限定近年
python3 scripts/incremental_search.py --theme oral-gut-axis --start-year 2023
```

产物：`data/pending_download_<theme>.json`
（与历史 catalog 和 `papers/pdfs/PMID*.pdf` 按 PMID/DOI 自动去重，只含新增）。

## 2. 全文下载

```bash
# 2a. 开放获取（OA）优先：Europe PMC / PMC / Unpaywall
python3 scripts/download_oa_fulltext.py --max 50

# 2b. 付费墙文献：HKU Library 批量下载（需先确认登录方式，见文末问题）
python3 scripts/batch_hku_download.py
```

PDF 统一落到 `$COLLECTOR_HOME/papers/pdfs/PMID<id>_<标题>.pdf`。

## 3. LLM 挖掘（PDF → KB 候选条目）

复用主产品的挖掘脚本（在 meta2banalyst 仓库内）：

```bash
cd $M2B/backend
env -u KIMI_BASE_URL venv/bin/python3 scripts/literature_mine.py \
  --pdf-dir $COLLECTOR_HOME/papers/pdfs \
  --out-dir knowledge_staging \
  --limit 12 --sleep 3.0
```

产物：`knowledge_staging/papers/<pmid>.json`（物种 × 疾病 × 方向 × 证据句）。
`--limit 0` 全量；小批量续跑可防止 LLM 配额中断导致大量返工。

## 4. 增量合并进 KB

```bash
cd $M2B/backend
venv/bin/python3 scripts/merge_staging_kb.py            # 先 dry-run 看差异
venv/bin/python3 scripts/merge_staging_kb.py --apply    # 确认后写入
git add . && git commit -m "kb: merge literature mining batch" && git push
```

合并器按 pmid+direction 去重，可重复执行（幂等）。

## 5. 定时化（可选）

launchd 或 cron 每周增量一轮（避开整点/半点）：

```cron
# 每周一 07:13：增量搜索 + OA 下载
13 7 * * 1  cd $COLLECTOR_HOME && python3 scripts/incremental_search.py && python3 scripts/download_oa_fulltext.py --max 50 >> data/cron_weekly.log 2>&1
```

挖掘建议保持人工触发或 Kimi Work 定时任务（需要 LLM 配额管理）。

## 待确认事项

1. **HKU Library 认证方式**：`batch_hku_download.py` 需要校园网/图书馆会话。
   待确认：cookie 复用 / EZproxy 前缀 / 浏览器手动登录一次后导出会话。
2. **collector git 化**：当前 collector 只在本地目录。建议新建私有仓库
   `HuangShiLab/oral-microbiome-data-collector`（PDF 与 data/ 大文件用 .gitignore
   排除或走 Git LFS / 共享盘），这样 MacStudio 一条 `git clone` 即可开跑。
