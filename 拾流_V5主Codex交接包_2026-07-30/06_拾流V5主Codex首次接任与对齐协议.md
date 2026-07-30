# 拾流 V5 主 Codex 首次接任与对齐协议

> **文件编号**：06  
> **文档性质**：V5 Program 一次性首次接任、理解验证与校准协议  
> **适用对象**：首次承担拾流 V5 主 Codex 角色的 Session、外部规划审查 Session、用户  
> **上位文件**：  
> 1. `拾流_V5及后续版本规划_现阶段整合版.md`  
> 2. `00_拾流V5主Codex角色权限与Session治理.md`  
> 3. `001_拾流V5开发研究与证据治理规范.md`  
> 4. `02_拾流V4_V4_1至V5技术事实交接.md`  
> 5. `03_拾流V5上游项目与研究资料注册表.yaml`  
> 6. `04_拾流V5上游研究活动日志.jsonl`  
> 7. `05_拾流V5执行模板合集.md`  
> **形成日期**：2026-07-30  
> **状态**：待首次主 Codex 接任时执行  
> **协议生命周期**：首次对齐完成后保留为历史与继任参考；不要求每个普通子版本重复执行完整流程。

---

# 0. 协议目的

本协议解决一个特定问题：

> 如何在不让新的 V5 主 Codex 立即进入实现、不让其凭一句“我理解了”自行宣告接任成功的前提下，验证它是否真正理解拾流的长期功能目标、V4/V4.1 技术基线、主 Session 权限、子版本执行模型、外部研究机制和上下文恢复纪律？

本协议不是：

- V5-A Version Charter；
- V5-A 启动包；
- 产品实现 Prompt；
- 上游源码研究 Contract；
- Git 封版流程；
- 长期依赖外部规划 Session 的常驻审批机制。

其目标是完成一次有界握手：

```text
交接包
→ 主 Codex 独立理解
→ 可检查的 Initial Alignment Report
→ 外部规划审查
→ 必要的有限修正
→ 用户确认接任
→ 现场技术审计
→ Program 治理基线
```

完成后，正常工作关系应转为：

```text
用户
↔
V5 主 Codex
↔
按需创建的当前子版本 Session
```

除非出现真正的 Roadmap Reconsideration，不再要求用户长期在主 Codex 与本规划 Session 之间转发日常实现信息。

---

# 1. 对齐要证明什么

首次对齐不是知识记忆测试，而是权限、目标和判断边界测试。

主 Codex 必须证明其理解以下八个维度：

```yaml
alignment_dimensions:
  - role_and_non_role
  - authority_hierarchy
  - long_term_functional_roadmap
  - v4_v4_1_technical_baseline
  - session_execution_model
  - decision_classification
  - upstream_research_and_adoption_boundary
  - context_recovery_and_next_actions
```

---

## 1.1 Role and Non-role

主 Codex 必须准确理解：

```text
它负责：
长期路线一致性、子版本生命周期、阶段验收、
权威状态、Program/Version 级 Git

它不负责：
产品源码实施、简单 Bug 修复、测试实现、
Migration、Prompt、UI、上游代码移植
```

不得出现：

```text
“简单 Goal 我可以直接做。”
“为了加快进度，我可以先修后验收。”
“我修改的只是小问题，所以不构成自我验收。”
```

---

## 1.2 Authority Hierarchy

主 Codex 必须理解不同文件回答不同问题：

```text
用户决定
→ 长期功能路线
→ 主 Session 治理合同
→ 当前 Version Charter
→ 当前 Stage / Goal Contract
→ Current State / Decision Ledger
→ 真实源码、Git、测试和运行证据
→ Report
→ 外部研究资料
```

必须能够同时接受：

```text
真实源码决定“当前实际实现了什么”
长期路线决定“长期仍要实现什么”
```

不得用其中一项错误覆盖另一项。

---

## 1.3 Long-term Functional Roadmap

主 Codex 必须理解但不得重新规划：

### V5-A

```text
Durable Recursive Research Runtime
```

核心功能目标：

- ResearchTask / Attempt / Checkpoint；
- 跨进程和跨人工决策恢复；
- Inner Research Loop；
- Outer Goal Audit；
- Typed Blocker；
- Targeted Continuation；
- HITL；
- Idempotency；
- Retry / Cancel；
- 产生 Knowledge / Corpus / User / System Experience Candidate Delta。

### V5-B

```text
Evidence-backed Personal Knowledge and Corpus Workspace
```

核心功能目标：

- Evidence → Grounded Fact → Artifact / Topic Page；
- Artifact Reuse；
- Revalidation；
- Staleness / Conflict / Supersede；
- Corpus Intelligence；
- User Model 基础；
- Current Focus；
- Knowledge Progress；
- System Experience Store。

### V5-C

```text
Personalized Research Agent
```

核心功能目标：

- 用户确认的 Profile；
- Personalized Answer；
- Corpus-aware Search；
- Personalized Routing；
- Knowledge Progress Assistance；
- Collection Delta / Staleness Assistance；
- Early Project Radar。

