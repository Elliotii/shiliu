# V3 Checkpoint 3 Token 与上下文成本分析

日期：2026-07-17
对象：Taxonomy Run #1，Snapshot #2，48 条 Discovery + 3 条 D 级 Assignment
边界：本报告只分析既有落盘产物；没有调用模型，没有修改生产摘要格式，也没有启动 Discovery A/B/C。

## 一、结论

成本主要不来自最初的 48 张紧凑卡片，而来自四件事：

1. **历史阶段输出被反复放回上下文。** 按字符权重分摊到真实 API prompt token 总量后，历史 Draft、局部候选和原始待修复响应约占已知输入 Token 的 **80.7%**。
2. **局部 Topic / Entity 输出膨胀。** 第一批一次生成了 23 个 Topic 和 57 个 Entity，原始输出 20,568 字符，并触发 Repair。
3. **high thinking。** Consolidation 与 Hierarchy Validation 的已知调用共消耗 91,081 Token，其中 reasoning token 为 28,253；reasoning 占这些调用 completion token 的 65.4%。
4. **故障、Repair 与质量重试。** 理想的一次成功路径约为 82,334 Token；其余已知 84,404 Token 来自 Repair、被替代的 Draft/Validator 以及重试，占已知总量 50.6%。另有一次空响应 usage 已无法恢复。

Checkpoint 3 已知总量是 **至少 166,738 Token**：Prompt 94,773，Completion 71,965。一次空 Validator 响应的 usage 在审计修复前被覆盖，因此不能把 166,738 称为精确总量。

## 二、逐调用明细

`prompt_characters` 是落盘 user prompt 的 Unicode 字符数，不包含固定 66 字符 system message。空响应行的 Token 和耗时无法恢复。

| call_id | stage | batch | cards | attempt | thinking | prompt chars | prompt / cached | completion / reasoning | total | sec | raw chars | schema valid | repair |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| `consolidation/main/s01/r01` | consolidation | main | 0 | 1 | high | 19,162 | 7,155 / 0 | 11,480 / 4,273 | 18,635 | 142.056 | 21,441 | 是 | 否 |
| `consolidation/main/s02/r01` | consolidation | main | 0 | 1 | high | 20,589 | 7,610 / 7,040 | 16,385 / 10,057 | 23,995 | 228.632 | 18,938 | 否 | 是 |
| `repair/consolidation/s02/r01` | json_repair | main | 0 | 1 | off | 19,731 | 6,613 / 0 | 6,357 / 0 | 12,970 | 57.059 | 19,040 | 是 | — |
| `hierarchy/main/s01/r01` | hierarchy_validation | main | 0 | 1 | high | 28,762 | 11,216 / 0 | 5,231 / 4,787 | 16,447 | 85.869 | 1,064 | 是 | 否 |
| `hierarchy/main/s02/r01` | hierarchy_validation | main | 0 | 1 | high | 28,997 | 未知 | 未知 | 未知 | 未知 | 0 | 否 | 否 |
| `hierarchy/main/s02/r02` | hierarchy_validation | main | 0 | 2 | high | 28,997 | 11,325 / 11,264 | 5,886 / 5,245 | 17,211 | 89.600 | 1,919 | 是 | 否 |
| `hierarchy/main/s04/r01` | hierarchy_validation | main | 0 | 1 | high | 27,345 | 10,559 / 0 | 4,234 / 3,891 | 14,793 | 81.312 | 1,272 | 是 | 否 |
| `local/b001/s01/r01` | local_discovery | 001 | 24 | 1 | off | 8,952 | 4,192 / 0 | 6,971 / 0 | 11,163 | 80.047 | 20,568 | 否 | 是 |
| `repair/local/b001/s01/r01` | json_repair | 001 | 0 | 1 | off | 21,764 | 7,361 / 0 | 5,279 / 0 | 12,640 | 44.533 | 15,368 | 是 | — |
| `local/b002/s01/r01` | local_discovery | 002 | 24 | 1 | off | 7,806 | 3,879 / 0 | 3,023 / 0 | 6,902 | 45.612 | 8,183 | 否 | 是 |
| `repair/local/b002/s01/r01` | json_repair | 002 | 0 | 1 | off | 10,174 | 3,630 / 0 | 2,871 / 0 | 6,501 | 27.358 | 7,796 | 是 | — |
| `assignment/b001/s01/r01` | trial_assignment | 001 | 24 | 1 | off | 19,817 | 8,385 / 0 | 1,908 / 0 | 10,293 | 18.442 | 6,697 | 是 | 否 |
| `assignment/b002/s01/r01` | trial_assignment | 002 | 24 | 1 | off | 18,699 | 7,801 / 0 | 2,099 / 0 | 9,900 | 20.291 | 7,264 | 是 | 否 |
| `assignment/b003/s01/r01` | trial_assignment | 003 | 3 | 1 | off | 13,078 | 5,047 / 4,608 | 241 / 0 | 5,288 | 3.755 | 829 | 是 | 否 |

