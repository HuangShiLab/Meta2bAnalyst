# Paper2Agent × Meta2bAnalyst 集成评估

论文: Miao J, Davis JR, Zhang Y, Pritchard JK, Zou J. *Reimagining research papers as interactive and reliable AI agents.* Nature, 2026-09-16. doi:10.1038/s41586-026-11044-y (arXiv:2509.06917)
代码: https://github.com/jmiao24/Paper2Agent (3.3k stars)

## 1. Paper2Agent 做了什么

多智能体系统，把"论文 + 代码仓库"自动转换成两样东西：

1. **Paper Skill**(paper2skill)—— 论文知识(正文、附图、方法细节)整理成 agent 可读的 SKILL.md
2. **Paper MCP Server**(paper2mcp)—— 把论文代码包装成 MCP 工具，三层结构：
   - **Tools**: 原子分析函数(绑定到仓库真实代码)
   - **Resources**: 论文内容、数据文件
   - **Prompts/Workflows**: 论文 tutorial 级别的多步流程

关键机制：coordinator agent 并行调度 specialist agents 生成工具，再由**全新 verifier agents 迭代生成测试、运行、修复**，直到 MCP 稳定。100 篇计算生物学论文基准上 91.2% 准确率；AlphaGenome agent 复现率 98.7%(对比直接给 Claude 仓库访问 82.7%)。

产物 ZIP 可连到任何 MCP 客户端(Claude Code / Codex / Gemini CLI),或用 HuggingFace 托管的远程 MCP。

## 2. 与 Meta2bAnalyst 架构的对照

| Paper2Agent 概念 | Meta2bAnalyst 对应物 | 现状 |
|---|---|---|
| MCP Tools(原子分析) | `agent/module_registry.py` 的 56 个 ModuleSpec → `analysis.py` REST 端点 | ✅ 已有，且刚通过全量冒烟 |
| 自然语言调用 | `agent/planner.py`(关键词/模板匹配 + LLM) | ✅ 已有，但匹配能力弱 |
| 多步 workflow prompts | DAG 工作流编辑器 + `workflows.py` | ✅ 已有 |
| 论文知识 Resources | 文献挖掘管线(PDF→LLM→taxon-disease KB) | ✅ 已有(形式不同) |
| MCP 标准接口 | **无** | ❌ 缺口 |
| 自动测试-修复循环 | 手写冒烟脚本 | ⚠️ 半自动 |

结论：**两边架构高度同构**。Paper2Agent 的输出物(MCP server)正是 Meta2bAnalyst 缺的标准化接口层。

## 3. 三个可行的集成方向

### 方向 A:把 Meta2bAnalyst 暴露为 MCP server(推荐，收益最大)

用 `fastmcp` 把现有 56 个分析端点包装成 MCP tools——我们的 REST API 已经是"session + 参数 → 结构化结果"的干净契约，包装层很薄。

收益：
- 学生/合作者可从 Claude Code、Kimi 桌面等任何 MCP 客户端直接驱动 Meta2bAnalyst
- 这恰好是 Nature 论文验证过的分发范式——我们自己就是那个"paper agent"
- 与现有 Agent 页面并存，不动前端

工作量：**约 2–3 天**。含 session 管理工具(create/upload)、分析工具封装、结果返回(plot_data 是 base64/JSON,需注意 MCP 传输大小)、Bearer token 鉴权(复用方案 A 的用户体系)。

### 方向 B:Meta2bAnalyst 作为 MCP client,接入第三方 paper agents

让 planner/executor 能调用外部 MCP server。立即可用的场景：
- **PICRUSt2**: 我们因缺 KO 参考库暂时禁用；HuggingFace 上若有功能预测类 MCP server 可直接接上
- AlphaGenome / Scanpy 等已托管的 MCP

工作量：**约 3–5 天**(executor 增加 MCP 调用通道 + planner 学会外部工具路由)。风险：外部 MCP 质量参差，需谨慎挑选白名单。

### 方向 C:借用 paper2skill 工作流强化我们的文献挖掘

我们的 KB 管线产出结构化 taxon-disease 证据；paper2skill 产出的是"论文知识卡"。可为每篇纳入 KB 的文献同时生成一份 skill 摘要，挂在证据条目上供 Agent 回答"这个方法怎么做"类问题。优先级低，属于增强而非补缺。

## 4. 建议

**先做方向 A**。理由：架构已就绪、工作量最小、直接响应"让学生/外部用户用自然语言串流程"的目标，且发表叙事上 Meta2bAnalyst 本身就是"可被 agent 化的平台"。方向 B 可作为二期，优先接功能预测(PICRUSt2 替代)。

验证方式(借鉴论文的 verifier 思路):给每个 MCP tool 自动生成 1–2 个冒烟调用(用 sample_data),CI 里跑——我们刚建好的冒烟脚本可以直接改造成这个 verification loop。