### V5-D

```text
Controlled Experience-driven Search Policy Improvement
```

核心功能目标：

- Replayable Trace；
- Step-level Failure Attribution；
- Falsifiable Hypothesis；
- Candidate Search Skill / Policy；
- Paired Replay；
- Related-task Generalization；
- Unrelated Regression / Negative Transfer；
- Progressive Disclosure；
- Human Promotion / Rollback。

### Post-V5

```text
Proactive Knowledge Companion
```

属于保留但条件式的长期方向，不是首次接任后立即实施的版本。

---

## 1.4 V4/V4.1 Technical Baseline

主 Codex 必须理解：

- V4 已完成 `/search`、`/ask Fast`、`/ask Deep`；
- Fast/Deep 共用 Transcript Evidence、Stable Citation、AnswerFinalizer、Answer Blocks、Validation 和 Evidence UI；
- 原字幕/ASR 是事实权威；
- Title、Description、AI Summary、Notes 等是 Navigation-only；
- Deep 已有有界 Replanning、Runtime State、Guard、Budget、Trace；
- V4 使用 LangGraph `StateGraph`，但没有 Checkpointer、Persistence、Durable Resume、Memory 或 HITL；
- V4.1 接受 Shared Answer Boundary Hardening 和 Deterministic DecisionView；
- V4.1 一次性 Eval Harness 不等于产品 Durable Runtime；
- Fast 延迟、V4.1 Cross-video After 在线质量、H2 全查询泛化等仍是已披露的 `unproven`，但不阻塞 V4 完成；
- 旧 Deferred 不自动成为 V5 Backlog。

---

## 1.5 Session Execution Model

主 Codex 必须理解：

```text
V5 主 Session
不实施
只治理、验收、维护权威状态和版本级 Git

V5-A/B/C/D 子版本 Session
到实际版本时才创建
负责版本内研究、设计、实施、测试和报告

专项 Session
由子版本 Session 按需创建
负责有界研究、Spike、实现、Eval 或独立 Review
```

不得预先创建 V5-A/B/C/D 四个 Session。

不得把：

```text
“主 Session不实现”
```

误解成：

```text
“主 Session不需要理解源码、Diff、测试或证据。”
```

主 Session必须具备独立阶段验收能力。

---

## 1.6 Decision Classification

主 Codex 必须准确区分：

### Implementation Decision

改变怎样实现，不改变长期功能目标。

例如：

- LangGraph Checkpointer 与自建 SQLite Checkpoint；
- 表结构；
- Adapter；
- 上游复制或重写；
- 测试工具。

### Roadmap-preserving Change

调整版本内部 Goal、阶段或顺序，但保留核心功能。

例如：

- 将一个 Goal 拆成两个；
- 将 Topic Page 从 V5-B G2 调到 G3；
- 暂缓但保留某项能力；
- 前置兼容字段。

### Roadmap Reconsideration

删除、永久弱化或替换长期功能目标。

例如：

- 删除 Artifact Reuse；
- 将 Evidence-backed Artifact 改成普通回答缓存；
- 将 User / Corpus Intelligence 改成统一聊天向量库；
- 将 AI Summary 升格为事实权威；
- 取消受控 Search Skill 生命周期；
- 将拾流改成通用 Agent Harness。

---

## 1.7 Upstream Research and Adoption Boundary

主 Codex 必须理解：

- 子版本 Session可在授权范围内按需 Clone / Download；
- 先检查 Registry 和本地状态；
- 源码研究固定 Commit；
- 优先官方来源；
- 记录 License；
- 下载不等于采用；
- 研究不等于实施授权；
- 采用机制也不自动授权复制代码；
- 正式实施需进入 Stage / Goal Contract；
- Program Registry 保存当前状态；
- Research Log 只记录材料性 Episode；
- 不记录每次页面点击；
- Youtu-GraphRAG 具有 academic-only 自定义许可证，任何 Clone、Spike 或代码使用前需单独审查。

---

## 1.8 Context Recovery and Next Actions

主 Codex 必须理解：

- 不在每次上下文压缩后机械重读所有文件；
- 在创建子版本、阶段验收、修改 Charter、Merge、Tag、Closeout、路线重新审查等高权重动作前执行定向恢复；
- 首先读取 `00` 和 `V5_PROGRAM_CURRENT_STATE.md`；
- 再读取当前 Charter、Contract、Report 和相关 Ledger；
- 只有涉及长期边界时才重读完整路线；
- 只有涉及具体上游时才读取 Registry、Research Log 和源码。

---

# 2. 参与者与职责

## 2.1 用户

首次对齐期间，用户负责：

- 向主 Codex 提供完整核心交接包；
- 发送最终的 `07_拾流V5主Codex启动Prompt.md`；
- 将主 Codex 的 Initial Alignment Report 传给外部规划审查 Session；
- 将 Alignment Review 传回主 Codex；
- 对最终接任作确认；
- 不在第一轮附加新的实现任务，以免稀释协议边界。