完整机器可读表属于 `<local-run-artifact>`，不会进入仓库。

### 阶段聚合

| 阶段 | 调用数 | 已知 Token | Prompt | Cached | Completion | Reasoning | 已知耗时 |
|---|---:|---:|---:|---:|---:|---:|---:|
| facet | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| local_discovery | 2 | 18,065 | 8,071 | 0 | 9,994 | 0 | 125.659s |
| content_type_discovery | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| consolidation | 2 | 42,630 | 14,765 | 7,040 | 27,865 | 14,330 | 370.688s |
| quality_gate_feedback | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| hierarchy_validation | 4 | ≥48,451 | ≥33,100 | 11,264 | ≥15,351 | ≥13,923 | ≥256.781s |
| trial_assignment | 3 | 25,481 | 21,233 | 4,608 | 4,248 | 0 | 42.488s |
| json_repair | 3 | 32,111 | 17,604 | 0 | 14,507 | 0 | 128.950s |
| other | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

`quality_gate_feedback` 没有独立模型调用；它以 1,427 字符追加到第二次 Consolidation，分摊约 527 Prompt Token。

Token 最高三个阶段：Hierarchy Validation ≥48,451、Consolidation 42,630、JSON Repair 32,111。
耗时最高三个阶段：Consolidation 370.688 秒、Hierarchy Validation ≥256.781 秒、JSON Repair 128.950 秒。

### high thinking

- 已知 high-thinking 总 Token：91,081，占已知总量 54.6%。
- high-thinking completion：43,216。
- reasoning token：28,253，占全部已知 Token 16.9%，占 high-thinking completion 65.4%。
- high-thinking 已知耗时：627.469 秒，占模型累计已知耗时 67.9%。

因此 high thinking 是重要成本来源，但它与超长历史上下文叠加：不能把全部 91,081 Token 都归因于 thinking。真正由隐藏推理明确增加的是 28,253 reasoning token。

### 故障与重试成本

按不同口径区分：

- JSON Repair：32,111 Token。
- 第一版 Validator 未覆盖子节点，随后被替代：16,447 Token。
- 已知协议/Repair 故障成本合计：48,558 Token，另加一次 usage 未知的空响应。
- 第一次 Consolidation + 能发现真实支持问题的 Validator 属于质量迭代，而非纯故障；相对理想一次成功路径，它们增加 35,846 Token。
- 理想一次成功、无需 Repair 的同等路径约 82,334 Token；实际额外已知消耗 84,404 Token。

### Trial Assignment

Trial Assignment 消耗 25,481 Token，占已知总量 **15.28%**；耗时 42.488 秒，占已知模型耗时 4.6%。其输入中 68.3% 是重复发送冻结 Taxonomy Draft，而不是卡片本身。

## 三、输入字段成本拆分

DeepSeek V4 Pro 的精确 tokenizer 当前不在本地依赖中。阶段总 Prompt Token 来自 API，属于真实值；字段级 Token 是按字符权重分配并校准到每次 API `prompt_tokens` 的估算值，不应称作 tokenizer 实测值。

