> 当前状态（2026-10-10）：已合入日常产品并完成18520真实网页验收。以下前期章节保留阶段历史，最新发布结果见文末。

# Deep V2 × Jev B0 集成验收概要

2026-10-10。结论：**可以合并发布**，等待用户最终验收与发布授权。隔离实现和网页验收已完成；**未合并、未部署、未重启或切换日常18520**。

## 实际交付

唯一产品目标仍为 `Shiliu-research-next`（`codex/research-next`，基线 `5a8abeb` 加当前未提交产品改动）。隔离分支 `codex/deep-v2-b0-integration` 位于 `/Users/elliot/.codex/worktrees/deep-v2-b0-integration/Shiliu-jev-rerank`。先复制当前产品必要代码/fixture并记录文件hash，原工作区没有stash/reset；本次增量不包含这些已有助手改动。

- 定向复用 `v2.py`、`f1_tools.py`、`retrieval/f1.py`、原文追读和相关既有测试。当前 Ask Deep 使用 V2/F1；直接构造旧 Deep 的内部调用者保留原默认行为。
- 新 `batch_reduce.py` / `jev.py` 实现冻结 B0。Prompt、BatchReduction Schema、C_REL及40%核心/60%补位、精确去重与5秒前序保护已与研究中的纯定义比对一致，固化为自包含fixture；无研究脚本运行时依赖，无BQ/C。
- Search完成后在同一批次调度共享Reduce；原始证据在应用跨Query结果前登记。预算预检复用实际批次结果应用器与Controller消息构造器，暂存只在请求局部，Graph没有临时实例状态。
- 成功共享摘要不进入单Query缓存；独立摘要缓存保留。单Query、空/失败结果、混合工具和独立缓存命中保留S。Jev/共享结构/引用/预算/deadline失败整批回退S，保留已发生usage和未知usage，取消/超时后不追加派发。
- Deep单独固定Flash、非thinking模型工厂；当前Final事实Prompt不修改，适配完整V2 Context与精确引用。Fast/Assistant/Memory/Wiki及其他研究路径不换Provider。主数据库仍为Schema25，无数据库迁移/降级。
- F1 companion接入已有检索同步边界，错误不阻断原同步；过期/损坏索引不能充当Deep证据。依赖及锁文件仅增加 `jieba==0.42.1`。
- 前端只复用现有状态文本节点：实际Jev HTTP派发后显示“正在使用 Jev 筛选并整理检索证据”；S及后续阶段为普通文案。补最小V2终态/来源导航映射、脚本缓存版本号，没有新组件、Badge、开关UI、布局或CSS。保留现有Deep 202+轮询、Fast NDJSON事件、答案分块与引用。

配置缺省S；文件 `[llm] deep_reduce_strategy="b0"` 或环境 `SHILIU_DEEP_REDUCE_STRATEGY=b0` 显式开启，环境优先、启动时读取，保存其他设置不会丢失策略。回切S需有序重启；原始数据库不回滚。Trace记录策略、批次accepted/fallback及原因、引用映射、Provider usage、冻结合同hash与运行代码/数据库路径。

## 工程检查

- 受影响范围回归 **230通过，1项助手基线失败单独排除**；最后窄范围复核 **175通过**；现有JS机制加最小生命周期/来源导航检查 **7通过**。
- 覆盖V2/S、跨Query登记/原文引用、共享缓存隔离与重复查询、同Graph并发run、部分Search失败、Jev部分成功后失败、非法共享结构/引用、输入/后续Controller预算、迟到/取消、凭据/配置切换、实际Application路由、Schema25与companion故障隔离。复用Fast/API/Continuation/Trust及助手、知识相关原有测试。
- 助手已有失败为 `test_relative_time_is_anchored_and_old_note_expires_without_epoch_change`，在集成前完整产品快照的独立目录重新运行，同样出现 `task_note_dependency_changed`。不把它算通过，也不在本次改动中修助手的时间依赖问题。
- 原 `research-next` 基线全部记录文件hash再次核对：**0变化**。18520仍为原PID43226。隔离代码保留了原未提交产品功能；没有提交/删除/覆盖它们。

## 实际网页和服务证据

付费成功项都由浏览器在普通 `/ask` 页面选择Deep并点击提交，经实际Application、`POST /api/ask/runs`和后台V2 Graph；没有B0Graph子类或CLI替代。18521使用独立v25备份、字幕副本、索引/Trace目录。预算保护仅在私人验收启动器的HTTP transport，未改产品行为。