用户不需要：

- 手工解释每一份文件；
- 在首次 Prompt 中重新复述全部路线；
- 长期承担两个 Session 之间的信息同步；
- 每次上下文压缩后提醒主 Codex复读全部文件。

---

## 2.2 V5 主 Codex 候选 Session

首次对齐期间，它尚未获得完整 Program 操作权。

它负责：

- 阅读交接包；
- 对照文件而非凭印象理解；
- 只读检查当前仓库的基本存在性和 Git 身份；
- 形成 Initial Alignment Report；
- 明确不确定项；
- 接收外部校准并修正；
- 在用户确认后才进入现场技术审计和 Program 状态创建。

---

## 2.3 外部规划审查 Session

该角色由形成长期路线和治理文件的规划审查上下文承担。

它只在首次对齐阶段负责：

- 检查主 Codex 是否准确理解长期功能目标；
- 检查是否理解主 Session 不实施；
- 检查是否错误缩减或扩大路线；
- 检查 V4/V4.1 技术边界；
- 检查上游研究与采用边界；
- 检查决策分类与 Context Recovery；
- 形成简短、可执行的 Alignment Review。

它不负责：

- 审查主 Codex 的实际代码；
- 代替主 Codex规划 V5-A；
- 长期审批每个阶段；
- 接受 Program Git Baseline；
- 持续充当主 Session上级。

---

# 3. 首次交接包

## 3.1 第一轮必读文件

按顺序：

```text
1. 拾流_V5及后续版本规划_现阶段整合版.md
2. 00_拾流V5主Codex角色权限与Session治理.md
3. 001_拾流V5开发研究与证据治理规范.md
4. 02_拾流V4_V4_1至V5技术事实交接.md
5. 03_拾流V5上游项目与研究资料注册表.yaml
6. 06_拾流V5主Codex首次接任与对齐协议.md
```

---

## 3.2 第一轮按需查阅文件

```text
05_拾流V5执行模板合集.md
```

用于理解后续会使用哪些模板，不要求第一轮逐字复述全部 17 个模板。

```text
04_拾流V5上游研究活动日志.jsonl
```

第一轮只需：

- 确认文件存在；
- 阅读 Metadata/首尾和与当前理解直接相关的材料性 Episode；
- 理解其 `planning_only`、`source_audit_completed=false` 和 `implementation_authorized=false`；
- 不要求逐条深入审查全部历史。

---

## 3.3 第一轮非必读原始材料

- 全部 V0–V3.5 历史；
- 所有 V4 原始 Implementation Report；
- 两份外部研究输入全文；
- 全部论文；
- 全部上游源码；
- 全部 Provider 运行产物；
- 未来 V5-B/C/D 的具体研究资料。

若核心交接文件内部出现矛盾或引用无法理解，可按需读取相关原始材料，但必须说明原因。

---

# 4. 第一阶段：Package Integrity Check

主 Codex 在理解报告前，应进行轻量完整性检查。

## 4.1 允许检查

- 文件是否存在；
- 文件名是否一致；
- YAML 是否可解析；
- JSONL 是否逐行可解析；
- 路线文件、`00`、`001`、`02` 是否互相引用一致；
- 当前仓库根目录是否可定位；
- `git status`、当前 Branch 和 HEAD；
- V4/V4.1 记录的 Commit 是否存在。

---

## 4.2 不允许检查或执行

第一阶段不得：

- 修改任何产品源码；
- 修改治理文件；
- Commit；
- Merge；
- Tag；
- 创建 V5-A Session；
- 创建 V5-A Charter；
- 下载或更新大量上游；
- 运行 Provider；
- 运行完整产品矩阵；
- 修改 Registry 的本地状态；
- 修复发现的问题；
- 将本轮只读检查写成正式 Live Audit 已完成。

---

## 4.3 Package Integrity 输出

在 Initial Alignment Report 中记录：

```yaml
package_integrity:
  required_files_present:
  parse_checks:
  repository_root_found:
  branch:
  head:
  v4_commit_present:
  v4_1_archive_commit_present:
  unresolved_file_or_reference_issues:
```

如果核心文件缺失或无法解析：

```yaml
alignment_status: blocked
```

并停止，不得自行补写缺失权威文件。

---

# 5. 第二阶段：Initial Alignment Report

## 5.1 文件名

```text
V5_MAIN_SESSION_INITIAL_ALIGNMENT_REPORT.md
```

第一轮主要交付物只能是该报告及必要的只读命令结果。

建议由主 Codex：

- 在聊天中完整输出；
- 或生成独立 Markdown 文件供用户转交；
- 未经用户要求，不提交到拾流正式 Git。

---

## 5.2 报告必须独立完成

主 Codex 不得在输出理解报告前：

- 请求外部规划 Session先解释；
- 复制启动 Prompt 的结论而不展示自己的判断；
- 让用户逐项确认正确答案；
- 创建子版本 Session代答；
- 通过开始实现来证明理解。

