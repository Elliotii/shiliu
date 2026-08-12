# Shiliu V5.5 Charter — 产品化与真实使用升级

> Date: 2026-08-13  
> Status: READY_FOR_GOAL_1  
> Version role: bounded productization release  
> Baseline: `f0c704db88f79794c52b3f4f6e6ac77c320470f2`

---

## 1. 版本定位

V5.5 不重新设计拾流，也不继续扩张 V5 的技术版图。

它承接 V5-A / V5-B / V5-C 已经完成的 Research Runtime、长期知识工作区和个性化辅助能力，以及 Post-V5 真实使用后完成的可靠性修复，目标是解决一个明确问题：

> **把已经存在的工程能力，变成用户真正能理解、能完成任务、能持续使用的产品流程。**

因此 V5.5 的优先级是：

```text
产品可用性 > 新能力数量
真实用户闭环 > 工程展示面
复用已有能力 > 新建架构
少量真实验证 > 大型 Eval / 重复审阅
```

---

## 2. 权威基线

V5.5 从以下冻结基线开始：

```text
baseline branch: codex/post-v5-bounded-repair
baseline HEAD:   f0c704db88f79794c52b3f4f6e6ac77c320470f2
```

建议 V5.5 主开发分支：

```text
codex/v5-5-productization
```

V5.5 不回写或重定义已经验收的 V5-A / B / C 历史结论，也不修改 Post-V5 Repair 已修复的真实性与安全语义。

主要参考资料：

- `SHILIU_V5_PROGRAM_FINAL_CLOSEOUT.md`
- `POST_V5_BOUNDED_REPAIR_CLOSEOUT.md`
- `V5_5_GOAL_1_READ_ONLY_SOURCE_AUDIT.md`

后续 Goal 仅在确有需要时按需读取更早的 Stage 文档，不预加载整个 V5 历史。

---

## 3. V5.5 Goals

### Goal 1 — 可用的长程 Research

目标：

> 将 V5-A 已存在的 receipt-bound Provider Research 能力，以最小、服务器控制的产品接入方式接入普通 Web Research，使用户能够真正完成一次有证据的研究任务。

核心成功体验：

```text
用户提出研究问题
→ 系统进行与问题复杂度相称的搜索与取证
→ 产生 grounded research result
→ 展示来源 / Citation
→ 明确说明当前结果、停止原因和下一步
```

本 Goal 是 **product integration（产品接入）**，不是 Research 架构重写。

必须优先复用现有：

- Durable Research Task / Attempt / Checkpoint；
- receipt-bound Provider dispatch；
- Deep Search；
- grounded answer / EvidenceUse / Citation；
- Provider budget / deadline / cost / SideEffect 语义；
- deterministic Outer Audit；
- 当前 product projection 与 durable control。

不得把“运行更久”“循环更多”本身作为 Research 成功标准。

---

### Goal 2 — Research → Knowledge → Reuse 知识闭环

目标：

> 让 V5-B 已实现的 Fact / Artifact / Topic Page、修正、过期、冲突、复用和增量刷新能力，在真实用户流程中形成至少一个自然、可理解、可重复使用的完整闭环。

目标闭环：

```text
完成一次有证据的 Research
→ 形成可理解的 Knowledge Candidate
→ 用户 Review / Publish
→ 形成长期知识资产
→ 后续相似问题命中已有资产
→ Direct Reuse / Refresh / Conflict / Research Seed
→ 可以下钻到原始字幕 / ASR 证据
```

本 Goal 不新建 Memory 系统；重点是让已经存在的长期知识机制真正产生并服务于真实资产。

---

### Goal 3 — 个性化产品表面与产品语言收口（条件性）

目标：

> 把 V5-C 已实现的关注状态、知识进度、收藏库辅助搜索、过期/新增内容提示和下一步建议，以普通用户能够理解的方式组织出来，并统一清理主要页面的工程化 / AI 味文案。

重点回答：

```text
系统目前知道什么？
我最近关注什么？
哪些结果已经存在？
哪些可能过期或冲突？
新增收藏与当前关注有什么关系？
下一步适合 Search / Deep / Research / Reuse 哪一条？
```

主界面优先使用用户任务语言；内部术语、Trace、Receipt、Route、Audit 等仅在确有需要的 Advanced / Diagnostics 区域出现。

Goal 3 为条件性 Goal：若 Goal 1 / Goal 2 已自然解决大部分产品表达问题，可进一步缩小；不得为了“完成版本规划”强行扩大实现。

---

## 4. 全版本必须保持的产品真实性边界

以下原则在 V5.5 中继续有效：

