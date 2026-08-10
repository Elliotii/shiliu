# 拾流 V5-C Stage 1 Contract

```yaml
stage: V5-C Stage 1
title: Confirmed Personalized Answer Presentation
contract_status: proposed_pending_v5_main_acceptance
proposal_authority: V5-C Version Session
acceptance_authority: V5 Main Session
created_at: 2026-08-09
execution_branch: codex/v5-c
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
schema_source_at_contract: 14
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
live_database_migration_authorized: false
self_acceptance: forbidden
```

> 本 Contract 在 V5 Main 明确接受并授权前不允许产品实施。它冻结行为、权威、测试和复杂度边界，
> 不冻结内部函数名；任何实现报告都只能请求 Main 验收，不能宣布 Stage accepted。

## 1. Stage 使命

以一个最短、无 Provider、用户可见的纵切证明：结构化反馈只会形成 Candidate，只有用户明确输入或
确认过的 versioned preference 才能改变 Research answer 的一个低风险展示行为；用户能看见使用了
哪条记录并能单次关闭、持久关闭、修正或恢复旧值，同时答案与证据权威完全不变。

```text
Exact-target Feedback Event(s) ──→ behavioral Candidate ──→ user confirm ─┐
Explicit Preference ──────────────────────────────────────────────────────┤
Explicit Current Focus ───────────────────────────────────────────────────┤
                                                                          ↓
                            versioned PersonalizationContext projection
                                                                          ↓
Research answer blocks + limitations ──→ confirmed presentation treatment + explanation
                                                                          ↓
                              off / correct / expire / tombstone / rollback
```

Stage 1 不是完整 Personalized Answer、Corpus-aware Search 或 Router；它先证明最危险的 authority
跃迁不会发生，并建立后续 Stage 可复用的 paired baseline 纪律。

## 2. 用户可见结果

在现有 Research task workspace 中，用户应能：

1. 创建明确 preference 和 Current Focus，看到 record kind、authority、status、version 和 history；
2. 在 Topic Page/ArtifactRoute feedback 中可选一个严格枚举的 structured preference hint；
3. 只有至少两个 compatible、distinct、same-task exact-target Feedback Events 时，才可显式创建
   `inferred_candidate`；系统不自动创建、不自动确认；
4. 对 Candidate confirm/correct/reject/expire/tombstone，所有动作追加 immutable revision；
5. 在 Research answer 看到 `Personalization` explanation，说明 applied/baseline、preference revision、
   Current Focus revision、effect scope 和 fallback reason；
6. 已确认 `answer.presentation.limitations_position=before_answer` 时，把现有 limitations panel 显示在
   answer blocks 之前；`after_answer` 保持当前默认位置；
7. 使用当次 `Personalization off` 立即回到当前 baseline，不写数据库；
8. 持久 tombstone/expire 后回 baseline；correct 或“恢复旧值”创建新 revision，不复活旧 revision；
9. 重启、重复命令和 fault 后得到同一有效投影，不产生双份 authority 或半应用效果。

## 3. 冻结行为边界

### 3.1 唯一 effect key

```yaml
semantic_key: answer.presentation.limitations_position
allowed_values:
  - before_answer
  - after_answer
default_without_confirmed_record: after_answer
effect_scope: research_answer_presentation_only
```

`after_answer` 必须保持当前 Research answer/limitations 的内容与顺序 baseline；允许新增严格分离的
personalization explanation/control metadata。`before_answer` 只移动现有 limitations container；不得修改：

- answer block 文本、顺序或 status；
- citation IDs、citation card、EvidenceIdentity/currentness、limitations 内容；
- retrieval query、candidate、open lane、Fact/Artifact/Page/Route；
- Research Task/Attempt/Checkpoint/Result、termination 或 budget；
- Prompt、模型、Provider、ASR/Translation；
- Fast/Deep Ask、Product Search 或其他页面。

Current Focus 在 Stage 1 只出现在 explanation chip/details，不能影响答案、搜索、route 或 budget。