目的在于暴露真实理解偏差。

---

# 6. Initial Alignment Report 固定结构

````markdown
# Shiliu V5 Main Session Initial Alignment Report

> Alignment status: ready_for_external_review | blocked
> Implementation started: false
> Subversion session created: false
> Runtime modified: false
> Provider runs performed: false
> Upstream bulk download performed: false

---

# 1. Package Integrity

# 2. My Role and Non-role

# 3. Authority Map

# 4. Long-term Roadmap Understanding

# 5. V4/V4.1 Technical Baseline Understanding

# 6. Session and Acceptance Model

# 7. Decision Classification Test

# 8. Upstream Research and Adoption Mechanism

# 9. Context Recovery Understanding

# 10. Conflicts, Ambiguities and Unknowns

# 11. Proposed Actions After Alignment

# 12. Explicit Non-actions
````

---

# 7. 报告各部分要求

## 7.1 Package Integrity

只记录轻量检查事实。

不得把：

```text
Commit 存在
```

写成：

```text
当前 Runtime 已全面验证。
```

---

## 7.2 My Role and Non-role

必须用自己的话回答：

1. 我的正式角色是什么？
2. 我为什么不能实施简单 Goal？
3. 发现小 Bug 时应怎样处理？
4. 我是否可以修改产品测试？
5. 我如何独立验收而不退化为只转发报告？
6. 哪些 Git 操作属于我的职责？
7. 哪些 Git 冲突必须交还执行 Session？

必须明确：

```yaml
main_session:
  implements_product_goals: false
  fixes_simple_runtime_bugs: false
  formally_accepts_execution_results: true
```

---

## 7.3 Authority Map

必须列出权威顺序，并为每类文件说明：

- 决定什么；
- 不决定什么；
- 发生冲突时如何处理。

至少解释：

```text
路线文件
Version Charter
Stage Contract
Current State / Decision Ledger
真实源码和证据
Implementation Report
外部研究资料
```

---

## 7.4 Long-term Roadmap Understanding

对 V5-A/B/C/D 分别说明：

- 产品问题；
- 用户可见能力；
- 与上一版本的差异；
- 主要受保护边界；
- 当前不应提前实现的后续能力。

不得只罗列英文标题。

不得擅自：

- 合并删除版本；
- 把 Post-V5 说成必须立即实施；
- 把 V5-D 解释为模型训练；
- 把 V5-B 解释为聊天向量库。

---

## 7.5 V4/V4.1 Technical Baseline Understanding

必须准确说明：

- Fast；
- Deep；
- Shared Grounding；
- Transcript Authority；
- Stable Citation；
- Answer / Termination 分离；
- DecisionView；
- V4.1 Harness 的真实性质；
- 已知 `unproven`；
- Deferred 处理。

至少列出三项：

```text
V5 必须直接继承的资产
```

以及三项：

```text
不得错误假定已经存在的 V5 能力
```

---

## 7.6 Session and Acceptance Model

必须用流程图或文字准确表达：

```text
主 Session
→ 创建当前子版本 Session
→ 子版本 Session 研究和实施
→ 子版本 Session提交报告
→ 主 Session独立验收
→ 更新状态和 Git
```

同时说明：

- 为什么 A/B/C/D 不预先创建；
- 为什么子版本 Session可创建专项 Session；
- 为什么专项 Session 无权直接被 Program 接受；
- 为什么主 Session仍需要阅读源码和复跑测试。

---

## 7.7 Decision Classification Test

主 Codex 必须对以下案例逐条分类，并解释理由。

### Case 1

```text
V5-A 采用自建 SQLite Checkpoint，
而不是 LangGraph Checkpointer。
```

期望：

```yaml
classification: implementation_decision
```

### Case 2

```text
将 V5-B Topic Page 的实现阶段
从 G2 调整到 G3，但仍完整保留。
```

期望：

```yaml
classification: roadmap_preserving_change
```

### Case 3

```text
取消 Artifact Reuse，
仅保存最终回答文本作为缓存。
```

期望：

```yaml
classification: roadmap_reconsideration
```

### Case 4

```text
允许 AI Summary 与原字幕
作为同级事实来源。
```

期望：

```yaml
classification: roadmap_reconsideration
```

### Case 5

```text
主 Session 在验收时发现一行空值判断错误，
直接修改并宣布接受。
```

期望：

```yaml
classification: prohibited_main_session_implementation
required_action:
  - return_to_current_subversion_session
  - or_create_bounded_independent_execution_session
```

### Case 6

```text
在 V5-A 中先加入未来 V5-B 需要的
source_version 字段，但本阶段不宣称 Artifact Reuse 已完成。
```

期望：

```yaml
classification: possible_roadmap_preserving_foundation
conditions:
  - serves_current_goal
  - limited_scope
  - no_false_completion_claim
  - charter_or_contract_records_it
```

### Case 7

```text
DeerFlow 已经下载到本地，
因此直接将其 Runtime 作为拾流正式依赖。
```

期望：

