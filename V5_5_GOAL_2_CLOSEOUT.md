# Shiliu V5.5 Goal 2 Closeout — Research → Knowledge → Reuse

> Date: 2026-08-13
> Branch: `codex/v5-5-productization`
> Baseline / rollback point: `cc707a62f32698d8fc5cbeb36995e0b05736d066`
> Status: COMPLETE

## 1. 最终闭环

普通 Research 页面现在提供“保存到知识”入口。成功 Research 先形成待确认结论；页面展示核心结论、来源、证据状态和主题，用户明确“确认发布”后，服务器才复用既有 V5-B 服务依次创建 current-grounded Fact、Knowledge Artifact、Topic Page 并发布。后续问题通过用户语言的“检查已有知识”进入既有 ArtifactRoute；页面用“直接使用 / 补充研究 / 重新研究”解释结果，并保留原始字幕下钻。

没有新增模型调用、schema、Knowledge extraction Agent、Router、后台任务或自动发布。

## 2. 关键修改文件

- `src/shiliu/research/knowledge_contracts.py`：显式发布选择合同。
- `src/shiliu/research/knowledge_service.py`：薄的 publish orchestration，内部只调用既有 review / Fact / Artifact / Topic Page / publish；候选增加字幕下钻链接。
- `src/shiliu/web.py`：`POST /knowledge/publish` 产品入口。
- `src/shiliu/templates/research.html`、`src/shiliu/static/research.js`：保存、Review/Publish、正式知识展示、later query、Reuse/Refresh/Research Seed 的用户语言和证据下钻。
- `tests/test_v5_5_goal2_knowledge_product.py`：显式发布、receipt-safe retry、相关不同问题 direct reuse、incomplete negative regression。
- 3 个既有 V5-B UI 测试同步新的产品文案。

## 3. G1 Case C 真实 Knowledge Promotion

直接复用 G1 Case C，没有重新运行 Research，也没有 Provider 调用：

- Research Task：`rtask_c9a09e60bcab6ffb30bc29baa226bae4`
- Result：`result_a80e3f1d6ace4ea2a2466bab923e1a87`
- Knowledge Candidates：
  - `kcandidate_949db1399e36bc2c2109b138d80fc3a3`
  - `kcandidate_c3f2046a5d297ca4210ba46ec932c830`
  - `kcandidate_f3af5a5e4ccab558c0b5084b38292519`
- Fact revisions：
  - `factrev_c9907da13f207c8622368b3081ef82ce`
  - `factrev_89f898437188668ae337e87243d2e639`
  - `factrev_cee38f19315ba5fb150616eecdfc5852`
- Artifact：`kartifact_e92cab89444104179f5d6b10dc7e1782`
- Artifact revision：`kartifactrev_13c5fc3fb48b4701e1e7d05461d23593`
- Topic Page：`topicpage_29617c1f89baf4c19023f07403b5478f`
- Page revision：`topicpagerev_df9238004d937f744a6a2fdd050fdbf0`
- Page 状态：`published`，published version `1`

发布请求显式选择 3 条待确认结论；发布后为 3 accepted Candidate、3 current Fact、1 current Artifact、1 published/current Topic Page。相同 publish command 的 focused regression 证明各既有 receipt 可安全恢复/去重，不会创建第二套资产。

## 4. Evidence / Citation lineage

正式 Fact / Artifact / Topic Page 继续指向 G1 Result、source boundary、EvidenceUse 和 current Evidence identity。真实发布资产使用的 current Evidence 为：

- Evidence：`citation_v1_e547e00b60dbcd6f7cb25765452e4334ec84b8ef69eea3be1366ecd01f673ad8`
- Video：`168`，`Skill 不就是更长的 Prompt 吗？答案没那么简单`
- current raw transcript：`/videos/168/transcript`
- raw subtitle fallback：`/media/168/raw-subtitle`
- Source version：`b47a34d7ac60ec8e9ba963cdff2f5dd1d7a50c6db8c3f478b764517273986753`

浏览器验证中 Topic Page 只展示一条去重后的“下钻到原始字幕”入口；ArtifactRoute 也可回到同一 current raw subtitle。Knowledge Asset 没有成为 Citation Authority。

## 5. Later Related Query / Direct Reuse

后续相关但不同问题：

```text
把可复用方法做成 Skill，除了写说明文字还需要哪些工程能力？
```

用户声明必须回答的自然要点：`按需读取`、`确定性执行`、`工程资产`。

