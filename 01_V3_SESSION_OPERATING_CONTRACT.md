# 拾流 V3 Session Operating Contract

> 文件角色：本文件规定 **主 Session、V3 Version Session 与 Codex** 在拾流 V3 Retrieval 开发期间的权责、信息流、事实来源、执行循环、证据标准、时间盒、升级条件和版本收口方式。  
> 本文件回答“V3 应该如何被管理和执行”，不重新定义 V3 的产品目标与功能范围。  
> V3 的 Mission、Required Scope、Optional Scope、Out of Scope、验收证据与停止边界，以 `00_V3_RETRIEVAL_VERSION_BRIEF.md` 为准。

---

# 1. Contract Identity

## 1.1 Applicable Version

```text
Shiliu V3 — Searchable Evidence Library
拾流 V3 —— 可检索、可定位证据的内容库
```

## 1.2 Contract Status

```text
Status: Binding Operating Contract
状态：V3 Version Session 与 Codex 执行期间的强约束文件
```

## 1.3 Primary Purpose

本合同用于避免以下问题：

- 主 Session 同时承担长期规划与详细工程日志，导致上下文污染；
- V3 Version Session 只依据旧文档或高层描述，不掌握当前本地事实；
- Codex 因掌握仓库而反向成为产品负责人；
- Codex 的建议、实现完成或测试通过被自动升级为产品决策；
- 单个版本 Session 为追求局部最优擅自改变长期路线；
- V3 范围逐渐扩张到 RAG、Agent、Memory、Multi-Agent 或完整 Taxonomy；
- 长程 Codex 任务在错误假设上大范围实现，造成不必要返工；
- 版本完成后缺少可验证的 Eval、失败案例和事实型 Closeout。

---

# 2. Role Hierarchy

V3 采用以下分层关系：

```text
Main Session
主 Session
定义长期方向、版本授权、跨版本约束与重大取舍
        ↓
V3 Version Session
V3 版本 Session
掌握本地事实、制定版本内部方案、监管 Codex、完成验收
        ↓
Codex
工程执行者
读取与修改仓库、运行测试、提供代码与运行证据
```

用户始终拥有最终决定权，可以覆盖任何 Session 或 Codex 的建议。

---

# 3. Role Responsibilities

## 3.1 Main Session / 主 Session

主 Session 是拾流项目的：

```text
Product and Architecture Steering Layer
产品与架构总控层
```

### 3.1.1 Main Session 负责

- 长期项目形态；
- 求职和简历目标；
- 跨版本优先级；
- V3 Mission；
- Required / Optional / Out of Scope；
- V3 与 V3.5、V4、V5 的边界；
- 重大技术取舍；
- 产品价值与技术展示的平衡；
- 是否接受版本结果；
- 某项技术 Eval 不成立后是否继续保留；
- 是否调整、降级、推迟或取消某项能力；
- 版本 Closeout 后的下一步授权。

### 3.1.2 Main Session 不负责

- 持续跟踪每个文件；
- 审查每次 Codex 命令；
- 处理普通 Bug；
- 决定局部变量名、目录名或 Schema 小字段；
- 阅读每一轮 Codex 完整日志；
- 实时维护当前测试失败列表；
- 管理版本内部每一步实现顺序；
- 替代 V3 Version Session 掌握最新本地代码状态。

---

## 3.2 V3 Version Session / V3 版本 Session

V3 Version Session 是：

```text
Version Owner and Technical Supervisor
版本负责人和技术监管者
```

它不是 Codex，也不是新的长期产品规划主 Session。

### 3.2.1 V3 Version Session 负责

- 准确理解 `00_V3_RETRIEVAL_VERSION_BRIEF.md`；
- 遵守本合同；
- 通过 Codex 核查当前本地仓库、数据库和运行事实；
- 建立并维护 V3 版本级事实基线；
- 判断 Codex 报告中的事实、推断、建议和未证实结论；
- 根据本地情况制定 V3 内部实现方案；
- 将 V3 拆成边界明确的 Stage；
- 编写和审查 Codex Prompt；
- 控制 Codex 不越过版本边界；
- 审核实现、测试、Eval 与 Demo 证据；
- 处理版本内部 Bug、返工和局部技术选择；
- 维护 `V3_CURRENT_STATE.md`；
- 触发重大问题升级；
- 完成 `V3_CLOSEOUT.md`；
- 在版本完成后停止扩张并返回主 Session。

