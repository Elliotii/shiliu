# bilibili-cli 对拾流 V0 的技术评估

> 状态：完成。评估基于上游 commit `dbe28551930df43b633baa52e9639832aeada967`、聚焦单元测试、隔离回归测试和只读真实 API 测试。真实 412 未故意触发，以避免制造反爬风险；其映射由源码和隔离测试确认。

## 1. 执行结论

最终结论：**B. 可以使用，但必须增加拾流包装层**。

更精确地说：`bilibili-cli` 可以作为拾流的认证、收藏夹发现、基础视频信息和错误治理组件，但**不能不加修改地充当完整 B 站 Adapter**。拾流必须拥有自己的领域 Schema、基线/幂等状态和 Transcript Provider；语言选择、人工/AI 字幕来源和错误分类仍需要包装或补实现。CLI 只读取 P1 的行为符合拾流 V0。

不能直接作为完整 B 站 Adapter 的已确认原因：

1. 无中文字幕时选择第一条任意字幕，不满足“中文、英文、否则跳过”；
2. 字幕 payload 不保留语言和人工/AI 字幕来源；
3. 收藏夹 item 缺少收藏时间、发布时间、封面和 UP 主 ID；
4. 视频规范化 payload 缺发布时间和封面；
5. 格式合法但不存在的 BV 实测返回 `internal_error`，而不是稳定的 `not_found`；
6. 底层直接依赖 GPL-3.0-or-later 的 `bilibili-api-python`，分发或源码复用方式需要单独评估许可证影响。

## 2. 环境和安装

| 项目 | 结果 |
|---|---|
| OS | macOS 26.5.1, arm64 |
| Python | 3.12.13；系统 Python 3.9.6 不满足上游 `>=3.10` |
| 上游仓库 | `public-clis/bilibili-cli`；旧地址 `jackwener/bilibili-cli` 会重定向 |
| 上游 commit | `dbe28551930df43b633baa52e9639832aeada967` |
| 源码版本 | 0.6.2 |
| PyPI 最新版 | 0.6.2，发布于 2026-03-11 |
| 与 tag 差异 | 当前 main 仅多 4 个文档/CI 提交，功能代码与 v0.6.2 一致 |
| 安装方式 | 本地 venv + editable source install |
| CLI 许可证 | Apache-2.0 |
| 关键运行依赖 | bilibili-api-python 17.4.2，声明 GPL-3.0-or-later |

正式拾流不应安装 `audio` extra。此次为了运行上游 dev 测试安装了 dev extra，其中包含 `av`，但没有执行任何音频命令或音频测试。

## 3. 功能测试矩阵

| 能力 | 测试结果 | 稳定性 | 拾流是否需要 | 备注 |
|---|---|---|---|---|
| 二维码登录 | 通过 | 初步可用 | 是 | 自动浏览器 Cookie 提取超时，二维码成功 |
| 凭证持久化 | 通过 | 初步可用 | 是 | 新进程验证成功；文件权限 0600 |
| 无效凭证清理 | 通过 | 初步可用 | 是 | 隔离 HOME 实测；返回 `not_authenticated` 且未泄露测试 secret |
| 收藏夹列表 | 通过 | 初步可用 | 是 | 合法 JSON，共 10 个文件夹 |
| 指定收藏夹 | 通过 | 初步可用 | 是 | 目标 `llm`，首次记录 1 个基线 BV |
| 分页 | 通过当前单页；多页单元测试通过 | 初步可用 | 是 | 当前目标第一页 `has_more=false` |
| 视频信息 | 通过 | 初步可用 | 是 | 关键基础字段存在，部分 V0 字段缺失 |
| 中文字幕 | 通过 | 初步可用 | 是 | 保留 from/to/content |
| 英文 fallback | 源码不满足 | 不适用 | 是 | 当前实现回退到任意第一轨 |
| 无字幕跳过 | 通过 | 初步可用 | 是 | 真实样本返回 `available=false`、空 items、退出码 0 |
| 多 P | V0 通过 | 初步可用 | 仅预留 | CLI 只读取第一 P，符合 V0；未来保留 `process_all_parts` 开关 |
| 音频 | 未测试 | 不适用 | 否 | 明确排除 |
| B站 AI summary | 未测试 | 不适用 | 否 | 明确排除 |