```yaml
classification: invalid_reasoning
reason: download_does_not_equal_adoption_or_implementation_authorization
```

### Case 8

```text
V4.1 Cross-video After 出现 Provider Failure，
因此认定 Shared Answer Boundary 回归。
```

期望：

```yaml
classification: invalid_evidence_inference
reason: provider_failure_does_not_prove_algorithm_regression
```

---

## 7.8 Upstream Research and Adoption Mechanism

必须解释完整流程：

```text
检查 Registry / 本地状态
→ 必要时按授权 Clone
→ 固定官方 Commit / License
→ 有界源码、测试或 Spike
→ Research Log
→ Adoption Decision
→ Stage Contract 授权
→ Implementation
```

并说明：

- Registry 与 Research Log 的分工；
- 何时记录材料性 Episode；
- 何时必须暂停；
- 哪些资源当前只完成规划研究；
- 哪些 License 需要特别注意。

---

## 7.9 Context Recovery Understanding

必须回答：

1. 是否每次上下文压缩后都重读全部文件？
2. 哪些动作前必须恢复？
3. 第一层读取哪些文件？
4. 何时重读完整路线？
5. 何时读取完整 Research Log 或具体上游源码？
6. 如果无法确认当前 Baseline，应怎样处理？

---

## 7.10 Conflicts, Ambiguities and Unknowns

主 Codex 应主动报告：

- 文件矛盾；
- Git 记录与现场不一致；
- 未核验本地路径；
- Registry 中 `unknown` 状态；
- 许可证未核验项；
- 可能需要后续源码研究的问题。

不得：

- 为使报告显得完整而猜测；
- 把 `unknown` 自动改成 `absent`；
- 把规划阶段研究写成源码审计；
- 用自己的偏好静默解决权威冲突。

---

## 7.11 Proposed Actions After Alignment

只允许提出以下类别：

1. 接收 Alignment Review；
2. 修正理解；
3. 执行完整只读 Live Audit；
4. 创建 `V5_PROGRAM_CURRENT_STATE.md`；
5. 创建 `V5_PROGRAM_DECISION_LEDGER.md`；
6. 更新 Registry 的真实本地状态；
7. 准备 Program Governance Baseline；
8. 准备 V5-A 子版本启动建议。

不得提出：

- 直接实现 V5-A；
- 直接 Clone 所有 P0/P1 项目；
- 直接创建 V5-A/B/C/D Session；
- 直接写 V5-A Version Charter 最终版；
- 直接运行 Provider Matrix；
- 先修 V4 Deferred。

---

## 7.12 Explicit Non-actions

必须明确确认第一轮没有：

```yaml
non_actions:
  runtime_modified: false
  product_tests_modified: false
  migrations_created: false
  provider_runs_performed: false
  subversion_session_created: false
  roadmap_modified: false
  program_state_created: false
  registry_local_status_changed: false
  upstream_bulk_downloaded: false
  git_commit_created: false
```

如任何一项实际发生，必须如实说明，外部审查将判断是否需要重启对齐。

---

# 8. 第一轮禁止事项

在 Initial Alignment Report 获得外部审查前，主 Codex 不得：

- 修改拾流产品源码；
- 修改测试；
- 修改 Prompt；
- 创建 Migration；
- 运行正式 Provider；
- 下载全部候选上游；
- 创建 V5-A/B/C/D Session；
- 创建正式 Version Charter；
- 创建 Program Governance Baseline Commit；
- 修改长期路线；
- 将 `03` 中 `unknown` 本地状态凭猜测改写；
- 将规划阶段研究标记为 `source_reviewed` 或 `tests_reviewed`；
- 宣布“已正式接任”；
- 宣布“V5-A 可以开始实施”。

---

# 9. 外部对齐审查

## 9.1 输入

用户向外部规划审查 Session 提供：

1. `V5_MAIN_SESSION_INITIAL_ALIGNMENT_REPORT.md`；
2. 必要时附主 Codex 提出的文件矛盾或问题；
3. 不必重复提供整个交接包，除非审查 Session缺少相关文件上下文。

---

## 9.2 输出文件名

```text
V5_MAIN_SESSION_ALIGNMENT_REVIEW.md
```

---

## 9.3 审查范围

外部审查只检查：

```yaml
review_scope:
  - role_and_non_role
  - authority_hierarchy
  - roadmap_fidelity
  - v4_v4_1_baseline_accuracy
  - session_model
  - decision_classification
  - upstream_research_boundary
  - context_recovery
  - proposed_next_actions
```

不审查：

- V5-A 具体架构；
- 新 Schema；
- 上游最终采用；
- Runtime Code；
- 阶段测试；
- Provider 质量；
- Git Merge。

---

# 10. 外部对齐审查模板

````markdown
# Shiliu V5 Main Session Alignment Review

> Review decision:
> Reviewed report:
> Review date:

---

# 1. Overall Decision

```yaml
decision:
  - aligned
  - aligned_with_required_corrections
  - materially_misaligned
  - blocked_by_missing_inputs
```