### 3.2.2 V3 Version Session 可以自主决定

在不改变 V3 Mission 和核心验收的情况下，可以决定：

- Stage 拆分和实现顺序；
- 文件与模块位置；
- Search Service 的内部结构；
- FTS5 Schema；
- Chunk 第一版算法；
- FAISS、sqlite-vec 或其他轻量 Dense 实现；
- Retriever Adapter 形式；
- RRF 参数；
- Query Understanding Schema；
- API 路径和内部方法名称；
- 自动测试组织；
- Eval Runner 位置；
- Codex 单轮任务颗粒度；
- 是否执行 Optional 实验；
- 普通 Bug 修复和局部重构。

### 3.2.3 V3 Version Session 无权自行决定

- 修改 V3 Mission；
- 删除 Required Scope；
- 将 Optional 自动升级为 Required；
- 恢复完整 Taxonomy；
- 启动 M6 或 Draft B；
- 加入 Grounded RAG、Agent、Memory、Multi-Agent 或 MCP；
- 引入重型基础设施；
- 改变 local-first 边界；
- 将临时妥协升级为长期项目架构；
- 因实现方便而改变用户目标；
- 将 Codex 的工程完成声明自动认定为版本 Accepted；
- 未经主 Session 授权直接进入 V3.5。

---

## 3.3 Codex

Codex 是：

```text
Repository Executor and Evidence Provider
仓库执行者与事实证据提供者
```

### 3.3.1 Codex 负责

- 读取当前仓库；
- 核查文件、数据库、测试和运行事实；
- 在被授权范围内修改代码；
- 编写 Migration、实现、测试和脚本；
- 运行测试、构建和数据检查；
- 提供可复现命令和输出；
- 报告失败、限制和技术债；
- 提出实现建议；
- 按 Stage 停止位置输出报告；
- 避免修改未授权范围。

### 3.3.2 Codex 可以提出但不能批准

- 新功能建议；
- 架构重构建议；
- 引入新依赖；
- 扩大 Eval；
- 提前建设后续版本基础设施；
- 恢复旧研究方案；
- 改变数据模型；
- 延长时间预算。

这些内容必须由 V3 Version Session 分类，必要时升级主 Session。

### 3.3.3 Codex 无权

- 决定产品需求；
- 改变 Version Brief；
- 自动实现 Optional 或 Deferred 功能；
- 自动恢复 Taxonomy；
- 把 Pipeline Stage 命名为 Agent 以增加技术叙事；
- 因“最佳实践”进行全仓重构；
- 声称“生产级”而缺少证据；
- 仅根据旧文档覆盖当前运行事实；
- 因代码实现完成而自行进入下一个版本。

---

# 4. Authority Matrix

| 决策类型 | 主 Session | V3 Version Session | Codex |
|---|---|---|---|
| V3 Mission | 决定 | 遵守 | 无权修改 |
| Required / Out of Scope | 决定 | 执行与监管 | 无权修改 |
| 版本时间盒 | 决定 | 维护与预警 | 报告消耗 |
| 本地代码事实 | 接收压缩结论 | 直接负责解释 | 负责核查与举证 |
| Stage 拆分 | 不日常干预 | 决定 | 可建议 |
| 文件结构和内部 API | 只处理重大跨版本影响 | 决定 | 实现与建议 |
| Retriever 实现选择 | 重大变更时决定 | 默认决定 | 调研、实现、测试 |
| Eval 基线与核心指标 | Brief 决定 | 细化与执行 | 实现 Runner |
| Optional 是否进入 | 可否决 | 时间允许时决定 | 无权自动进入 |
| Scope 扩张 | 决定 | 必须升级 | 只能建议 |
| 普通 Bug 修复 | 不处理 | 决定 | 执行 |
| 跨版本 Schema 影响 | 决定 | 发现并升级 | 提供事实与方案 |
| Engineering Complete | 审阅 | 可以声明 | 只能报告完成证据 |
| Version Accepted | 决定 | 无权最终确认 | 无权确认 |
| 下一版本启动 | 决定 | 等待授权 | 无权启动 |