| 用例 | 同run执行证据 | 网页结果 |
| --- | --- | --- |
| 真实B0：深圳/厦门吃逛 | `ask_run_7d9a505f7fdd4a13a7f17641ad723eb3`；2个字幕Query，8个真实Jev HTTP，1次共享Reduce accepted=true、fallback=false，2轮Controller及Final；无执行errors | partial，7块答案、17引用，78.69s；引用按钮定位到对应卡片，厦门原文展开成功 |
| 真实S：海边路线/宝安美食 | `ask_run_daddec59ebbf4da0995015c45c6a2393`；隔离实例切S并重启，2个Query独立Reduce，无Jev/共享Reduce；后续Controller和Final正常 | partial，4块答案、9引用，30.55s，完成状态正常；这是开关冒烟，不是质量对照 |
| 确定性多批/跨Query追读 | 最终Graph代码运行 `ask_run_5c3f504c85bc41b69634b7a570bf172c`；Query qa引用仅由qb返回的原文；第二批read_context沿该ref追读，并命中原始Search缓存；3轮Controller、4个工具、Final正常 | complete，跨Query引用可定位/展开；现有状态区Jev文案已看到并截图 |
| 确定性Jev故障 | `ask_run_4161176825864a81a59d40d807352c1f`；模拟HTTP503，B0 fallback=true，两项S Reduce继续，沉没调用记录保留 | complete，正常答案/引用，无卡住或异常中间状态；Jev派发期间显示Jev，回退后恢复普通阶段 |
| 单Query | `ask_run_770b5eb9aec3448caba8eb0a5d85668e`；skip=fewer_than_two_eligible_queries，独立Reduce，Jev=0 | complete，普通Deep终态与引用 |
| Fast同页 | `ask_run_b63254ef496449dba0f0f39bccfa7c3b`；原Fast检索/NDJSON生命周期与Final，假Provider，无付费调用 | complete，快速回答分块/引用与按钮恢复正常 |
| 历史/原文 | 隔离服务重启后GET回读真实B0的持久结果，仍为7块/17引用；两条真实请求全部26条Citation重做当前源校验 | video/bvid、完整quote、segment身份、起止时间及jump_url全部与原始Store/原文一致 |

确定性网页项在18522的实际Application中仅替换依赖，使用合法的原文证据及真实Store/Materializer/服务持久化；Jev用HTTP MockTransport，Controller/Reduce/Final用假Provider，**不算真实模型证据**。真实B0样本自然只执行一批且没有跨Query独有引用，多批与该引用风险由确定性网页及工程检查补齐，不追加批量真实请求。

当前产品原本没有研究线独立分步面板或answer_part渐进交付；本次保护的是它已有的状态区、轮询/流式事件、终态分块及引用，没有搬新UI。历史结果经持久API回读验证；当前页面刷新仅保留问题/范围，没有新增历史页面。浏览器直开JSON API被客户端阻止，改由实际服务GET核实；未声称历史列表网页已新增/验收。

视频外链的bvid/t和原文已核对，点击外链未取得可观察的新播放器页面，**外部视频播放没有确认**；用户可在正常浏览器复核，不能把它写成播放通过。模型/ASR的主体和事实语义风险仍存在，合法引用不保证每个结论正确；未调Prompt或重新开展质量评测。

## 费用与证据位置

新增真实请求仅2条，**18次HTTP（DeepSeek10、Jev8）**。实际返回usage完整，无未知费用项；按官方价格与周末非高峰费率估算合计 **$0.027305046**，未取得供应商账单，不称账单核销。启动器每次派发前以输入字节上界及最大输出按峰价预留，跨重启共享$1账本，重试/错误也计入；本次峰价上界账本累计$0.052364。没有重跑历史评测或新增Jev研究。