### 全部已知 Prompt 的字段归因

| 输入部分 | 字符数 | 分摊 Token 估算 | Prompt 占比 |
|---|---:|---:|---:|
| 历史阶段输出 | 202,349 | 76,441 | 80.7% |
| 核心观点 | 10,172 | 4,582 | 4.8% |
| 任务说明 | 6,066 | 2,371 | 2.5% |
| 简介 | 5,190 | 2,326 | 2.5% |
| 一句话结论 | 5,026 | 2,265 | 2.4% |
| Schema | 5,699 | 2,233 | 2.4% |
| 标题 | 3,038 | 1,364 | 1.4% |
| JSON / 行式协议开销 | 3,000 | 1,355 | 1.4% |
| 实体 | 2,194 | 990 | 1.0% |
| Quality Gate feedback | 1,427 | 527 | 0.6% |
| 短 ID + 证据等级 | 495 | 223 | 0.2% |
| System Prompt | 858 | 96 | 0.1% |

原始卡片字段及其行式开销在 Local Discovery 和 Assignment 中合计分摊约 13,105 Prompt Token，只占全部已知 Prompt Token 13.8%、全部已知 Token 7.9%。

### Local Discovery 的 48 张卡片

| 字段 | 字符数 | 分摊 Token 估算 | Local Prompt 占比 |
|---|---:|---:|---:|
| 核心观点 | 5,086 | 2,441 | 30.2% |
| C 级简介 | 2,595 | 1,257 | 15.6% |
| 一句话结论 | 2,513 | 1,206 | 14.9% |
| JSON / 行式协议 | 1,546 | 745 | 9.2% |
| 标题 | 1,503 | 723 | 9.0% |
| 实体 | 1,097 | 529 | 6.5% |
| Schema | 1,078 | 520 | 6.4% |
| 任务说明 | 1,070 | 516 | 6.4% |
| 短 ID + 证据等级 | 240 | 116 | 1.4% |
| System Prompt | 132 | 18 | 0.2% |

真实确认：

- 48 条分布为 A=22、B=9、C=17。
- A/B **没有发送简介**；A 的结论/观点/实体字符分别为 1,866 / 3,765 / 856，B 为 647 / 1,321 / 241。
- 17 条 C 级简介共发送 2,595 字符，最短 9、最长 300、平均 152.6。
- 核心观点、实体和一句话结论在 Local Discovery 读取一次，又在 Trial Assignment 完整读取一次。
- Consolidation **没有读取原始卡片**，只读取候选支持统计、两批局部候选和第二次的 Quality Gate feedback。
- Hierarchy Validation 读取 Draft 和局部候选；三次已知 Validator Prompt 中历史输出占 97.6%。
- Trial Assignment 重复读取 Draft；Draft 分摊约 14,493 Prompt Token，占 Assignment Prompt 68.3%。
- JSON Repair 读取原始响应而非卡片；待修复原始响应占 Repair Prompt 约 92.2%。

完整字段数据属于 `<local-run-artifact>`，不会进入仓库。

## 四、输出膨胀

### Local Discovery

| 批次 | CT | 一级 Domain | 二级 Domain | Topic | Entity | supporting ID 次数 | definition 字符 | includes/excludes | stability reason |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| batch-001 | 5 | 5 | 2 | 23 | 57 | 130 | 3,106 | 800 | 274 |
| batch-002 | 4 | 3 | 3 | 3 | 9 | 59 | 904 | 947 | 259 |

第一批的 23 个 Topic 和 57 个 Entity 是最明显的膨胀源：它们带来大量 definition 与 supporting ID，并超过 Schema 的候选数量限制，最终触发 Repair。Content Type 和 Domain 总共只有 12 个，不是第一批输出失控的主要原因。

局部阶段可以延后的内容：