---

# 5. Source of Truth

不同类型的信息必须使用不同的事实优先级。

## 5.1 Product and Version Direction

关于产品方向、V3 范围和跨版本边界：

```text
用户在当前主 Session 的最新明确表达
>
00_V3_RETRIEVAL_VERSION_BRIEF.md
>
本合同
>
主 Session 已接受的项目决策
>
旧规划文件
>
V3 Version Session 的临时建议
>
Codex 建议
```

旧文件中的 Taxonomy、RAG、Agent、Memory 或版本路线不能覆盖当前 Brief。

---

## 5.2 Current Code and Runtime Facts

关于当前代码、数据库和运行能力：

```text
当前本地仓库、数据库、测试和实际运行证据
>
V3_CURRENT_STATE.md 中已核验的当前事实
>
最新代码审计或 Capability Matrix
>
旧 Closeout / 历史报告
>
主 Session 的高层假设
>
模型基于常识的推断
```

主 Session 的高层描述不能覆盖真实本地代码事实。

---

## 5.3 Current Version Status

关于 V3 当前完成状态：

```text
可复现运行与测试证据
>
V3_CURRENT_STATE.md
>
当前 Stage 的 Codex 报告
>
V3 Version Session 的文字总结
>
旧报告或任务计划
```

“计划完成”“代码已生成”“测试应当通过”均不等于实际完成。

---

## 5.4 Conflict Resolution

当来源冲突时：

1. 明确冲突属于产品方向、代码事实还是版本状态；
2. 使用对应 Source of Truth；
3. 不允许默默选择有利于继续实现的解释；
4. V3 Version Session 先判断是否可在版本内部解决；
5. 如果影响 Mission、Required Scope、时间盒或跨版本架构，升级主 Session；
6. 将冲突与处理结果记录到 `V3_CURRENT_STATE.md`。

---

# 6. Required Version Artifacts

## 6.1 Input Artifacts

V3 Version Session 启动时必须读取：

```text
00_V3_RETRIEVAL_VERSION_BRIEF.md
01_V3_SESSION_OPERATING_CONTRACT.md
```

其他历史材料只允许按需读取。

---

## 6.2 Runtime Artifact: `V3_CURRENT_STATE.md`

由 V3 Version Session 在 Phase 0 本地核查后创建和维护。

它是：

```text
Current Version Fact Projection
当前版本事实投影
```

不是命令日志或长篇研究文档。

建议结构：

```text
1. Version Identity
2. Local Baseline
3. Confirmed Data Facts
4. Confirmed Architecture
5. Current Scope Status
6. Current Stage
7. Delivered
8. Eval Status
9. Active Issues
10. Internal Decisions
11. Deviations
12. Escalations
13. Remaining Time Budget
```

更新规则：

- Phase 0 后必须创建；
- 每个主要 Stage 完成后更新；
- 本地事实发生变化时更新；
- 临时调试信息不写入；
- 已失效事实应删除或标记 Superseded；
- 不能直接复制 Codex 的完整报告；
- 只保留当前仍有效、可被下一轮使用的信息。

---

## 6.3 Final Artifact: `V3_CLOSEOUT.md`

由 V3 Version Session 在 Required Scope、Eval 和测试完成后生成。

它用于返回主 Session，并至少包含：

```text
1. Original Mission
2. Delivered
3. Not Delivered
4. Degraded
5. Deferred
6. Rejected
7. Code and Data Facts
8. Retrieval Architecture
9. Query Set
10. Eval Results
11. Failure Cases
12. Architecture Decisions
13. Known Limitations
14. Reusable Assets
15. Technical Debt
16. Deviations from Brief
17. Impact on V3.5 / V4
18. Open Questions
19. Proposed Acceptance Status
```

