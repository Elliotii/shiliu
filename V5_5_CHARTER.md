# Shiliu V5.5 Charter — 产品化与真实使用升级

> Date: 2026-08-13
> Status: GOAL_2_COMPLETE_READY_FOR_GOAL_3
> Version role: bounded productization release
> Initial baseline: `f0c704db88f79794c52b3f4f6e6ac77c320470f2`
> Goal 1 frozen HEAD: `cc707a62f32698d8fc5cbeb36995e0b05736d066`
> Current V5.5 checkpoint / Goal 3 baseline: `09e50bd0f3b4c4a7d86ad90306d766369b4b2572`

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

## 2. 权威基线与当前检查点

V5.5 初始冻结基线：

```text
baseline branch: codex/post-v5-bounded-repair
initial baseline HEAD: f0c704db88f79794c52b3f4f6e6ac77c320470f2
```

V5.5 当前主开发分支：

```text
codex/v5-5-productization
```

已冻结检查点：

```text
Goal 1:
cc707a62f32698d8fc5cbeb36995e0b05736d066

Goal 2:
09e50bd0f3b4c4a7d86ad90306d766369b4b2572
```

Goal 3 必须以 Goal 2 frozen HEAD 为执行基线。

主要参考资料：

- `SHILIU_V5_PROGRAM_FINAL_CLOSEOUT.md`
- `POST_V5_BOUNDED_REPAIR_CLOSEOUT.md`
- `V5_5_GOAL_1_CLOSEOUT.md`
- `V5_5_GOAL_2_CLOSEOUT.md`
- `V5_5_GOAL_3_PRODUCT_SURFACE_AUDIT.md`

Goal 3 启动时，当前提供的本 Charter 作为 V5.5 最新权威 Charter。若仓库中存在旧版同名 Charter，应以当前提供版本为准并同步替换；不得因为旧版状态仍停留在 Goal 2 而阻塞。

后续 Goal 仅按需读取更早文档，不重新加载整个 V5 历史。

---

## 3. V5.5 Goals

### Goal 1 — 可用的长程 Research

**Status: COMPLETE / ACCEPTED / FROZEN**

普通 Web `/research` 已支持服务器授权的 Provider Research，并复用既有 receipt / SideEffect / budget / Deep Search / grounded answer / EvidenceUse / Citation / durable Research / deterministic Outer Audit。

Goal 1 不再继续优化。

---

### Goal 2 — Research → Knowledge → Reuse 知识闭环

**Status: COMPLETE / ACCEPTED / FROZEN**

已完成真实闭环：

```text
Provider Research Result
→ Knowledge Candidate
→ 用户 Review / Publish
→ Fact / Artifact / Topic Page
→ 后续相关但不同 Query
→ ArtifactRoute
→ Direct Reuse
→ current Evidence / raw transcript drilldown
```

Goal 2 未新增模型调用、schema、Knowledge extraction Agent、Router 或后台任务。

Goal 2 不再继续优化。

---

### Goal 3 — 个性化体验与全产品使用流程收口

**Status: AUTHORIZED / NEXT**

正式目标：

> **让用户能够在 Library → Search / Ask → Research → Knowledge → Reuse 的过程中，始终理解自己在哪里、当前结果是什么、下一步可以做什么；同时让 V5-C 已有个性化能力只以真正有用户价值的形式出现。**

Goal 3 是 Product Experience Consolidation（产品体验收口），不是新的底层能力版本。

#### MUST 1 — Research 主视图重新建立用户层级

普通用户默认视图优先：

```text
问题
→ 当前状态 / 最终结果
→ 证据
→ 保存知识
→ 下一步
```

Policy、Workspace authoring、Route internals、Trace、Authority、Receipt、hash、维护操作等不得与主任务竞争，必要内容放入明确的 Advanced / Diagnostics disclosure。

#### MUST 2 — V5-C 产品化

不为每个 V5-C capability 新建独立产品模块。

现有 Focus、Progress、Staleness、Collection Delta、Radar / Assistance、Route Recommendation、Integrated Journey 只在有真实用户价值时出现，并使用用户语言说明：

```text
它是什么
为什么现在有用
用户下一步可以做什么
```

Cold start 不显示大面积 reason code / baseline / hash / empty internal panels；应隐藏无价值区域或给出简洁、可操作的空状态说明。