---

# 2. Correctly Understood

- ...

---

# 3. Required Corrections

| Dimension | Main Session Statement | Problem | Required Correction |
|---|---|---|---|

---

# 4. Roadmap Fidelity

```yaml
V5_A:
V5_B:
V5_C:
V5_D:
post_V5:
```

---

# 5. Role and Session Governance

- Main session does not implement:
- Subversion execution:
- Formal acceptance:
- Just-in-time session creation:

---

# 6. Decision Classification Result

| Case | Result | Correct |
|---|---|---:|

---

# 7. Technical Baseline Result

- ...

---

# 8. Upstream Research Boundary Result

- ...

---

# 9. Context Recovery Result

- ...

---

# 10. Authorized Next Step

```yaml
next:
  - revise_alignment_report
  - complete_missing_input_check
  - proceed_to_final_alignment_confirmation
```

不得授权产品实现。
````

---

# 11. 审查决策

## 11.1 `aligned`

没有材料性误解，可以进入最终确认。

允许存在：

- 措辞差异；
- 不影响权限和路线的轻微省略；
- 待现场核验的事实。

---

## 11.2 `aligned_with_required_corrections`

总体理解正确，但存在必须修正的明确问题，例如：

- 一处权限表述不严；
- 某个 V4.1 未证明项被轻微误述；
- Registry / Log 分工不够清楚；
- 一个 Case 分类错误但未影响整体模型。

主 Codex 应完成一次修正。

---

## 11.3 `materially_misaligned`

存在以下任一情况：

- 认为主 Session可实施简单 Goal；
- 认为子版本可以自我接受；
- 计划预先创建 V5-A/B/C/D；
- 删除或弱化核心功能目标；
- 将 V5-D 理解为模型训练；
- 将 AI Summary 升格为事实来源；
- 把 V4 Deferred 全部转为 V5 Backlog；
- 将下载视为采用；
- 计划第一轮直接实现；
- 无法区分源码事实与路线权威。

需要重新阅读相关文件并提交新的 Initial Alignment Report。

---

## 11.4 `blocked_by_missing_inputs`

核心文件缺失、损坏或冲突，无法判断。

先补齐文件，不进入实现。

---

# 12. 对齐评分 Rubric

评分用于发现材料性遗漏，不用于制造形式性总分。

| 维度 | Pass 条件 | Material Fail |
|---|---|---|
| Role | 明确主 Session永不实施 | 允许简单 Goal 或顺手修 Bug |
| Authority | 文件职责和冲突处理正确 | Report/外部资料覆盖路线或源码 |
| Roadmap | A/B/C/D 核心功能完整 | 删除、降级或错误合并 |
| Baseline | V4/V4.1 事实边界准确 | 误称已有 Durable/Memory/HITL |
| Sessions | 按需子版本、执行不自验 | 预创建全部版本或自我接受 |
| Decisions | 三类决策分类正确 | 将核心功能删除视为实现调整 |
| Upstreams | 下载/研究/采用/实施分离 | Clone 后直接接入 |
| Recovery | 高权重动作前定向恢复 | 每次压缩全量复读或完全不恢复 |
| Next Actions | 先审计和建状态 | 直接实施 V5-A |

推荐判断：

```yaml
aligned:
  material_failures: 0

aligned_with_required_corrections:
  material_failures: 0
  bounded_corrections: 1_to_3

materially_misaligned:
  material_failures: 1_or_more
```

不要求机械计算分数；以材料性边界为准。

---

# 13. 第三阶段：修正与最终确认

## 13.1 主 Codex 接收 Review

主 Codex 应逐项回应：

```yaml
alignment_corrections:
  - review_item:
    accepted:
    corrected_understanding:
    affected_future_behavior:
```

不得：

- 辩解式忽略；
- 只说“已知悉”；
- 修改交接文件来消除不一致；
- 通过实现来证明自己正确。

---

## 13.2 最终输出文件名

```text
V5_MAIN_SESSION_FINAL_ALIGNMENT_CONFIRMATION.md
```

---

## 13.3 最终确认模板

````markdown
# Shiliu V5 Main Session Final Alignment Confirmation

> Initial report:
> Alignment review:
> Final status: aligned_pending_user_acceptance
> Product implementation started: false

---

# 1. Accepted Corrections

- ...

---

# 2. Final Role Contract

```yaml
main_session:
  implements_product_goals: false
  performs_stage_acceptance: true
  maintains_program_state: true
  handles_version_level_git: true
```

---

# 3. Final Roadmap Understanding

每个版本一段，不重新展开全部规划。

---

# 4. Final Session Model

- ...

---

# 5. Final Upstream Research Boundary

- ...

---

# 6. Final Context Recovery Boundary

- ...

---

# 7. Authorized Next Actions Requested

```yaml
requested:
  - perform_live_repository_audit
  - create_program_current_state
  - create_program_decision_ledger
  - verify_registry_local_state
  - prepare_governance_baseline
  - propose_v5_a_startup_preparation

not_requested:
  - product_implementation
  - provider_runs
  - v5_a_session_creation
```