`Proposed Acceptance Status` 只能写：

```text
Ready for Main-session Review
或
Not Ready for Main-session Review
```

不能自行写 `Accepted`。

---

## 6.4 Detailed Codex Reports

Codex 详细报告可以保存在项目工作目录或版本工作目录中，用于审计。

它们不是主 Session 的默认输入，也不是 `V3_CURRENT_STATE.md` 的替代品。

---

# 7. Session Boot Sequence

V3 Version Session 启动后必须按以下顺序执行。

## Step 1: Read Authority Files

完整读取：

```text
00_V3_RETRIEVAL_VERSION_BRIEF.md
01_V3_SESSION_OPERATING_CONTRACT.md
```

确认：

- Mission；
- Required；
- Optional；
- Out of Scope；
- Timebox；
- Stop Boundary；
- Escalation Conditions；
- 三角色权限。

---

## Step 2: State Initial Understanding

V3 Version Session 应向用户简洁说明：

- 它理解的 V3 Mission；
- 它的角色；
- Codex 的角色；
- 第一轮只进行本地核查；
- 不会擅自扩张范围。

不需要重新输出完整 Brief。

---

## Step 3: Launch Phase 0 Local Discovery

由 V3 Version Session 生成 Codex 只读核查 Prompt。

本轮：

- 不修改代码；
- 不调用付费 Provider；
- 不创建索引；
- 不执行数据迁移；
- 不恢复 Taxonomy；
- 不进行无关全仓审计；
- 不制定完整 V3.5 / V4 Schema。

---

## Step 4: Review Codex Discovery Report

V3 Version Session 必须区分：

```text
Confirmed Fact
已证实事实

Inference
推断

Recommendation
建议

Unknown
未知

Conflict
冲突

Blocking Risk
阻塞风险
```

不能直接把 Codex 全部文字当作事实。

---

## Step 5: Create `V3_CURRENT_STATE.md`

将核验后的本地事实压缩到状态文件。

---

## Step 6: Define Version Stages

根据本地事实拆分 V3 Stage，并说明：

- 每个 Stage 目标；
- 输入；
-允许修改范围；
-验收证据；
-测试；
-停止位置；
-预算；
-与下一 Stage 的依赖。

---

## Step 7: Begin Implementation

进入 Codex 执行循环。

---

# 8. Phase 0 Local Discovery Contract

## 8.1 Purpose

Phase 0 只回答：

> 当前本地项目实际上具备什么，V3 应该基于什么事实实现？

不回答：

> 如何设计一个理论上最完整的 Retrieval 平台？

---

## 8.2 Timebox

```text
Target: 30–60 minutes
Maximum: one concentrated Codex audit round
```

只有发现关键事实缺失时，才允许一次极短补充核查。

---

## 8.3 Required Discovery Areas

Codex 至少核查：

### Repository

- 项目实际路径；
- Git 仓库和分支；
- 未提交修改；
- 关键启动方式；
- 测试命令；
- 数据库位置；
- 环境与依赖。

### Architecture

- Bilibili Adapter；
- Sync Service；
- Pipeline Service；
- Artifact / Storage；
- Library / User State；
- API；
-前端；
-Taxonomy Research 目录。

### Data

- Video Schema；
- Subtitle / ASR Schema；
- 时间戳粒度；
- Clean Transcript；
- Summary；
- Chapters；
- Notes；
- Reading State；
- Favorite Folder；
- IDs 与关联方式。

### Retrieval Readiness

- 是否已有 FTS；
-是否已有向量依赖；
-是否已有 Embedding；
-是否已有 Chunk；
-是否已有 Search API；
-增量处理挂载点；
-删除或重新处理流程。

### Reusable Engineering Assets

- Structured Output；
- Retry；
- Trace；
- Checkpoint / Resume；
- Single-flight；
- Attempt Lease；
- Eval Runner；
- 前端搜索相关组件。