- ArtifactRoute：`artifactroute_0384523b15f94fadce285962065f50cd`
- Recommendation：`direct_reuse`
- Gate：scope `exact`、currentness `current`、citations `pass`、completeness `complete`
- Missing aspects：0
- Confirmed outcome：`direct_reuse / completed`
- Reused Fact revisions：3
- Newly researched：0
- Continuation Task：无

这证明长期知识服务于相关但不完全相同的问题，不是相同 Query 的 Response Cache。Direct Reuse 已满足核心正向证明，未继续人工制造 stale/conflict/refresh Case。

## 6. blocked A/B negative check

复用历史 blocked task，没有重新运行：

- `rtask_dc9e7bc87944f3a35c389bf5a33286cc`：intake 结果 0 Candidate；0 Fact / Artifact / Page。
- `rtask_13f7b3b151e176677f6c79a6d44a58a6`：intake 结果 0 Candidate；0 Fact / Artifact / Page。

二者可形成空的 candidate snapshot 记录，但没有 grounded answer block，因此普通产品路径没有可 Review/Publish 的长期知识，也没有自动发布。

## 7. Focused / nearby regression

最终运行 129 个测试：

```text
tests/test_v5_5_goal2_knowledge_product.py
tests/test_v5_b_stage1_knowledge_workspace.py
tests/test_v5_b_stage2_knowledge_lifecycle.py
tests/test_v5_b_stage3_artifact_reuse.py
tests/test_v5_b_stage4_personal_workspace.py
tests/test_v5_b_stage5_product_closeout.py
tests/test_v5_a_stage4_operational_control.py
tests/test_v5_a_stage5_gate_b_provider_wiring.py
tests/test_v5_a_stage5_gate_b_provider_product.py
tests/test_v5_a_stage5_product_completion.py
tests/test_boundaries_and_web.py
tests/test_post_v5_execution_persistence.py

129 passed
```

另通过 `python -m compileall -q src tests`、`node --check src/shiliu/static/research.js` 和 `git diff --check`。未运行完整 deterministic suite，留给 V5.5 Final Gate。

## 8. Bounded correction

使用了唯一一次 bounded correction。真实浏览器检查发现已发布页面仍把维护术语放在主视图，并重复展示同一字幕。修正仅去重/截短证据预览、已发布后锁定保存按钮，并把 maintenance / feedback / authority 细节移入折叠区；没有改变 Knowledge authority、lineage、route 或 durable data。

## 9. Remaining limitations

- G1 Case C 虽有 8 条 EvidenceUse、覆盖 3 个视频，但 3 个 answer block 的直接 citation 都是同一 Evidence identity；本次正式知识的合法 lineage 因而正确但来源多样性较窄。
- 产品 publish 是既有、各自有 receipt 的 V5-B 步骤编排，不是一个跨步骤 SQLite 大事务；若来源在步骤中途改变，会 fail closed 并可能留下已接受 Fact，需用同一 command 安全继续或人工处理。
- Direct Reuse 仍要求用户填写“这个问题必须回答的要点”；没有新增模型去自动推断 required aspects。
- 真实验证在正确 Goal 2 worktree 的临时 `18521` 服务完成并写入现有 live DB；临时服务已停止。常驻 `18520` LaunchAgent 仍指向原 `Shiliu` worktree，本 Goal 未修改或重启常驻服务配置。

## 10. Checkpoint / completion conditions

- Branch：`codex/v5-5-productization`
- Goal 2 baseline：`cc707a62f32698d8fc5cbeb36995e0b05736d066`
- Goal 2 final HEAD：包含本 closeout 的 branch tip；精确 immutable SHA 在提交后的交付信息中记录。

- [x] 真实 Provider Research Result 合法进入 Knowledge Candidate。
- [x] blocked / incomplete Research 不会被误发布。
- [x] 用户明确 Review / Publish。
- [x] 形成真实 Fact / Artifact / Topic Page。
- [x] 正式知识可下钻 current Evidence / Citation / raw transcript。
- [x] 后续相关但不同 Query 发现已有知识。
- [x] ArtifactRoute 给出真实 route decision。
- [x] Direct Reuse 已被真实产品验证。
- [x] 主流程不要求理解内部工程术语。
- [x] focused / nearby / G1 regression 通过。
- [x] Goal 1 行为未回归。
- [x] 未引入禁止的新架构。

Goal 2 completion conditions 已满足。Goal 3 未启动。
