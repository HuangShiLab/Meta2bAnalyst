# 贡献指南

感谢您考虑为 Meta2bAnalyst 做出贡献！无论是修复 Bug、添加新功能、改进文档，还是提供使用反馈，您的参与都将帮助这个项目变得更好。

---

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
  - [报告 Bug](#报告-bug)
  - [提出功能建议](#提出功能建议)
  - [改进文档](#改进文档)
  - [提交代码](#提交代码)
- [开发环境搭建](#开发环境搭建)
- [代码规范](#代码规范)
- [Pull Request 流程](#pull-request-流程)
- [版本发布流程](#版本发布流程)
- [社区](#社区)

---

## 行为准则

本项目遵循 [Contributor Covenant](https://www.contributor-covenant.org/) 行为准则。参与本项目即表示您同意遵守以下准则：

- 使用友善和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

---

## 如何贡献

### 报告 Bug

如果您发现了 Bug，请通过 [GitHub Issues](https://github.com/your-org/meta2banalyst/issues) 提交报告。一个好的 Bug 报告应该包含：

1. **问题描述**：简洁清晰地描述问题
2. **复现步骤**：详细的操作步骤，让开发者能够复现问题
3. **期望行为**：描述您期望发生什么
4. **实际行为**：描述实际发生了什么
5. **环境信息**：
   - 操作系统及版本
   - 浏览器及版本（前端问题）
   - Python 版本（后端问题）
   - Docker 版本（部署问题）
6. **截图/日志**：如果有错误提示，请提供截图或后端日志

**Bug 报告模板：**

```markdown
## 问题描述
[简要描述问题]

## 复现步骤
1. 打开 ...
2. 点击 ...
3. 选择 ...
4. 出现错误

## 期望行为
[描述期望发生的行为]

## 实际行为
[描述实际发生的行为]

## 环境信息
- OS: [e.g. macOS 14.0]
- Browser: [e.g. Chrome 120.0]
- Python: [e.g. 3.11.4]
- Docker: [e.g. 24.0.7]

## 附加信息
[截图、日志、错误信息等]
```

### 提出功能建议

如果您有功能改进建议，欢迎提交 Feature Request：

1. 先搜索 [GitHub Issues](https://github.com/your-org/meta2banalyst/issues)，确认该功能未被建议过
2. 使用 `enhancement` 标签创建新 Issue
3. 描述功能的使用场景和预期效果
4. 如果可能，提供示例 UI 或 API 设计

### 改进文档

文档是项目的重要组成部分。如果您发现文档有错误、不清晰或缺失，可以通过以下方式改进：

- 直接在文档页面点击"编辑"链接（如果支持）
- 提交 Pull Request 修改 `docs/` 目录下的 Markdown 文件
- 提交 Issue 描述文档问题

文档改进的 Pull Request 通常会被优先合并。

### 提交代码

#### 工作流程

1. **Fork 仓库**：点击 GitHub 页面右上角的 Fork 按钮
2. **克隆仓库**：
   ```bash
   git clone https://github.com/your-username/meta2banalyst.git
   cd meta2banalyst
   ```
3. **添加上游仓库**：
   ```bash
   git remote add upstream https://github.com/your-org/meta2banalyst.git
   ```
4. **创建功能分支**：
   ```bash
   git checkout -b feature/your-feature-name
   # 或修复分支
   git checkout -b fix/bug-description
   ```
5. **编写代码**：遵循代码规范，编写测试
6. **提交更改**：
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```
7. **同步上游**：
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```
8. **推送分支**：
   ```bash
   git push origin feature/your-feature-name
   ```
9. **创建 Pull Request**：在 GitHub 上创建 PR，描述更改内容

---

## 开发环境搭建

### 方式 1：使用开发脚本（推荐）

```bash
# 克隆仓库
git clone https://github.com/your-org/meta2banalyst.git
cd meta2banalyst

# 启动开发环境（Redis + 后端 + 前端）
bash docker/dev.sh
```

开发环境将启动：
- Redis 缓存服务（端口 6379）
- FastAPI 后端（端口 8000，热重载）
- Vite 前端（端口 5173，热重载）

### 方式 2：手动搭建

**步骤 1：启动 Redis**
```bash
docker run -d --name meta2b-redis -p 6379:6379 redis:7-alpine
```

**步骤 2：启动后端**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**步骤 3：启动前端（新终端）**
```bash
cd frontend
npm install
npm run dev
```

### 使用 Makefile

项目提供了常用命令的 Makefile：

```bash
make dev       # 启动开发环境
make stop      # 停止开发服务
make test      # 运行后端测试
make build     # 构建 Docker 镜像
make up        # 生产环境启动（Docker）
make down      # 生产环境停止
make logs      # 查看 Docker 日志
make clean     # 清理 Docker 容器与镜像
```

---

## 代码规范

### 提交信息规范（Conventional Commits）

所有提交信息必须遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型（type）：**

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: add alpha diversity calculation` |
| `fix` | Bug 修复 | `fix: resolve sample name mismatch issue` |
| `docs` | 文档修改 | `docs: update API guide for filter endpoint` |
| `style` | 代码格式（不影响功能） | `style: fix indentation in analysis.py` |
| `refactor` | 重构（既不修复 bug 也不添加功能） | `refactor: extract data validation logic` |
| `perf` | 性能优化 | `perf: optimize BIOM parsing speed` |
| `test` | 测试相关 | `test: add unit tests for filter module` |
| `chore` | 构建/工具/依赖更新 | `chore: upgrade FastAPI to 0.104` |
| `ci` | CI/CD 相关 | `ci: add GitHub Actions workflow` |

**作用域（scope）：**

- `frontend`：前端相关更改
- `backend`：后端相关更改
- `api`：API 接口更改
- `analysis`：分析模块更改
- `docs`：文档更改
- `docker`：Docker 配置更改
- `deps`：依赖更新

**示例：**

```bash
git commit -m "feat(backend): add DESeq2 differential analysis support"
git commit -m "fix(frontend): resolve plot rendering issue in Safari"
git commit -m "docs: update user manual for strain-level analysis"
git commit -m "refactor(api): simplify session management logic"
```

### Python 代码规范

后端代码遵循 [PEP 8](https://pep8.org/) 规范，并使用以下工具：

- **格式化**：Black (`black backend/`)
- **类型检查**：mypy (`mypy backend/app/`)
- **代码检查**：flake8 (`flake8 backend/`)
- **导入排序**：isort (`isort backend/`)

```bash
# 后端代码提交前检查
cd backend
black app/ scripts/ tests/
isort app/ scripts/ tests/
flake8 app/ scripts/ tests/
mypy app/
pytest
```

**关键规范：**

- 使用类型注解（Type Hints），特别是函数参数和返回值
- 函数文档字符串使用 Google Style 或 NumPy Style
- 模块和类命名遵循 PEP 8
- 字符串使用双引号，除非字符串内部包含双引号
- 行长度限制 100 字符

**示例：**

```python
from typing import List, Dict, Optional
from fastapi import HTTPException

async def calculate_alpha_diversity(
    feature_table: pd.DataFrame,
    metadata: pd.DataFrame,
    metrics: List[str],
    grouping: str,
    test_method: str = "wilcoxon",
) -> Dict[str, any]:
    """Calculate alpha diversity metrics and compare between groups.

    Args:
        feature_table: Feature abundance table (features × samples).
        metadata: Sample metadata table (samples × variables).
        metrics: List of diversity metrics to calculate.
            Options: "shannon", "simpson", "chao1", "ace", "observed", "pielou".
        grouping: Name of the grouping variable in metadata.
        test_method: Statistical test method for group comparison.
            Options: "ttest", "wilcoxon", "anova", "kruskal".

    Returns:
        Dictionary containing diversity values, statistics, and plot data.

    Raises:
        HTTPException: If grouping variable is not found in metadata.
        ValueException: If any group has fewer than 3 samples.
    """
    if grouping not in metadata.columns:
        raise HTTPException(status_code=400, detail=f"Grouping variable '{grouping}' not found")
    
    # ... implementation
```

### TypeScript/React 代码规范

前端代码遵循以下规范：

- **格式化**：Prettier（配置在 `.prettierrc` 中）
- **代码检查**：ESLint（配置在 `.eslintrc` 中）
- **类型检查**：TypeScript 严格模式

```bash
# 前端代码提交前检查
cd frontend
npm run lint
npm run type-check
npm run build
```

**关键规范：**

- 使用 TypeScript 严格类型，避免 `any`
- 组件使用函数式组件 + Hooks
- 组件命名使用 PascalCase（如 `AlphaDiversityPlot`）
- 工具函数命名使用 camelCase（如 `calculateShannon`）
- 常量命名使用 UPPER_SNAKE_CASE（如 `MAX_UPLOAD_SIZE`）
- 优先使用 `const` 和 `let`，避免 `var`
- 使用 `async/await` 处理异步操作，避免回调地狱

**示例：**

```typescript
import React, { useState, useEffect } from "react";
import { useSession } from "@/hooks/useSession";
import { AlphaDiversityResult } from "@/types/analysis";

interface AlphaDiversityPanelProps {
  sessionId: string;
  onResult: (result: AlphaDiversityResult) => void;
}

export const AlphaDiversityPanel: React.FC<AlphaDiversityPanelProps> = ({
  sessionId,
  onResult,
}) => {
  const [metrics, setMetrics] = useState<string[]>(["shannon", "simpson"]);
  const [grouping, setGrouping] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const { runAnalysis } = useSession(sessionId);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const result = await runAnalysis("alpha-diversity", {
        metrics,
        grouping,
      });
      onResult(result);
    } catch (error) {
      console.error("Analysis failed:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* ... JSX */}
    </div>
  );
};
```

### 测试规范

#### 后端测试

- 使用 `pytest` 框架
- 测试文件命名：`test_*.py` 或 `*_test.py`
- 测试函数命名：`test_feature_description`
- 使用 `pytest-asyncio` 测试异步函数
- 使用 `pytest.fixture` 共享测试数据

```bash
# 运行所有测试
cd backend
pytest

# 运行特定测试文件
pytest tests/test_analysis.py

# 运行特定测试函数
pytest tests/test_analysis.py::test_alpha_diversity_calculation

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

#### 前端测试

- 使用 `vitest` 框架（Vite 内置）
- 使用 `@testing-library/react` 测试组件
- 测试文件命名：`.test.tsx` 或 `.spec.tsx`

```bash
# 运行所有测试
cd frontend
npm run test

# 运行特定测试文件
npm run test -- src/components/AlphaDiversityPanel.test.tsx

# 生成覆盖率报告
npm run test -- --coverage
```

---

## Pull Request 流程

### 创建 PR 前的检查清单

提交 Pull Request 前，请确认以下事项：

- [ ] 代码已遵循项目代码规范（Black、ESLint、类型检查通过）
- [ ] 新功能已编写测试，且所有测试通过
- [ ] 文档已更新（README、用户手册、API 指南等）
- [ ] 提交信息遵循 Conventional Commits 规范
- [ ] 分支已同步到最新上游代码
- [ ] 代码通过本地测试，无类型错误
- [ ] UI 更改已截图并在 PR 描述中展示
- [ ] API 更改已在 API 文档中更新

### PR 描述模板

```markdown
## 描述
[简要描述本次更改的内容和目的]

## 更改类型
- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档更新
- [ ] 性能优化
- [ ] 代码重构
- [ ] 其他：

## 关联 Issue
Closes #123
Relates to #456

## 测试
- [ ] 已添加单元测试
- [ ] 已手动测试关键功能
- [ ] 已测试边界情况

## 检查清单
- [ ] 代码已格式化
- [ ] 类型检查通过
- [ ] 测试全部通过
- [ ] 文档已更新

## 截图（如有 UI 更改）
[在此处插入截图]
```

### 代码审查

所有 Pull Request 都需要至少一名维护者的审查。审查者将检查：

- 代码逻辑正确性
- 测试覆盖度
- 代码规范遵循情况
- 文档完整性
- 性能影响

### 合并策略

项目采用 **Squash and Merge** 策略合并 PR。这意味着：

- 您 PR 中的所有提交将被合并为一个提交
- 请确保 PR 标题清晰描述更改内容
- 提交信息将被整理为最终提交信息

---

## 版本发布流程

项目采用 [Semantic Versioning](https://semver.org/)（语义化版本）规范：

- `MAJOR.MINOR.PATCH`
- `MAJOR`：不兼容的 API 更改
- `MINOR`：向后兼容的功能添加
- `PATCH`：向后兼容的问题修复

### 发布步骤

1. 维护者在 `main` 分支上创建版本标签
2. 生成 CHANGELOG（基于提交历史）
3. 构建 Docker 镜像并推送到 Registry
4. 创建 GitHub Release，包含 CHANGELOG 和安装说明

---

## 社区

### 沟通渠道

- **GitHub Issues**: Bug 报告和功能建议
- **GitHub Discussions**: 使用问答、经验分享
- **GitHub Discussions - Ideas**: 新功能讨论
- **GitHub Discussions - Show and Tell**: 分享使用 Meta2bAnalyst 的研究成果

### 贡献者荣誉

所有贡献者将在项目 README 的 **Contributors** 部分获得致谢。显著的贡献者（如核心功能开发、重要文档编写）将被邀请加入维护团队。

---

再次感谢您的贡献！如果您有任何疑问，请随时通过 GitHub Issues 或 Discussions 联系我们。

> 本贡献指南最后更新于 2024 年。如有建议或改进，欢迎提交 PR 修改本文件。