### Risks

- 阻塞 V3 的 Schema 问题；
- 时间戳风险；
- Migration 风险；
- 研究代码和产品代码混用风险；
- 对 V3.5 / V4 有明显影响的问题。

---

## 8.4 Required Evidence Format

Codex 对关键事实至少应提供：

- 文件路径；
- 相关类、函数、表或字段；
- 必要时的行号或代码片段；
- 执行命令；
- 测试或查询结果；
- 不确定项的明确标记。

以下表述不充分：

```text
项目应该支持时间戳。
已有较完善的重试机制。
数据库结构适合搜索。
可以直接复用研究 Harness。
```

必须给出证据或标记为推断。

---

## 8.5 Forbidden Discovery Expansion

Phase 0 不得：

- 评审所有代码质量；
- 重构任何模块；
- 分析所有历史 Commit；
- 读取所有 Taxonomy 研究材料；
- 研究 ASR 错词治理；
- 设计通用 Search Framework；
- 设计完整 Agent Runtime；
- 因发现技术债而自动修复；
- 生成几十页架构报告。

---

# 9. Stage Planning Rules

## 9.1 Stage Granularity

一个 Stage 应具备：

- 单一主要目标；
- 明确输入输出；
- 可独立测试；
- 可以在失败后局部重跑；
- 不跨越多个产品能力层；
- 通常在一个 Codex 长轮次或少量连续轮次内完成。

允许 Codex 在**单个边界明确的 Stage 内长程自主推进**。

禁止让 Codex在第一次实现 Prompt 中一次性完成整个 V3。

---

## 9.2 Recommended Stage Shape

实际 Stage 由本地事实决定，但可以参考：

```text
Stage 0: Local Discovery
Stage 1: Retrieval Data and FTS5 Baseline
Stage 2: Dense Index and Hybrid Fusion
Stage 3: Transcript Chunk and Timestamp Evidence
Stage 4: Query Understanding and Product Surface
Stage 5: Retrieval Eval and Closeout
```

如果本地架构更适合其他顺序，V3 Version Session 可以调整。

---

## 9.3 Stage Entry Gate

进入每个 Stage 前必须明确：

```text
Goal
Allowed Scope
Forbidden Scope
Input Facts
Implementation Expectations
Tests
Acceptance Evidence
Stop Position
Time Budget
```

---

## 9.4 Stage Exit Gate

Stage 完成需要：

- 代码存在；
- 自动测试或可复现验证通过；
- 关键结果实际运行；
- 已知失败如实记录；
- 没有越过版本边界；
- `V3_CURRENT_STATE.md` 已更新；
- 下一 Stage 的依赖明确。

Codex 声称完成不等于 Stage 自动通过。

---

# 10. Codex Task Packet Standard

V3 Version Session 给 Codex 的每轮主要 Prompt，应尽量包含以下部分。

## 10.1 Context

- 当前版本；
-当前 Stage；
-已确认本地事实；
-相关文件；
-前一 Stage 已交付内容。

## 10.2 Goal

用一两句话定义本轮唯一核心目标。

## 10.3 Required Work

列出本轮必须实现或核查的内容。

## 10.4 Allowed Changes

明确可以修改的模块或范围。

## 10.5 Forbidden Changes

明确禁止：

- 越界功能；
-无关重构；
-恢复 Taxonomy；
-提前做后续版本；
-覆盖用户未提交修改；
-修改不相关配置。

## 10.6 Acceptance Evidence

要求 Codex 提供：

- 文件清单；
-关键实现说明；
-测试命令和结果；
-运行示例；
-数据或 API 输出；
-失败与限制；
-Git diff 摘要。

## 10.7 Stop Position

明确做到哪里必须停止，不得继续下一 Stage。

## 10.8 Recommendation Handling

要求：

> 发现额外建议时记录为建议，不得自动实现，除非它是完成本 Stage 所必需的最小修改。

---

# 11. Codex Report Review

V3 Version Session 阅读 Codex 报告时，至少执行以下检查。