- Topic 不需要完整 definition；局部只保留短名称和 supporting IDs 即可，详细定义可在全局阶段按需生成。
- Entity 局部只需 `name + entity_type + supporting IDs`，无需为几十个实体重复生成长定义。
- Domain/Content Type 的 includes、excludes 对归并有价值，但局部可限制为各 1～2 条短边界。
- `stability_reason` 可改成短证据代码或延后到全局稳定性判断。
- Topic/Entity 应先做确定性去重和数量门禁，避免 batch-001 这类 80 个候选对象进入 Repair 和 Consolidation。

### Consolidation 与 Assignment

- 初版 Consolidation：4 CT、6 一级、6 二级、23 Topic、38 Entity、175 次 supporting ID。
- 修正版 Consolidation：6 CT、5 一级、2 二级、23 Topic、35 Entity、152 次 supporting ID。
- Consolidation 仍原样携带大量 Topic/Entity，说明局部膨胀被传递到了全局上下文。
- 51 条 Assignment 输出的 `reason` 字符数为 **0**：当前真实 Schema 没有输出规划中的 concise classification reason。这是实现与规划的差异，本报告未修改它。

完整统计属于 `<local-run-artifact>`，不会进入仓库。

## 五、私有审计样例

真实 Discovery View、Local Discovery 请求与原始输出、Consolidation 字段摘要和 Trial Assignment 请求/输出摘要均保存在 `<local-run-artifact>`。这些文件包含真实收藏内容或原始模型上下文，不进入仓库；公开报告只保留脱敏后的聚合统计。

## 六、不调用模型的压缩估算

方案 A 使用当前紧凑行。方案 B 使用：短 ID、标题、main_subject、content_goal、最多 5 个 technical concepts、最多 3 个 usage contexts、最多 5 个 entities、证据等级。

| 范围 | 方案 A 字符 / Token 估算 | 方案 B 字符 / Token 估算 | 字符压缩 | Token 压缩 |
|---|---:|---:|---:|---:|
| 同一 48 条 | 14,457 / 10,038 | 11,192 / 6,798 | 22.6% | 32.3% |
| 全部 128 条 | 41,239 / 27,962 | 28,959 / 17,624 | 29.8% | 37.0% |

限制：目前只有 12 条真实 Facet，其中 6 条与这 48 条重合。方案 B 使用真实 ID、标题、证据等级；已有 Facet 使用真实字段，其余按 12 条真实 Facet 的字段形状循环投影。它是上下文尺寸估算，不是 128 条已生成的 Classification Profile，也没有计算生成 Profile 本身的 LLM 成本。

Classification Profile 能降低卡片输入，但无法单独解决本次主要成本：历史输出反复回传、Topic/Entity 膨胀、Repair 和 high-thinking reasoning。

## 七、正式 A/B/C 前的建议成本门禁

先不修改生产摘要。根据本次数据，建议正式 A/B/C 前至少满足：

1. 24 条 Local Discovery 原始响应一次通过 Schema，Repair 率为 0。
2. 每批 Topic 不超过 8、Entity 不超过 15；局部 Topic/Entity 不生成长 definition。
3. 单批 Local Discovery 总 Token 不超过 10,000，completion 不超过 3,500。
4. 单次 Consolidation 不超过 20,000 Token，且不因格式问题触发 Repair。
5. A/B/C 每轮只做 Local Discovery + 单轮 Consolidation，单轮门禁建议不超过 45,000 Token；三轮合计不超过 135,000 Token。
6. Hierarchy Validator 不再读取完整局部候选，只读取 Draft、节点证据摘要和必要边界样本。
7. high thinking 暂只保留给全局 Consolidation；是否用于 Validator，应在一次非 high 的同输入离线对比后决定。Local、Assignment、Repair 继续关闭 thinking。
8. 缓存命中不能作为主要降本手段；本轮虽命中 22,912 Prompt Token，但主要来自重试，不能抵消不必要的上下文与输出。

在这些门禁通过前，不建议启动正式 Discovery A/B/C。

## 八、数据与复现

- 全部计算结果、逐调用 CSV、字段拆分 CSV 和输出膨胀 CSV：`<local-run-artifact>`
- 纯离线复现脚本：[`analyze_v3_checkpoint3_cost.py`](../tools/analyze_v3_checkpoint3_cost.py)