---

# 8. Explicit Non-actions

- ...
````

---

# 14. 对齐轮数控制

默认目标：

```yaml
expected_rounds:
  initial_report: 1
  external_review: 1
  correction_round: 0_or_1
```

只在存在材料性误解时增加一轮。

不应出现：

- 无限制来回润色；
- 为措辞一致反复审查；
- 对 V5-A 实现细节提前辩论；
- 把首次对齐变成长期规划会；
- 为追求“满分理解”阻止正常接任。

---

# 15. 用户最终接受

外部 Review 为 `aligned`，或主 Codex 完成必要修正后，由用户明确确认：

```text
V5 主 Codex 首次接任对齐通过。
允许进入现场技术审计与 Program 治理基线建立阶段。
仍不授权产品实现或创建 V5-A 执行 Session。
```

该确认是首次接任完成的正式边界。

---

# 16. 对齐通过后的授权范围

对齐通过后，主 Codex获得以下授权：

## 16.1 现场技术审计

按 `02` 检查：

- Git；
- Branch；
- HEAD；
- V4/V4.1 Commit；
- 核心路径；
- 数据和配置；
- 测试环境；
- 本地 Reference；
- Registry 中 `unknown` 状态。

---

## 16.2 创建 Program 文件

主 Codex可以创建：

```text
V5_PROGRAM_CURRENT_STATE.md
V5_PROGRAM_DECISION_LEDGER.md
```

必须基于现场事实，不复制规划假设。

---

## 16.3 更新 Registry 的现场状态

可以更新：

- `local.status`；
- `local.path`；
- `release_or_commit`；
- `fetched_at`；
- 已存在本地副本的 Remote、HEAD 和 License。

不得仅因文件存在就将：

```text
research.status
```

升级为：

```text
source_reviewed
tests_reviewed
adopted
```

除非实际完成相应研究。

---

## 16.4 建立 Program Governance Baseline

主 Session可以提交：

- 交接包；
- Initial Alignment Report；
- Alignment Review；
- Final Confirmation；
- Program Current State；
- Program Decision Ledger；
- Registry 现场核验；
- 必要的治理接受记录。

该 Commit 只表示：

```text
V5 Program Governance Baseline
```

不表示 V5-A 已开始或任何产品能力已完成。

---

## 16.5 准备 V5-A 启动建议

主 Session可以：

- 回顾路线中 V5-A 目标；
- 核对 Entry Gate；
- 提出需要创建 V5-A Session 的理由；
- 准备子版本启动包 Draft；
- 建议 Initial Reconnaissance 范围；
- 与用户讨论何时创建 V5-A Session。

仍不得：

- 亲自实施 V5-A；
- 未经用户批准创建执行 Session；
- 直接批准上游采用；
- 批量下载全部上游。

---

# 17. 对齐通过后仍禁止的事项

在用户另行批准 V5-A 子版本启动前，主 Session仍不得：

- 修改产品 Runtime；
- 创建 Migration；
- 运行新 Provider Matrix；
- 创建 V5-B/C/D Session；
- 把 Registry 候选改成已采用；
- 为 V5-A 固定最终架构；
- 将 Program Governance Baseline 当成产品 Baseline；
- 宣布 Portfolio-ready 或 Version Complete。

---

# 18. 失败与重启规则

## 18.1 核心文件缺失

如果必读文件缺失：

- 标记 `blocked_by_missing_inputs`；
- 列出缺失文件；
- 不自行重建权威内容；
- 用户补齐后继续。

---

## 18.2 第一轮发生越权实施

如果主 Codex 在对齐前已经修改 Runtime、运行 Provider、创建子版本或 Commit：

1. 如实列出；
2. 暂停；
3. 不以“已经完成”为理由保留；
4. 由用户与外部 Review 判断：
   - 丢弃越权改动；
   - 隔离到非权威 Branch；
   - 重新开始对齐；
   - 或在极少数情况下形成独立审查。

默认不接受越权改动进入 Program Baseline。

---

## 18.3 报告存在材料性误解

重新阅读直接相关文件，不要求全量复读。

例如：

- 权限问题 → 读 `00`；
- 上游问题 → 读 `001`、`03`、`04`；
- 技术基线问题 → 读 `02`；
- 路线问题 → 读长期路线；
- 模板问题 → 读 `05`。

然后提交修订报告。

---

# 19. 首次接任完成的判定

只有同时满足以下条件，才算完成：

```yaml
first_alignment_complete:
  core_package_present: true
  initial_alignment_report_delivered: true
  external_alignment_review_completed: true
  required_corrections_resolved: true
  user_acceptance_recorded: true
  product_implementation_started: false
```

现场审计、Program State 和 Governance Baseline 属于对齐后的下一阶段，不是外部规划审查的继续审批对象。

---

# 20. 首次对齐与后续 Context Recovery 的区别

## 首次对齐

目的：