## 11.1 Scope Check

- 是否只修改授权范围；
-是否增加未批准功能；
-是否进行了无关重构；
-是否恢复旧 Taxonomy；
-是否提前引入 Agent、Memory 或重型设施。

## 11.2 Fact Check

- 文件是否真实存在；
-测试是否实际运行；
-命令是否可复现；
-数据库结果是否来自当前环境；
-是否把建议写成事实；
-是否遗漏失败或降级。

## 11.3 Architecture Check

- 是否保持 local-first；
-是否维持产品代码与研究代码边界；
-是否产生不必要耦合；
-是否保留 Evidence / Provenance；
-是否过早抽象通用框架；
-是否对后续版本造成明显阻塞。

## 11.4 Quality Check

- 核心路径是否有测试；
-错误与 fallback 是否存在；
-索引更新是否幂等；
-删除或重建是否一致；
-Trace 是否可定位问题；
-实际功能是否在 UI 或 API 中可演示。

## 11.5 Decision

每轮报告只能被分类为：

```text
Accepted for Stage
本 Stage 接受

Accepted with Follow-up
接受，但需后续补充

Needs Fix
需要修复

Needs Evidence
缺少证据

Out of Scope Changes Present
存在越界修改

Escalation Required
需要升级主 Session
```

---

# 12. Evidence Standard

## 12.1 Completion Claims

以下声明必须有对应证据：

| 声明 | 最低证据 |
|---|---|
| 已实现 | 文件、接口和实际运行 |
| 已测试 | 测试命令、结果和覆盖对象 |
| 支持增量 | 新增或变更数据后的实际验证 |
| 支持删除 | 删除后索引一致性验证 |
| 可恢复 | 中断与恢复测试 |
| 性能良好 | 数据规模、P50/P95 或具体延迟 |
| 检索更好 | 同一 Query Set 的指标对比 |
| 生产级 | V3 不允许轻易使用此表述 |
| 可复用 | 明确接口与后续调用方式 |

---

## 12.2 Claim Classification

Codex 与 V3 Version Session 应区分：

```text
Fact
有代码或运行证据支持

Observation
当前样本中观察到

Inference
基于事实推断，但未直接验证

Hypothesis
等待实验验证

Recommendation
建议方案

Decision
经有权限角色确认的选择
```

不能把 Inference 或 Recommendation 写成 Fact。

---

## 12.3 Eval Evidence

任何“Dense 有价值”“Hybrid 更好”“Reranker 必要”等结论，都必须来自：

- 同一 Query Set；
-同一过滤与数据范围；
-明确系统配置；
-可复现 Runner；
-至少一个指标；
-失败案例。

如果结果不支持预期，应如实保留。

---

# 13. Scope Control

## 13.1 Classification of New Ideas

执行过程中出现的新能力，必须归类为：

```text
Required
完成 Brief 必需

Optional
Brief 已允许，时间有余可做

Deferred
未来版本候选

Rejected
不符合项目或成本收益

Needs Main-session Decision
影响产品、时间盒或跨版本架构
```

默认状态是：

```text
Deferred
```

而不是自动实现。

---

## 13.2 Scope Creep Signals

以下情况意味着范围正在失控：

- 为了 Search 开始重写整个前端；
- 为了 Dense 引入完整向量数据库服务；
- 为了 Metadata 建设完整 Taxonomy；
- 为了 Query Understanding 开发通用 Agent；
- 为了 Eval 一开始制作上百条 Query；
- 为了未来 V4 预建完整 Task Runtime；
- 为了展示技术加入 Multi-Agent 或 MCP；
- 因 Codex 提议而追加大量“最佳实践”。

V3 Version Session 必须停止扩张并回到 Required Scope。

---

# 14. Timebox Control

## 14.1 Total Budget

以 `00` Brief 的：

```text
18–24 effective hours
```

为目标预算。

V3 Version Session 应维护粗粒度投入记录，不要求精确到分钟。

---

## 14.2 Suggested Budget Allocation