沿用现有 Workspace payload，不发明第二套 Profile schema：

| kind | canonical Stage 1 encoding |
| --- | --- |
| explicit preference | `semantic_key=<exact key>`；`payload={"key":<exact key>,"value":<allowed value>}` |
| inferred candidate | `semantic_key=<exact key>`；`payload={"statement":<allowed value>}` |
| current focus | `semantic_key=<topic>`；`payload={"topic":<topic>,"state":<state>}` |

projection decoder 必须同时校验 kind、semantic key、payload shape/value、authority 和 effective status；
不能只凭其中一个字段生效。

### 3.2 Effective authority

仅下列记录可进入 treatment：

| Record | 必要条件 | Stage 1 effect |
| --- | --- | --- |
| explicit preference | `explicit_memory`, exact key/value, `user_authored`, effective `current` | allowed |
| confirmed candidate | `inferred_candidate`, exact key/value, `user_confirmed`, effective `confirmed` | allowed |
| current focus | `focus_state`, user-authored/current 或 user-confirmed/confirmed | explanation only |

以下必须 baseline：candidate/unconfirmed、rejected、expired、tombstoned、invalidated、superseded、
behavioral candidate、corpus soft prior、progress/system experience、unknown semantic key、unknown value、
malformed payload、conflicting equal-head records、source boundary mismatch、projection error。

若存在多条合法历史，使用现有 Workspace effective-head/revision 语义确定唯一 current head；不能按
confidence、最近一次点击、自由文本相似度或模型推断偷偷覆盖确认态。冲突无法机械消解时 fail closed。

## 4. PersonalizationContext 投影

Stage 1 可增加一个窄的 read-only projection adapter，但不得增加新 authority store。最低输出：

```json
{
  "policy_version": "v5-c-stage1-personalization-context-v1",
  "enabled": true,
  "applied": true,
  "effect_scope": "research_answer_presentation_only",
  "preference": {
    "semantic_key": "answer.presentation.limitations_position",
    "value": "before_answer",
    "record_id": "...",
    "record_revision_id": "...",
    "version": 2,
    "content_hash": "...",
    "authority_class": "user_confirmed"
  },
  "current_focus": {
    "record_id": "...",
    "record_revision_id": "...",
    "version": 1,
    "topic": "...",
    "state": "..."
  },
  "reason_codes": ["confirmed_preference_applied"],
  "context_hash": "server-owned deterministic hash"
}
```

Baseline 也必须返回可解释 reason，例如 `no_confirmed_preference`、`personalization_disabled`、
`candidate_not_confirmed`、`record_expired`、`unrelated_key_ignored`、`conflict_fail_closed`。Response 不得
暴露自由形成的心理推断；只描述可审计记录与 deterministic rule。

`context_hash` 必须覆盖 policy version、effect scope、selected revision/content hash、focus revision 和
enabled flag，用于测试/诊断，不成为数据库 identity、Citation 或 Profile authority。

## 5. Structured Feedback → Candidate

### 5.1 Feedback contract extension

可在现有 `SubmitKnowledgeFeedbackRequest` 增加一个 optional、strict、extra-forbid 对象：

```json
{
  "candidate_preference": {
    "semantic_key": "answer.presentation.limitations_position",
    "proposed_value": "before_answer"
  }
}
```

它必须继续绑定当前 exact immutable TopicPageRevision content hash 或 ArtifactRoute authority hash，
继续写 existing `v5b_product_feedback_recorded` Event + CommandReceipt，`advisory_only=true`、
`automatic=false`。没有该对象的 V5-B Feedback 行为和 payload compatibility 不变。

### 5.2 Candidate gate

使用现有 Workspace create endpoint 创建 `inferred_candidate` 时，server 必须对 source refs 重新验证：