1. **原字幕 / Raw ASR 仍是事实 Citation Authority。** Metadata、Corpus Model、个性化状态和历史 Artifact 不能替代原始证据。
2. **Provider 生成结果不等于用户目标已验证完成。** `objective_verified` 只能由已注册、具有权威的目标验证逻辑授予。
3. kernel success、Provider answer、Citation 数量与用户级任务完成必须继续区分。
4. `failure / waiting_user / blocked` 等真实执行状态优先于漂亮的成功展示。
5. Branch / Replay 等会创建 durable state 的操作继续要求明确确认。
6. 已有 raw lineage、历史 Artifact 和 durable records 不因产品展示优化而被改写。
7. Provider 权限必须由服务器控制，客户端不能自行授予底层执行 authority。

---

## 5. 统一执行纪律

V5.5 明确采用轻量执行治理，不沿用重型版本审查流程。

每个 Goal 默认：

```yaml
source_audit: bounded_and_goal_specific
primary_implementation_passes: 1
bounded_correction_passes: 1
independent_reviewer_default: false
natural_real_use_cases: 2_to_3
new_eval_dataset: false
large_benchmark: false
new_stage_framework: false
```

### 修正循环上限

同一个问题默认只允许：

```text
第一次实现
→ focused validation / real use
→ 最多一次 bounded correction
→ 仍存在问题则记录 limitation 并 STOP
```

不得因为“还可以更严谨”不断进行 retry → review → refactor → rerun。

### Reviewer 触发条件

默认不开 independent reviewer。仅在出现以下实质风险时考虑一次只读或窄范围审阅：

- Citation Authority 可能被改变；
- durable data / lineage 可能被破坏；
- Provider side effect / receipt / authority 出现安全风险；
- 必须引入 migration 或明显跨架构修改。

UI、文案、普通回答质量和轻量产品摩擦本身不是独立 Reviewer 的触发条件。

### 测试策略

每个 Goal 优先：

```text
focused tests
+ nearby affected regressions
+ 2–3 个自然真实 Case
```

完整 deterministic suite 默认只在 V5.5 最终 Gate 运行一次；若某 Goal 实际修改了公共核心代码，可在 Closeout 中说明为什么提前运行一次。

---

## 6. 明确 Non-goals

除非出现无法继续的真实阻塞并由用户重新授权，V5.5 不做：

- 新 Research 架构 / 新 Planner；
- Provider Outer Audit；
- 第二套 final synthesis；
- 新 Worker / Queue / Redis / Celery 等后台平台；
- Retrieval / Embedding / Chunking 大改；
- 新 Memory 架构或 Knowledge Graph；
- 新 Router 平台；
- 新大型 Eval / Frozen Dataset；
- Multimodal / Multi-Agent / GraphRAG；
- 新 Self-evolution / Skill Promotion 系统；
- 主动后台 Agent / 通知系统；
- V6 范围扩张。

若某 Goal 需要依赖以上任一项才能继续，应停止并返回用户决策，而不是自行扩大 Scope。

---

## 7. Goal Session 模型

每个核心 Goal 使用独立的新 Codex Session 执行，优先使用 Goal mode。

Goal Session：

- 以本 Charter 为版本边界；
- 以该 Goal 的启动 Prompt 为执行合同；
- 读取与本 Goal 直接相关的源码和证据；
- 不重新规划整个 V5.5；
- 不自动开始下一个 Goal。

每个 Goal 完成后仅输出简洁 Closeout，至少包含：

```text
实现了什么
真实 Case 发生了什么
测试结果
仍有哪些 limitation
checkpoint / HEAD
是否建议进入下一个 Goal
```

后续 Goal 是否启动，由用户在验收后决定。

---

## 8. V5.5 Final Gate

当计划执行的 Goals 完成后，V5.5 只做一次最终收口：

1. 运行一次完整 deterministic suite；
2. 确认主要真实用户闭环仍可工作；
3. 确认 Post-V5 Repair 已修复的真实性语义没有回归；
4. 确认 scheduled sync / Web 基础运行未被破坏；
5. 形成一个 `V5_5_FINAL_CLOSEOUT.md`；
6. 记录最终 branch / HEAD / rollback point。

V5.5 成功不要求实现所有长期愿景。它的成功标准是：

> **V5 已经完成的核心工程能力，至少在 Research、长期知识复用和主要产品表面上，能够被真实用户自然理解并完成任务。**

---

## 9. 当前下一步

```text
V5.5 baseline frozen
→ create / enter codex/v5-5-productization
→ start a fresh Goal-mode Session
→ execute Goal 1 — 可用的长程 Research
→ user acceptance
→ decide Goal 2
```

当前只授权准备并启动 Goal 1；本 Charter 本身不构成后续 Goal 的自动实施授权。