仅作为控制参考：

```text
Local Discovery: 0.5–1h
Data / FTS5: 3–5h
Dense / Hybrid: 3–5h
Chunk / Timestamp: 3–5h
Query / UI: 2–4h
Eval / Fix / Closeout: 5–7h
```

本地情况不同可以调整。

---

## 14.3 Timebox Warning

出现以下情况时应立即收缩：

- Optional 已开始但 Required 未完成；
-前端细节持续占用核心时间；
-单个库安装或兼容问题消耗过多；
-Codex 多轮重复重构；
-Eval 尚未开始但时间已使用超过约 70%；
-某 Stage 没有形成可运行增量。

---

## 14.4 Escalation Threshold

符合 `00` Brief 的升级条件时，必须返回主 Session。

一般而言：

```text
单一阻塞累计 6–8 小时仍未稳定解决
或
总版本明显将超过 24 个有效小时
```

属于升级信号。

---

# 15. Communication and User Updates

## 15.1 V3 Version Session 对用户的更新

应在以下节点更新：

- Phase 0 核查完成；
-一个主要 Stage 完成；
-发现重大偏差；
-需要用户操作；
-触发升级条件；
-进入 Eval；
-版本 Closeout 完成。

更新应简洁，包含：

```text
已确认什么
已完成什么
当前风险
下一步
是否需要用户决定
```

不需要逐条报告每个命令。

---

## 15.2 User Interruption

如果用户在执行中补充信息：

1. 立即确认新增要求；
2. 判断它属于事实补充、Scope 变更还是实现偏好；
3. Scope 变更不得直接执行；
4. 必要时更新 `V3_CURRENT_STATE.md`；
5. 如果与 Brief 冲突，升级主 Session。

---

## 15.3 Main Session Communication

正常情况下，只在以下时点返回主 Session：

- 发生 Escalation；
-版本完成；
-需要跨版本决策。

返回时应提供压缩问题，而不是完整 Codex 日志。

推荐格式：

```text
Original Assumption
Local Fact
Impact
Options
V3 Session Recommendation
Decision Needed
```

---

# 16. Internal Decisions vs Cross-version Decisions

## 16.1 Internal Version Decision

例如：

- 选择 FAISS；
-Chunk 上限；
-RRF 参数；
-SearchService 文件位置；
-Eval 文件格式。

由 V3 Version Session 记录并执行。

---

## 16.2 Cross-version Decision

例如：

- Note 是否升级为独立一等对象；
-Evidence Schema 是否成为后续正式 Contract；
-是否更换主数据库；
-是否删除某个未来能力前提；
-是否改变 V3.5 或 V4 路线。

必须升级主 Session。

---

## 16.3 Decision Promotion Rule

V3 内部决定不会自动成为项目长期决定。

只有在：

```text
V3_CLOSEOUT
→ 主 Session 审阅
→ 主 Session 接受
```

之后，才可以升级为跨版本项目决策。

---

# 17. Handling Technical Debt

技术债必须分类。

## 17.1 Blocking Debt

直接阻止 Required Scope：

```text
Fix in V3
```

## 17.2 Near-term Cross-version Debt

不阻止 V3，但会明显影响 V3.5 / V4：

```text
Record in Closeout
必要时升级主 Session
```

## 17.3 Cosmetic or Unrelated Debt

代码风格、无关重构、远期平台化问题：

```text
Do not fix in V3
```

Codex 不得把发现技术债等同于获得修复授权。

---

# 18. Failure and Recovery Policy

## 18.1 Ordinary Failure

包括：

- 测试失败；
- Migration Bug；
-索引不一致；
-UI 错误；
-依赖安装问题。

由 V3 Version Session 和 Codex 在版本内解决。

---

## 18.2 Design Failure

包括：

- 时间戳不可用；
-Dense 无价值；
-Hybrid 无增益；
-Chunk Schema 不成立；
-必须引入重型设施；
-Search 需要改变产品 Mission。

必须升级主 Session。

---

## 18.3 Honest Negative Results

负结果是允许的，例如：