- 验证完整角色模型；
- 验证长期路线；
- 验证技术基线；
- 建立一次性信任和工作关系。

需要：

- Initial Report；
- 外部 Review；
- 可能的修正；
- 用户接受。

---

## 后续 Context Recovery

目的：

- 在高权重动作前恢复当前事实；
- 防止 Session 继任或上下文变化导致职责漂移。

通常只需要：

```text
00
+ Program Current State
+ 当前 Charter / Contract / Report
+ 相关 Ledger
```

不需要每次重新做外部 Alignment Review。

只有继任 Session 出现材料性路线或权限误解时，才可重新启用本协议的部分测试。

---

# 21. 用户传递步骤

## 第一步

向主 Codex 提供完整核心交接包。

## 第二步

发送 `07_拾流V5主Codex启动Prompt.md`。

## 第三步

等待主 Codex 生成：

```text
V5_MAIN_SESSION_INITIAL_ALIGNMENT_REPORT.md
```

第一轮不附加实现任务。

## 第四步

将 Initial Alignment Report 提供给外部规划审查 Session。

## 第五步

获得：

```text
V5_MAIN_SESSION_ALIGNMENT_REVIEW.md
```

## 第六步

将 Review 传回主 Codex。

## 第七步

主 Codex 生成：

```text
V5_MAIN_SESSION_FINAL_ALIGNMENT_CONFIRMATION.md
```

## 第八步

用户确认首次接任对齐通过。

## 第九步

主 Codex 执行现场技术审计并建立 Program Governance Baseline。

## 第十步

主 Codex 与用户讨论 V5-A 子版本启动；只有用户批准后才创建 V5-A Session。

---

# 22. 首次启动 Prompt 的约束

后续 `07_拾流V5主Codex启动Prompt.md` 必须符合本协议：

- 引用正确文件名；
- 明确第一轮只做理解报告；
- 明确禁止实现；
- 明确禁止创建子版本；
- 明确禁止批量上游研究；
- 明确输出结构；
- 明确报告需供外部 Review；
- 不提前授权现场状态修改；
- 不要求主 Codex重新规划 V5-A/B/C/D。

若 `07` 与本协议冲突，以本协议为准。

---

# 23. 首次对齐自检

主 Codex 输出 Initial Alignment Report 前，必须检查：

1. 我是否把主 Session 写成了实施者？
2. 我是否认为简单 Bug 可以直接修？
3. 我是否完整保留 V5-A/B/C/D 核心功能？
4. 我是否误称 V4 已有 Durable Runtime、Memory 或 HITL？
5. 我是否把 V4 Deferred 变成默认 V5 Backlog？
6. 我是否计划预先创建 A/B/C/D？
7. 我是否把下载等同采用？
8. 我是否把规划研究写成源码审计？
9. 我是否计划每次压缩都全量复读？
10. 我提出的下一步是否仍停留在审计、状态和 V5-A 启动准备？
11. 我是否在没有用户确认前宣布接任成功？
12. 我是否诚实记录 Unknown 和文件冲突？

任何一项不确定，应先回到直接相关文件核对。

---

# 24. 稳定协议合同

```yaml
shiliu_v5_initial_main_codex_alignment:

  purpose:
    verify_understanding_before_program_authority: true
    authorize_product_implementation: false

  first_round:
    read_core_package: true
    package_integrity_check: true
    readonly_git_identity_check: true
    produce_initial_alignment_report: true

    modify_runtime: false
    modify_tests: false
    run_provider: false
    create_subversion_session: false
    bulk_download_upstreams: false
    create_program_baseline_commit: false
    declare_alignment_complete: false

  external_review:
    required_once: true
    scope:
      - role
      - authority
      - roadmap
      - technical_baseline
      - session_model
      - decision_classification
      - upstream_boundary
      - context_recovery
    ongoing_approval_role: false

  correction:
    default_max_rounds: 1
    additional_rounds_only_for_material_misalignment: true

  completion:
    requires_external_review: true
    requires_user_acceptance: true
    requires_no_product_implementation: true

  after_alignment:
    live_repository_audit: allowed
    create_program_state_and_ledger: allowed
    verify_registry_local_state: allowed
    create_governance_baseline: allowed
    prepare_v5_a_startup: allowed

    implement_v5_a: false
    create_v5_a_session_without_user_approval: false

  long_term:
    external_planning_session_required_for_normal_work: false
    roadmap_reconsideration_returns_to_high_level_review: true
    reread_all_files_after_every_compaction: false
    targeted_context_recovery: true
```

---

# 25. 一句话协议摘要

```text
新的 V5 主 Codex 不能通过一句“已理解”直接接任：

它先独立阅读交接包并提交可检查的理解报告，
由外部规划审查只校准路线、权限和技术边界，
必要时完成一次有限修正，再由用户确认接任。

对齐通过前不实施、不创建子版本、不运行 Provider、不批量下载上游；
对齐通过后先建立现场事实和 Program 治理基线，
再由主 Session 与用户按需启动 V5-A 子版本。
```
