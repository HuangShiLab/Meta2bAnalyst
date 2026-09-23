# 用 AI 客户端驱动 Meta2bAnalyst（MCP 学生指南）

Meta2bAnalyst 除了网页界面，还提供标准 **MCP（Model Context Protocol）**接口。
接入后，你可以在 Kimi 桌面、Claude Code 等 AI 客户端里**用自然语言直接完成整套分析**：
加载数据 → 选分组 → 跑 PCoA / 差异分析 / 多组学整合 → 查知识库解读结果。

> 背后理念参考 Paper2Agent（Miao et al., Nature 2026）：分析平台不再只是网页，
> 而是一个可以被 AI 调用的"活性"工具集。

---

## 1. 服务器地址

向老师确认主机 IP（记为 `<HOST>`），MCP 端点为：

```
http://<HOST>:8080/mcp/
```

本机测试则为 `http://localhost:8080/mcp/`。

## 2. 客户端配置

### Kimi 桌面

在 MCP 插件配置中添加一个 HTTP 类型的 server：

```json
{
  "mcpServers": {
    "meta2banalyst": {
      "type": "http",
      "url": "http://<HOST>:8080/mcp/"
    }
  }
}
```

保存后新开会话，确认工具列表里出现 `run_analysis`、`load_demo_dataset` 等 12 个工具。

### Claude Code

```bash
claude mcp add --transport http meta2banalyst http://<HOST>:8080/mcp/
claude mcp list   # 确认连接成功
```

### Codex / 其它 MCP 客户端

同理，选择 **HTTP transport**，填入上面的 URL 即可。

---

## 3. 三个上手示例

直接用自然语言提问即可，Agent 会自动调用对应工具。

**示例 1：加载演示数据并看群落结构**

> 加载 microbiome 演示数据集，按 Visit 分组做 Bray-Curtis PCoA，告诉我前两个轴解释多少变异、各时间点的分离趋势。

**示例 2：差异分析**

> 用刚才的会话，比较 T1 和 T9 两个时间点（Wilcoxon，BH 校正），列出最显著的 10 个菌属，并说明 Fold change 的方向是怎么定义的。

**示例 3：知识库解读**

> 这些显著菌属在知识库里有什么已知功能和疾病关联？相关结论来自哪些文献（PMID）？

**示例 4（多组学）：**

> 加载 multi-omics 演示数据集，做 Mantel test 看菌群和代谢组的整体一致性，再做 genus–metabolite Spearman 相关，报告显著相关的数量。

---

## 4. 分析自己的数据

1. 让 Agent `create_session` 建会话；
2. 把本地 feature table 和 metadata 文件内容交给 Agent `upload_file`（它会 base64 编码上传）；
3. 先用 `get_metadata_columns` 确认分组列名，再 `run_analysis`。

文件要求与网页版一致：**feature table 和 metadata 的样品 ID 必须一致**；多组学每个组学各传一个 feature table；多部位每个部位一对文件。

## 5. 可用工具一览

| 工具 | 作用 |
|---|---|
| `load_demo_dataset` | 加载内置演示数据（microbiome / metabolome / multi-omics / multi-site-multi-omics） |
| `create_session` / `upload_file` / `list_sessions` / `list_session_files` | 会话与数据管理 |
| `get_metadata_columns` | 查看 metadata 列（选 group_column 前必查） |
| `list_analysis_modules` | 查看全部 56 个分析模块及参数 |
| `run_analysis` | 运行分析（pcoa、differential、permanova、metabolomics、cross-omics、mofa、multisite-* 等 34 类） |
| `get_job_status` | 查询大任务进度 |
| `search_knowledge_base` | 查菌的功能与疾病关联 |
| `list_paper_cards` / `get_paper_card` | 查知识库里每篇文献（PMID）贡献的关联证据 |

## 6. 结果解读注意事项

- 结果里带 `engine` 字段：`R::ALDEx2` 等表示 R 参考实现；`python::*` 且 `is_approximation=true` 表示 Python 近似实现；`external-mcp::*` 表示外部服务器结果。**近似/外部结果不能直接当作对应方法的原版结果引用。**
- `functional-prediction`（PICRUSt2）目前默认拒绝运行（缺 KO 参考库），这是有意为之。
- 图的原始数据以大结果形式返回时会被截断（默认前 100 行），完整图表请到网页版对应会话查看。