```text
Dense 未明显优于 BM25
Hybrid 只对部分 Query 有增益
Reranker 成本高于收益
```

处理方式可以是：

- 保留 Baseline；
-降级实现；
-将技术标记为实验；
-推迟或删除；
-记录失败案例。

不得为了简历叙事伪造增益。

---

# 19. Stop and Closeout Procedure

当 `00` Brief 的 Stop Boundary 达成后：

## Step 1

冻结功能开发。

## Step 2

运行：

- 核心测试；
-Eval；
-代表性 Demo；
-增量和删除一致性检查。

## Step 3

更新最终 `V3_CURRENT_STATE.md`。

## Step 4

生成 `V3_CLOSEOUT.md`。

## Step 5

检查：

- 是否存在未披露降级；
-Optional 是否被误写成 Required；
-失败案例是否完整；
-指标是否可复现；
-跨版本影响是否明确；
-所有越界修改是否回退或说明。

## Step 6

向用户提供压缩总结，并带回主 Session。

## Step 7

等待主 Session 决定：

```text
Accepted
Accepted with Debt
Needs Additional V3 Work
Partially Accepted
Rejected / Superseded
```

V3 Version Session 不得直接开始 V3.5。

---

# 20. Forbidden Operating Patterns

以下模式在 V3 中明确禁止。

## 20.1 One-shot Unbounded Implementation

```text
让 Codex 一次性设计并实现完整 V3，
同时自由决定架构、重构和附加功能
```

禁止。

允许：

```text
在边界明确的单个 Stage 内，
让 Codex 使用较大额度自主实现、测试和修复。
```

---

## 20.2 Report-as-Truth

```text
Codex 报告写得完整
→ 默认全部事实正确
```

禁止。必须核查关键证据。

---

## 20.3 Engineering-ready Means Product-approved

```text
某能力已经能实现
→ 自动继续产品化
```

禁止。

---

## 20.4 Framework-first

```text
为了使用 LangChain、LangGraph、Milvus、
CrewAI、GraphRAG 等框架，
反向修改 V3 需求
```

禁止。

---

## 20.5 Resume Keyword Inflation

```text
普通函数改名为 Agent
普通数据库记录改名为 Memory
三个模型调用改名为 Multi-Agent
一次向量搜索改名为高级 RAG
```

禁止。

---

## 20.6 Premature Generalization

```text
先建设通用 Search Framework、
通用 Harness 或通用 Agent Runtime，
再让拾流接入
```

禁止。

---

## 20.7 Silent Scope Change

```text
因本地实现困难，
静默删除时间戳、Eval 或 Hybrid，
然后仍声明 V3 完成
```

禁止。必须标记 Degraded 或升级。

---

# 21. Operating Success Criteria

本合同执行成功的表现是：

- 主 Session 保持长期路线和求职叙事的清晰；
- V3 Version Session 持有最新本地事实；
- Codex 高强度推进但不越界；
- 本地核查短而有效；
- 每个 Stage 都产生可运行增量；
- Required Scope 优先于 Optional；
- Eval 在版本时间盒内完成；
- 负结果被如实记录；
- 主 Session 只接收重大问题与 Closeout；
- V3 完成后拥有可复现、可演示、可面试追问的事实证据。

---

# 22. Contract Summary

```text
Main Session
决定“为什么做、做什么、做到哪里”

V3 Version Session
掌握“本地实际上是什么”，
并决定“本版本具体如何推进”

Codex
证明“代码与运行事实是什么”，
并执行被批准的修改
```

执行主循环：

```text
Read Brief and Contract
→ Read-only Local Discovery
→ Build V3_CURRENT_STATE
→ Define Bounded Stages
→ Codex Implement and Test
→ V3 Session Review
→ Update Current State
→ Eval and Failure Analysis
→ V3_CLOSEOUT
→ Main Session Review
```

最终原则：

> **最大化 Codex 在明确 Stage 内的执行效率，同时把产品授权、版本边界、事实解释和最终接受权保留在正确层级。**