聚焦上游测试覆盖 auth、video、favorites、subtitle 和 structured output：`61 passed, 108 deselected`。另加 3 条拾流契约回归测试，全部通过。

## 4. 输出 Schema 与错误契约

成功：

```json
{"ok": true, "schema_version": "1", "data": {}}
```

失败：

```json
{"ok": false, "schema_version": "1", "error": {"code": "not_authenticated", "message": "..."}}
```

实测：

- 公开视频元数据成功时退出码 0；
- 隔离 HOME 下 `status --json` 和 `favorites --json` 返回 `not_authenticated`，退出码 1；
- 沙箱网络不可用时返回 `network_error`，退出码 1；
- 明确允许网络后相同公开视频命令成功，说明错误映射有效；
- JSON 输出未被 Rich 展示内容污染；日志由独立 stderr console 设计承载。
- 目标字幕样本返回 525 个时间戳分段，覆盖 0.08–944.52 秒；轨道为 `ai-zh`、`type: 1`，因此来源记为 `ai`；stdout 可解析且 stderr 为空。
- 无字幕真实样本返回成功 envelope、`available=false`、空 items 和退出码 0；拾流可确定性映射为 `SKIPPED_NO_TRANSCRIPT`。
- 隔离假凭证被自动清理，返回 `not_authenticated`，退出码 1，stderr 未包含假凭证值。
- `BV0000000000` 实测退出码 1，但错误码为 `internal_error`，并暴露底层异常文本 `b'0' is not in list`，不符合 README 宣称的 `not_found` 分类预期。

字幕结构当前只有：

```text
available
format
text
items[]: from, to, content
```

CLI 当前缺少的轨道信息如下。其中 V0 明确要求保留 `source/type`；语言代码用于执行中文、英文、否则跳过的选择规则。其他字段可以暂不进入正式 Schema：

```text
language
language_name
source: human | ai | unknown
upstream_type: 原始 type 值
track_id
part/cid
原始轨道元数据
```

## 5. 风险分类

### B 站上游限制

- 登录态过期；
- 403/412 和反爬；
- 字幕并非所有视频都有；
- 私有、删除或权限受限内容的响应差异。

### bilibili-api-python 限制

- 非官方接口可能随 B 站变化；
- 当前安装元数据与上游 LICENSE 均声明 GPL-3.0-or-later；
- CLI 的 API 稳定性仍受 SDK 行为影响。

### bilibili-cli 自身缺陷

- 只处理 P1；这符合 V0，但未来开启 `process_all_parts` 时必须另行扩展；
- 英文 fallback 规则不正确；
- 人工/AI 字幕来源在 CLI payload 中丢失；
- 收藏夹和视频规范化字段不足；
- 浏览器 Cookie 自动提取在当前 macOS 环境超时。
- 不存在视频的部分 SDK 异常未被规范化，泄漏为 `internal_error`。

### 可由拾流包装解决

- 统一 JSON 解析、超时、重试和错误映射；
- 本地基线与新增差集；
- `SKIPPED_NO_TRANSCRIPT` 状态；
- 补抓视频详情字段；
- 固定目标收藏夹；
- 过滤和脱敏原始响应。
- 为 `internal_error` 设置保守分支，默认不盲目重试，并保留原始错误供诊断。

### 未来开关需要扩展的能力

- 通过现有 `bili video --subtitle*` 命令无法获取全部分 P；
- 当前命令无法精确选择英文轨道并保留轨道语言/来源。

英文选择和人工/AI 来源是 V0 必须补的；全部分 P 只在未来打开 `process_all_parts` 时才需要实现。

### 未直接触发

- 没有故意对真实 B 站 API 制造 403/412；源码把 `-412/412` 映射为 `RateLimitError`，隔离回归测试已验证类型映射；
- 没有破坏真实凭证测试过期行为，而是用临时 HOME 和假凭证完成；
- 目标收藏夹当前只有一页，因此真实多页遍历未触发；page 2 转发和 `has_more` 由上游单元测试覆盖，拾流比较器已经实现循环遍历。

