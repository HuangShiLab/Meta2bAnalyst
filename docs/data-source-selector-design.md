# 数据源选择器（DataSourceSelector）组件设计 — 步骤 1

> 状态：设计稿，待评审。对应 2026-10 讨论的四步数据层改造的第 1 步。
> 第 2-3 步（UserFile 个人数据库、My Data 页升级）见文末"后续预留"。

## 1. 问题

当前数据进入平台只有两条路：独立 Upload 页（顶层按"流程格式"选择，
基本只覆盖微生物组流程）和各模块自建的零散入口。后果（均为实际发生过的
bug/障碍）：

- **数据类型维度缺失**：代谢组表、菌株表只能从"TSV/CSV"通用入口进，
  file_type 靠文件名关键词猜测（`classifyFile`），猜错即下游拿不到数据
  （菌株文件曾全部落入 `feature_table`）。
- **每页自拼数据链路**：alpha-diversity 曾把 `indices` 放请求顶层被
  pydantic 丢弃；Multi-omics / Multi-site / Upload 三处各写一套上传逻辑。
- **Strain 页没有任何数据入口**，用户必须先知道"去 Upload 页传"。

## 2. UX 设计

### 2.1 组件形态：四来源单选（Tabs / SegmentedControl）

```
┌────────────────────────────────────────────────────────────┐
│ 数据来源                                                     │
│ [当前会话] [现在上传] [示例数据] [我的数据库(二期)]            │
├────────────────────────────────────────────────────────────┤
│ （内容区随选择切换，见下）                                    │
└────────────────────────────────────────────────────────────┘
```

- **当前会话**：列出 session 已有文件（file_type 徽章 + 行数/列数），
  满足 `requires` 即可点"使用当前数据"。空会话时引导切到其它来源。
- **现在上传**：两级选择（见 2.2），上传完成即建好新 session。
- **示例数据**：复用 `loadDemoDataset`（四个数据集卡片），行为不变。
- **我的数据库**：二期挂载个人持久数据集；一期置灰并显示"即将上线"。

### 2.2 上传分页：两级选择 + 显式标注

```
① 这是什么数据？（决定 file_type，显式、不猜）
   [微生物组丰度表] [代谢组丰度表] [菌株丰度表] [功能基因表] [分组元数据]

② 仅微生物组显示：来自哪个流程？
   [2bRAD-M] [QIIME 2/BIOM] [Mothur] [MetaPhlAn] [HUMAnN3] [通用 TSV/CSV]
   （其它类型暂只有通用格式，占位留给厂商格式）

③ 拖拽区：每个文件上传后显示徽章 ●微生物组表 ●代谢组表 ●菌株表 ●元数据…
   ——徽章可点击改判（一期保留，作为兜底而非主路径）
```

- 多组学：①可多选（微生物组+代谢组+元数据），一次拖入建一个会话。
- 元数据自动出现在所有组合中（required 标记由 `requires` 决定）。

### 2.3 模块内嵌位置

模块页面顶部（参数区之上）一个可折叠条："数据：当前会话
[3 个文件 · 查看/更换]"，展开即完整选择器。Strain 页作为首个试点，
补上它缺失的数据入口。

## 3. 组件 API

```tsx
// src/components/data/DataSourceSelector.tsx
export interface FileRequirement {
  type: "microbiome" | "metabolome" | "strain" | "function" | "metadata" | "taxonomy";
  label: string;            // "菌株丰度表（Strain2bScan 输出）"
  required: boolean;
  formats?: string[];       // 提示文案用，如 [".csv", ".tsv"]
}

export interface DataSourceSelectorProps {
  /** 本模块需要什么数据；决定上传分页的默认勾选与校验 */
  requires: FileRequirement[];
  /** 已有会话则传入；组件可能产出新会话 */
  sessionId: string | null;
  /** 数据就绪时回调（新会话或确认现有会话） */
  onSessionReady: (sessionId: string, files: { name: string; type: string }[]) => void;
  /** 紧凑模式：模块内嵌的折叠条 */
  variant?: "panel" | "inline";
}
```

约束：

- **单一实现**：格式校验、两级映射（数据类型 × 流程格式 → file_type）、
  上传进度、会话创建全部收敛在组件内；页面不再各自调用
  `createSession`/`uploadFile`。
- **file_type 由选择器显式给出**，`classifyFile` 文件名猜测仅作默认值
  建议显示在徽章上，用户可改——猜测不再是无提示的静默行为。
- 复用现有设施：`sessionStore`（zustand）、`utils/api.ts` 的
  `createSession`/`uploadFile`、`loadDemoDataset`；后端接口零改动。

## 4. 类型映射表（组件内常量）

| ① 数据类型 | ② 流程格式 | file_type |
|---|---|---|
| 微生物组 | 2bRAD-M / QIIME / Mothur / MetaPhlAn / 通用 | `microbiome`（.biom/.shared 走后端原类型 `biom`/`shared`） |
| 代谢组 | 通用（预留） | `metabolome` |
| 菌株 | Strain2bScan / 通用 | `strain`（Tag2bMap 映射同样归 `strain`） |
| 功能基因 | Tag2bMap / 通用 | `function`（后端如需细分再扩展） |
| 元数据 | — | `metadata` |
| 物种注释 | — | `taxonomy` |

## 5. 试点与迁移顺序

1. **组件实现 + Strain 页试点**（首个交付）：Strain 页获得数据入口，
   验证 `requires: [strain(必须), metadata(必须)]` 的完整链路。
2. **Upload 页换壳**：独立页变为 `requires` 全开放的选择器壳，
   旧六级格式选择下线。
3. **逐模块接入**：Microbiome → Multi-omics → Multi-site → 其余，
   每接一个删一份该页私有的上传代码。

## 6. 二期预留（不在本步实现）

- **我的数据库**：后端新增 `UserFile`/`Dataset` 实体（字节与配额归属），
  会话以引用方式挂载；本组件第四个 Tab 激活，接口形状
  `onSessionReady` 不变（挂载同样产出可用会话）。
- 配额：从"按会话文件累计"改为"按 UserFile 去重计"，500MB 语义不变。

## 7. 验收标准（一期）

- [ ] Strain 页内可完成：选择类型 → 上传 strain+metadata → 会话就绪 →
      直接运行菌株分析，全程不离开页面；
- [ ] 上传的每个文件在 UI 上有可见、可改的 file_type 徽章；
- [ ] 示例数据四个数据集行为与现状一致；
- [ ] Upload 页换壳后原有六种流程格式的老用户路径有等价入口；
- [ ] `classifyFile` 猜测仅作为徽章初值，任何文件都可手动改判。