Goal 3 的成功不要求 Focus / Progress / Delta / Radar 全部同时显示。**隐藏当前没有用户价值的 capability，本身就是合法的产品化结果。**

若现有 V5-C 已有合法的 explicit Current Focus 写入合同，可将通用 WorkspaceRecord authoring 收敛成一个薄的用户动作，例如：

```text
设置当前关注
更新当前关注
```

但不得新增 record type、自动推断 Focus、调用 LLM 生成 Focus、后台修改 Focus 或直接写 DB 制造演示数据。

#### MUST 3 — Knowledge 全局可发现

用户不应记住 originating Research Task 才能找到长期知识。

应复用现有 V5-B Knowledge assets，以轻量产品入口让用户能够重新发现：

```text
已发布 Topic Pages / Knowledge
主题
核心结论
currentness
来源
更新时间
related query / reuse
```

可以新增轻量 `/knowledge` 或当前架构中的等价产品入口。

该入口优先作为既有 Topic Page / Artifact 的**薄 read projection（只读产品投影）**和导航组织，不得为此新建：

- 第二套 aggregate model；
- 新 Knowledge search/index；
- 新 Truth Store；
- 新 Knowledge lifecycle；
- 第二套持久化结构。

#### MUST 4 — 有界 contextual handoff

打通现有能力之间最关键的产品入口：

```text
Library → Search / Ask
Search / Ask → Research（需要进一步研究时）
Knowledge → related query / reuse
```

这些是产品 handoff，不是新 Router 或新的自动执行系统。

Fast → Deep 已解决，不重新实现。

#### SHOULD — 仅在 bounded 范围内完成

- 澄清 Mark 与 Notes 的产品语义和命名，不改变独立数据语义；
- 将 Home raw status 转为用户语言；
- 将 Search 的 corpus-aware / sufficiency 主结果转为用户语言，把 pipeline / trace 放到 Advanced；
- 将 Taxonomy / Corpus Snapshot 实验从普通主导航降级；
- 避免 cold V5-C empty panels 默认占据大面积主视图。

---

## 4. 全版本必须保持的真实性边界

1. 原字幕 / Raw ASR 仍是事实 Citation Authority。
2. Provider answer、Citation、kernel success 不自动授予 `objective_verified=true`。
3. `failure / waiting_user / blocked` 优先于漂亮的成功展示。
4. Branch / Replay 等 durable 创建继续要求明确确认。
5. raw lineage、历史 Artifact、durable records 不因 UX 优化被改写。
6. Provider authority 继续由服务器控制。
7. Knowledge Asset 不能替代 current Evidence / Citation。
8. Research success 不等于自动发布长期知识。
9. V5-C inferred / candidate state 在用户确认前不得升级为事实或自动执行 authority。
10. Goal 3 的产品 handoff 不得变成自动 Router 或后台 Agent。

---

## 5. Goal 3 执行纪律

Goal 3 允许比 G1/G2 更完整地检查真实连续使用体验，但仍采用轻量治理：

```yaml
source_confirmation: bounded
primary_implementation_passes: 1
bounded_correction_passes: 1
independent_reviewer_default: false
real_user_journeys: 3_to_5
new_eval_dataset: false
large_benchmark: false
new_stage_framework: false
```

`primary_implementation_passes: 1` 表示一个连贯的主实现周期，不表示只能修改一次代码、只能创建一个 commit，或不能在同一实现周期内完成必要的小型局部调整。禁止的是多轮重新设计 → reviewer → 重构 → 再实现。

同一问题：

```text
实现
→ 真实 Journey / focused validation
→ 最多一次 bounded correction
→ 仍存在则记录 limitation 并 STOP
```

默认不开 independent reviewer。

仅在 Citation Authority、durable lineage、Provider authority/SideEffect、migration/架构风险出现时才考虑窄审阅。

---

## 6. Goal 3 明确 Non-goals

不得引入：