价格核对：[DeepSeek官方](https://api-docs.deepseek.com/quick_start/pricing/)、[Jev官方](https://docs.typesafe.ai/models)。继续请求旧Flash模型名并记录返回模型；供应商实际模型版本变化不由本次集成控制。

私有证据目录：`/Users/elliot/new-systems/agent-job-prep/Shiliu-b0-integration-runtime`。含 `api-ledger.json`、接收路径记录、真实/fixture Trace、全部源校验、测试XML/日志、助手基线复现、网页关键截图及可复现启动器。原文/数据库/凭据和截图不提交Git，报告只列必要摘要。

## 合并与切换日常网站的最小步骤

1. 用户验收并授权发布后，仅将本次隔离分支提交cherry-pick到 `codex/research-next`；先检查原未提交改动与本次路径是否冲突，保留原功能增量。不要合并整条旧研究分支，也不把落后的main当作本次迁移目标。
2. 在现有产品环境安装锁定的jieba依赖，沿用原v25数据库、Artifact、Qwen和原服务入口。为日常实例显式配置B0，并把Jev凭据安全注入环境或Keychain。**当前正式环境没有该Jev环境变量/Keychain；这次真实冒烟由私人启动器临时读取已有研究凭据，产品代码不会读取研究.env。若不补配置，会自动回退S。** 不把密钥写入代码、配置文件或Git。
3. 等待/处理原站在途run，再按授权有序重启18520。核对实际加载路径/提交和模块hash、v25数据库路径、有效策略；合并成功不能代替运行版本更新。
4. 在日常18520正常提交一次Deep问题，核对同run真实Jev与accepted共享Reduce、状态、答案和引用。这是**尚未执行的发布后验收**；隔离站通过不代表日常站已经上线。
5. 需要回退时设S、有序重启、用新网页请求Trace验证s且Jev=0；若是V2接线的版本问题则恢复记录的原兼容代码/配置，不进行数据库降级。

剩余边界：日常发布和发布后网页验收待授权；正式Jev凭据待安全配置；一项已存在的助手时间依赖失败及外部播放器限制如上。HTTP在途请求不能保证强制中断，迟到按deadline拒绝、禁止继续派发；20秒S预留不保证慢Provider一定成功，耗尽时仍按现有partial/insufficient合同结束。不扩大研究或迁移范围。


## 2026-10-10 产品能力整合收尾（后续授权）

此前未迁入的首尾与逐块交付现已整合；上文“Final不改、没有研究分步面板/answer_part”的描述仅代表第一阶段验收，不再描述当前隔离版本。本阶段定向复用研究线已验收的 `6fe808c`、`7877570`、`43ff722`、`7c51cd0` 成果，没有重设协议或UI；冻结B0未改。

- 原 `AnswerJSONStream` / `AnswerStreamDelivery`、Provider SSE、局部Citation Repair、首尾合同与安全强调展示按成熟设计复用。只有完整且通过当前源及Citation Integrity的答案块进入 `answer_part`，重试/错误/不足可撤回，最终结果统一对齐；ClaimVerifier启用时不抢先发布。Deep仍使用持久事件轮询，Fast仍使用NDJSON及原检索，不迁移Fast到研究线F1。
- 原紧凑连续研究步骤面板、CSS及前端节点复用保留；实际派发Jev仅改已有资料整理步骤文案，下一运行没有Jev时不保留该文案。只增加接口版本字段兼容、首尾结果/事件/Trace/草稿持久回读；Schema25 segment cardinality保护、产品Provider重试策略、原助手功能及B0接线均保留，无数据库变更。
- 工程回归 **274项通过，0失败**；JS **22项通过**。复用成熟流式/可读性测试与当前产品factory fixture，覆盖首尾历史/草稿读取、Provider真实SSE分片、先发布后完成、非法引用块隐藏、重试撤回/终态不足、语义Verifier阻止早发，以及B0、S、缓存/引用、Continuation/Trust、Fast及Assistant/Memory/Wiki相关回归。第一阶段记录的助手基线失败仍未在本次修复。
- 新增真实网页请求只有一条：`ask_run_31499d2b1c8a490da3dab58e1855fb79`，18521普通网页提交；2个字幕Query、8次真实Jev HTTP、一次共享Reduce accepted=true/fallback=false、后续Controller与Final正常。Provider真实SSE，Trace显示11块早期交付、0次reset；首块在Final生成开始后3.57秒校验发布，DOM实际显示距最终响应约 **10.85秒**。最终partial，11块/15引用、首尾俱全、总55.61秒，无执行errors；15条引用全部重做当前源/身份/原文/时间与URL校验，网页实际点击定位并展开原文。没有质量对照或Prompt迭代。
- 确定性实际网页（18522）`ask_run_8782238f23a7426eafa42e661dc32f06` 保留3轮Controller、跨Query引用及后续追读；两个合法块在Provider完成前分别显示，夹入的非法引用块 `INVALID_UNCITED_SENTINEL` 从未发布到answer_part或网页，Final保留合法块。Fast同页 `ask_run_28c2a721588448fc91adcb6a6bea87c6` 也渐进交付/首尾正常，研究面板隐藏，非法块未发布。假Provider项无付费模型证据。
- 本轮真实冒烟12次HTTP（DeepSeek4、Jev8），按实际usage估算新增 **$0.01348467**。从最初集成开始、含用户体验新增请求的累计账本35次HTTP、**$0.053748714**，仍受原$1预算保护。没有供应商账单核销。
- 私有证据沿用原目录：`stream-engineering.xml`、`stream-real-dom-metrics.json`、`stream-source-verification.json`、真实/fixture Trace、`stream-real-jev.jpg` / `stream-real-final.jpg` / `stream-real-citation.jpg`。原产品记录文件hash仍0变化，日常18520 PID43226未重启。新增验收期间没有操作真实日常数据库。

结论：**可以合并发布，无新增实质性阻碍**。沿用上文最小发布步骤，将两次隔离增量一起接入日常产品；配置Jev凭据、安装依赖、有序重启18520并验证日常网页仍待用户授权。外部播放器播放仍未确认，不扩大研究或数据库迁移。


## 2026-10-10 正式产品发布与最终网页验收

- 已将隔离成果定向cherry-pick至日常 `codex/research-next`：`5fc758d`（V2/B0）、`576527f`（首尾、流式答案块与研究步骤）。原77份未提交产品文件逐一hash核对保持不变，已另行私有备份，没有混入本次提交。
- 日常18520沿用原产品CLI、Schema25数据库、Artifact与离线Qwen配置；安装锁定jieba依赖，Keychain安全保存Jev凭据，现有配置明确开启B0。发布验收后已移除临时HTTP预算钩子并有序重启正常服务。18521/18522临时服务已停止。回退仍为将 `[llm] deep_reduce_strategy` 设为 `s` 后有序重启，无数据库回滚。
- 正式网页普通Deep请求 `ask_run_f6e8ee17783b44c68151e1b8121f948a`：8次真实Jev HTTP、一次共享Reduce accepted=true/fallback=false、2轮Controller与Final。共享输入46份去重证据/51518字符；首次Reduce HTTP超时后现有传输重试成功，无S回退或执行errors。总120.14秒，终态partial符合现有产品合同。
- 网页实际展示Jev研究步骤、10个渐进答案块及15条引用；首块约提前9.36秒显示，Trace交付10块/0次reset。实际点击引用定位并展开原文；全部15条引用的源身份、完整原文、segment、时间和跳转URL经当前Materializer与Store复核一致。没有声称外部播放器播放通过。
- 正式站Assistant、知识、研究、搜索页面HTTP200；本次没有另做付费Fast请求，Fast及Assistant/Memory/Wiki兼容沿用已通过的274项Python/22项JS回归和隔离网页检查。已知助手时间依赖基线问题未扩大修复。
- 发布新增13次HTTP，已返回usage费用估算$0.01289835，含超时未知usage的本次保守上界$0.072532158。自集成开始含用户体验累计已知usage估算$0.108676074，保守上界$0.257246016，低于$1；1次超时usage未知，已按派发预留上界计入，未声称供应商账单核销。
- 本地产品分支含199个未公开历史提交，其中有研究数据和私人截图，因此不直接推送整条历史。沿用脱敏发布方式，从已公开origin/main生成 `codex/research-next-release`，发布当前已提交产品源码、必要测试、依赖和本报告；不加入原77份未提交工作、数据库、环境文件、Trace、截图或原始实验数据。涉及真实字幕的测试fixture改为结构等价的合成数据，相关63项回归通过。公开源码与本地已提交产品源码相同；仅发布历史及fixture脱敏，不另维护产品版本。
- 最终证据保留私人runtime目录 `release/`：daily-acceptance.json、DOM时序、Jev/最终答案/引用截图、原配置及数据库备份。证据与凭据不进入Git。

结论：正式产品B0、Deep V2、流式输出与研究状态已实际验收通过，无新增阻碍发布的问题；GitHub发布结果以最终提交与远端核对为准。