## 6. 复用方式比较

| 方式 | 评价 | 当前建议 |
|---|---|---|
| subprocess 调 CLI | 进程隔离好、JSON 契约清晰，P1 行为符合 V0；但语言选择和人工/AI 来源不足 | 可作为 V0 底层组件，外部必须加包装层 |
| 作为 Python 包导入 | 实测可以导入 auth/client；但内部 API 没有稳定承诺，且直接耦合 GPL 依赖 | 谨慎，不作为首选公共边界 |
| 抽取/复用 client 与 auth | 最容易修正字幕和字段；维护分叉成本更高 | 个人 V0 可行，公开分发前先处理许可证和维护策略 |
| 只借鉴接口设计，自行实现 | 控制力最好；认证和错误治理需要重做 | 作为许可证或维护风险不可接受时的备选 |

## 7. 对拾流 V0 的建议

建议 Adapter 不暴露 CLI 原始结构，而输出拾流自己的对象：

```text
BilibiliAdapter
├── list_folders()
├── list_folder_items(folder_id, page)
├── get_video(bvid)
└── get_transcripts(bvid)
```

V0 的 `get_transcript` 只处理 P1，并执行：

```text
P1：中文字幕 → 英文字幕 → SKIPPED_NO_TRANSCRIPT
```

保存字幕时至少记录：

```yaml
language: zh | en
source: human | ai | unknown
upstream_type: 0 | 1 | null
```

当前真实样本中人工字幕轨道返回 `type: 0`，AI 中文字幕返回 `type: 1`。包装层应做 `0 → human`、`1 → ai` 的显式映射，并对未知新值保留 `unknown` 和原始值，避免以后上游扩展时误分类。

配置层预留：

```yaml
process_all_parts: false
```

V0 固定为 `false`：只保存和总结 P1，不检查其他 P 是否存在字幕，也不生成多 P 摘要。未来开启该开关时，再单独设计多 P 的字幕、失败和摘要语义。

首次扫描只把目标收藏夹当前 BV 集合写为基线，不拉字幕、不生成摘要。后续扫描按本地已见 BV 集合识别新增。

当前 `llm` 收藏夹基线已建立，比较器实测输出：1 页、基线 1 项、当前 1 项、新增 0、移除 0。

## 8. 原始证据索引

- 上游源码：`references/upstreams/bilibili-cli/`
- Spike 规则与快照：`spikes/bilibili-cli-evaluation/README.md`
- 测试矩阵：`spikes/bilibili-cli-evaluation/test-cases.md`
- 可复现命令：`spikes/bilibili-cli-evaluation/commands.md`
- 首次基线：`spikes/bilibili-cli-evaluation/artifacts/llm-baseline.json`
- 脱敏实测摘要：`spikes/bilibili-cli-evaluation/artifacts/probe-evidence.json`
- 基线差集比较器：`spikes/bilibili-cli-evaluation/compare_baseline.py`
- 无效凭证探针：`spikes/bilibili-cli-evaluation/probe_expired_credential.py`
- 契约边界回归测试：`spikes/bilibili-cli-evaluation/test_contract_boundaries.py`
- 关键源码位置：
  - `bili_cli/client.py:get_video_subtitle`
  - `bili_cli/payloads.py:normalize_video_summary`
  - `bili_cli/payloads.py:normalize_subtitle_items`
  - `bili_cli/commands/collections.py:favorites`
  - `bili_cli/auth.py:get_credential/save_credential`
  - `bili_cli/formatter.py:success_payload/error_payload`

除用户明确指定的目标名 `llm` 外，凭证、账号 ID、用户名、其他收藏夹名称和私人视频标题不写入报告。

## 9. 外部来源

- bilibili-cli 官方仓库：<https://github.com/public-clis/bilibili-cli>
- bilibili-cli PyPI 发布页：<https://pypi.org/project/bilibili-cli/>
- bilibili-api-python 官方仓库及许可证：<https://github.com/Nemo2011/bilibili-api/blob/main/LICENSE>

许可证部分是依赖风险提示，不构成法律意见。个人本地使用和对外分发的义务不同；若拾流未来公开发布，应再做一次针对实际依赖/分发方式的许可证审查。