- Provider latency / availability / quota 优化；
- Multi-source Research quality 扩张；
- 新 semantic completion Judge；
- 自动 required-aspect inference；
- 新 Research architecture / Planner；
- Provider Outer Audit 或第二套 final synthesis；
- 新 Worker / Queue / Scheduler / notification；
- proactive background Research / Radar；
- 新 Memory / Knowledge Graph；
- 新 Router / Agent；
- 新 Eval / Frozen Dataset；
- Retrieval / Embedding / Chunking 大改；
- Fast → Deep runtime reuse；
- Research persistence redesign；
- 新 schema / Knowledge lifecycle redesign；
- Multimodal / Multi-Agent / GraphRAG；
- Self-evolution；
- V6 范围；
- 与已确认问题无关的 broad visual redesign。

若 Goal 3 需要上述任一项才能继续，应停止并返回用户决策。

---

## 7. Goal 3 真实 Journey 验证

优先使用真实现有数据，不为演示制造 synthetic personalization。

建议覆盖 3–5 条连续 Journey：

### Journey A — 从收藏进入查询

```text
Library
→ contextual Search / Ask
→ 必要时 Research
```

验证入口与上下文延续是否自然。

### Journey B — 已有长期知识

```text
Knowledge
→ Topic Page
→ Evidence drilldown
→ related query
→ Reuse / Refresh decision
```

验证 Goal 2 资产是否真正可重新发现和使用。

### Journey C — Personalization cold start

```text
无 Focus / Progress / Delta
→ Research / personalization surface
```

验证页面是否简洁、有意义、没有 reason-code console。

### Journey D — 有一个真实明确 Focus（仅在现有合法 UI 可自然创建时）

```text
Current Focus
→ Assistance / Recommendation / Delta
```

观察是否产生真实用户价值。

不得为了此 Journey 人工灌入虚假记录。

### Journey E — Query escalation

```text
Search / Ask
→ 需要深入
→ Research
```

验证 handoff，不重新验收 G1 Research Runtime。

### 运行环境约束

真实 Journey 使用当前 Goal 3 worktree 的临时服务。

不得：

- 修改常驻 `18520` LaunchAgent；
- 提前把正式服务切到 Goal 3 worktree；
- 修改 scheduled sync 配置。

正式常驻服务切换留给 V5.5 Final Gate。

---

## 8. 测试策略

Goal 3 优先：

```text
focused UI / route tests
+ nearby affected regressions
+ necessary G1/G2 regression subset
+ 3–5 real journeys
```

不默认运行完整 deterministic suite。

完整 suite 留到 V5.5 Final Gate。

---

## 9. Goal Session 模型与文档交付

Goal 3 使用独立新的 Codex Goal-mode Session。

以本 Charter 为版本边界，以 Goal 3 Startup Prompt 为执行合同，并以：

```text
09e50bd0f3b4c4a7d86ad90306d766369b4b2572
```

作为 frozen baseline。

Goal 3 不得回写或重新验收 G1/G2。

完成后创建：

```text
V5_5_GOAL_3_CLOSEOUT.md
```

Goal 3 最终交付 commit 应包含：

- 当前权威 `V5_5_CHARTER.md`；
- `V5_5_GOAL_3_PRODUCT_SURFACE_AUDIT.md`；
- Goal 3 implementation；
- `V5_5_GOAL_3_CLOSEOUT.md`。

前置 Audit 作为事实记录保留，不得为了配合最终结果而回写、美化或重定义其结论。

然后停止，等待用户验收。

---

## 10. V5.5 Final Gate

当 Goal 3 验收完成后，再由用户决定是否直接进入 Final Gate。

Final Gate 默认：

1. 一次完整 deterministic suite；
2. 主要真实产品 Journey smoke；
3. Repair / G1 / G2 / G3 真实性语义回归确认；
4. scheduled sync / Web 基础运行确认；
5. 将常驻服务切到最终 V5.5 accepted HEAD，并验证；
6. `V5_5_FINAL_CLOSEOUT.md`；
7. final branch / immutable HEAD / rollback point。

---

## 11. 当前下一步

```text
V5.5 initial baseline
f0c704db88f79794c52b3f4f6e6ac77c320470f2

↓ Goal 1 COMPLETE / FROZEN
cc707a62f32698d8fc5cbeb36995e0b05736d066

↓ Goal 2 COMPLETE / FROZEN
09e50bd0f3b4c4a7d86ad90306d766369b4b2572

↓ NEXT

Goal 3 — Personalized Product Experience
         & Whole-product Journey Consolidation
```

当前仅授权 Goal 3。

Final Gate 尚未授权。