- 至少两个 distinct `v5b_product_feedback_recorded` Events；
- 同 `command_task_id`，每个 Event 的原 target/hash 仍可验证；
- 两个 Event 的 structured semantic key/value 完全一致；
- candidate payload 只接受 exact key/value，不从自由文本 `note` 做 NLP/LLM inference；
- source boundary hash 覆盖 Event identities/hashes；
- duplicate command 幂等，payload mismatch 拒绝，fault 不留孤儿 revision/receipt。

满足这些条件也只生成 `behavioral_candidate/candidate`。必须由用户通过现有 decision endpoint
`confirm` 后，新的 revision 才成为 `user_confirmed/confirmed`。Feedback、UI 聚合或 Candidate 创建均
不得直接修改 Prompt/Router/Skill/Workspace 其他 confirmed record。

Stage 1 UI 可以从 existing closeout feedback projection 提供“创建 Candidate”按钮；不得后台扫描、
定时聚合或静默创建。

## 6. Current Focus、修正、关闭与 rollback

### Current Focus

- 明确输入无 source refs 时继续是 user-authored/confirmed；
- 从行为推导时必须保留 candidate 语义和至少两个 sources；
- Stage 1 只展示 focus topic/state/version，不改事实内容；
- unknown/expired/conflicting focus 省略并说明 reason。

### 单次 Disable

UI 当次 toggle 只传递/应用 `enabled=false` 的 read projection，不写 Workspace/Event/Receipt；结果必须
与 no-profile `after_answer` baseline 等价。重新打开后重新读取 current confirmed revision。

### 持久 Disable

使用现有 tombstone 或 expire decision 追加 revision；从该 revision 生效后立即 baseline。不得 physical
delete 或修改旧 revision。

### Correct

使用 existing `correct` + expected version，replacement payload 必须通过 exact key/value validation；
新 revision supersede 旧 head，历史可见。

### Rollback

“恢复旧值”是读取用户指定的历史 payload 后，以 `correct` 追加一个新版本并记录
`reason=restore_previous_value`；不是把旧 revision 设回 current，不删除中间版本。rollback 之后
explanation 必须指向新 revision，并可下钻被恢复的历史版本。

### No resurrection

rejected/expired/tombstoned old boundary 不能因相同 Event replay 复活；新证据只有带新的 source
boundary 和明确 reopen reason 才能重新成为 candidate，仍需用户确认。

## 7. 实现 envelope

Main 接受后，Stage 1 默认上限：

```yaml
schema_version_change: 0
new_tables: 0
new_indexes: 0
new_migrations: 0
new_dependencies: 0
new_background_workers_or_schedulers: 0
new_prompt_versions: 0
provider_calls: 0
new_authority_stores: 0
new_composition_or_projection_adapters_max: 1
new_public_endpoint_types_default: 0
existing_surfaces_extended:
  - Research Workspace
  - existing Feedback payload
  - existing Workspace projection/decision
```

允许的代码面仅是：existing strict contracts 的 additive optional field、Feedback Event payload、
Workspace source validation/read projection、Research response composition、现有 Research template/JS/CSS
的小型展示扩展、对应 tests。若实现需要新表、migration、新 endpoint type、Prompt 或后台 worker，必须
停止并向 Main 提交材料性 Contract amendment；不能以普通实现细节自行扩权。

## 8. Mechanical Gate

全部测试使用 no-provider temp DB/临时 artifact path，不连接 live DB，不访问 Keychain。

### Gate A — baseline 与 treatment 配对

1. no Workspace rows：Research factual/product payload 与 answer/limitations DOM 内容和顺序为当前
   `after_answer` baseline；新增 control/explanation 只能报告 `no_confirmed_preference`；
2. unconfirmed candidate：product behavior 等于 baseline，explanation 只可多出 candidate-not-applied reason；
3. confirmed `before_answer`：仅 limitations DOM position 改变；
4. confirmed `after_answer`：answer presentation 等于 baseline，explanation 可指向 confirmed revision；
5. unrelated confirmed key：product behavior 等于 baseline；
6. malformed/unknown/conflicting/expired：fail closed baseline + reason。

### Gate B — disable / correct / rollback

1. per-session off：product behavior 等于 no-profile baseline，UI 可显示 disabled reason；DB
   row/event/receipt count 不变；
2. tombstone/expiry：baseline，history 保留；
3. correct：新 revision 生效，expected-version race 拒绝；
4. restore previous：形成新 revision，旧/中间 revision immutable；
5. terminal old-boundary replay 不复活；new boundary + reopen 仍先 candidate。

### Gate C — Feedback / Candidate

1. legacy Feedback payload/result 完全兼容；
2. exact target/hash、cross-task、duplicate、payload mismatch、fault rollback 继续成立；
3. 单个 structured Event 不创建/不授权 candidate；
4. 两个 incompatible/unrelated Events 不创建 candidate；
5. 两个 compatible distinct same-task Events 只允许 explicit candidate create；
6. candidate confirm 前 baseline，confirm 后 treatment；reject/expire 后 baseline；
7. free-text note 永不被解析为 confirmed preference。

### Gate D — authority non-interference

对 baseline/treatment/off/rollback 比较并断言以下完全相同：

- Research answer block text/order、status、limitations content；
- Citation/Evidence IDs、source versions、currentness、Fact/Artifact/Page heads；
- Search execution/open lane、ArtifactRoute recommendation/final route；
- Task/Attempt/Checkpoint/Result/termination/budget/provider status；
- Fast/Deep Ask 与 Product Search response；
- Prompt constants/files、schema version/table/index set。

### Gate E — restart/API/UI

- service/app restart 后 context hash 与 effective revision 稳定；
- API extra fields strict validation、content type/status code、legacy compatibility；
- UI 显示 applied/baseline reason、revision/version、Current Focus、off/correct/tombstone/rollback；
- JS tests 覆盖 before/after DOM placement、off、unrelated negative 与 accessibility order；
- Workspace UI 不再硬编码 `behavior effect false` 于已应用 key，但其他 kinds 仍如实显示 no effect。

### Gate F — regression envelope

至少运行：V5-B Workspace、Feedback/closeout、ArtifactRoute directed tests；Research Web/API；Search/Ask
compatibility；schema migration tests（temp copy only）；default no-provider suite 是否全跑由实际改动面决定，
但任何未跑项必须在 implementation report 诚实列出。

## 9. Stage 完成与报告

Stage 1 implementation report 必须报告：

- branch、accepted Contract authority、实现 Commit、diff scope、schema/table/index/prompt/dependency count；
- baseline/treatment/off/rollback/unrelated mechanical matrix；
- Feedback/Candidate authority、restart/fault/no-resurrection 证据；
- live DB 只读 hash window（如检查）与明确 `live rows not used`；
- Provider/credential/live migration 均未进行；
- fixture/cold-start/真实用户信号分层和未证明项；
- 请求 Main 做 Stage 1 有限验收，并且只在 Main 另行授权后进入 Stage 2。

## 10. 明确排除

- 个性化答案文本生成、Prompt 注入或事实裁剪；
- Corpus-aware retrieval/rerank、Fast/Deep/Research 通用路由、ASR/Translation 推荐；
- Knowledge Progress、Staleness、Collection Delta、Early Project Radar；
- generic Profile CRUD、MemoryOS、rules/inference/vector store、scheduler/notification/telemetry/eval platform；
- Provider、credential/Keychain、live migration、V5-D Skill/Policy、push/merge/tag；
- 将 fixture 当作真实用户收益或因 V5-A compound-query limitation 扩大 Stage。

## 11. Main 接受点

Main 若接受本 Contract，应明确记录：

1. 接受唯一 Stage 1 effect 与 authority/rollback 语义；
2. 接受零 schema/table/migration/Prompt/Provider 的默认 envelope；
3. 接受 Feedback → candidate → confirm 的三段边界；
4. 接受 mechanical Gate 与 cold-start 诚实报告规则；
5. 授权同一个 V5-C Session 实施 Stage 1。

没有上述明确记录时，`implementation_authorized=false`。
