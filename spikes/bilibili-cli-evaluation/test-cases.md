# 测试用例

| ID | 用例 | 预期 | 当前结果 |
|---|---|---|---|
| ENV-01 | 源码安装 | Python >= 3.10 可安装，不安装 audio extra | 部分完成；源码可安装，开发 extra 会连带安装 `av`，正式安装不需要 |
| UNIT-01 | 聚焦单元测试 | auth/video/favorites/subtitle/structured output 通过 | 61 passed, 108 deselected |
| AUTH-01 | 空 HOME 状态 | JSON `not_authenticated`，退出码 1 | 通过 |
| AUTH-02 | 浏览器 Cookie 自动提取 | 在合理时间内成功或明确失败 | 15 秒超时并明确提示改用二维码 |
| AUTH-03 | 二维码登录 | 登录成功并保存凭证 | 通过 |
| AUTH-04 | 凭证持久化 | 新进程继续登录 | 通过 |
| AUTH-05 | 凭证权限 | 文件权限 0600 | 通过 |
| AUTH-06 | 无效凭证 | 清理无效凭证并返回结构化错误 | 通过；隔离 HOME，`not_authenticated`，未泄露测试 secret |
| FAV-01 | 收藏夹列表 | 合法 JSON envelope | 通过，共读取 10 个文件夹；证据不保存私人名称 |
| FAV-02 | 指定收藏夹第一页 | 返回 folder_id/page/has_more/items | 通过，目标 `llm` |
| FAV-03 | 收藏夹分页 | 能遍历至 has_more=false | 通过，当前第一页即 `has_more=false`；多页真实样本未触发 |
| FAV-04 | 连续两次扫描 | BV 集合稳定，适合建立基线 | 通过，两次均返回同一个 BV |
| VIDEO-01 | 公开视频元数据 | 合法 JSON、退出码 0 | 通过，样本 `BV1ABcsztEcY` |
| VIDEO-02 | 视频字段覆盖 | BV、aid、标题、简介、UP、时长、URL | 通过；缺发布时间、封面、分 P 列表 |
| SUB-01 | 中文字幕和时间戳 | `available=true`，保留 from/to/content | 通过，样本 `BV1ABcsztEcY` |
| SUB-02 | 无字幕 | 可稳定映射为 `SKIPPED_NO_TRANSCRIPT` | 通过，公开样本 `BV1MW4y1z7Tk` |
| SUB-03 | 中文优先、英文次选 | 只允许中文或英文 | 源码不满足；无中文时选择任意第一轨 |
| SUB-04 | 多 P 的 V0 边界 | 默认只处理 P1 | 通过；源码使用 `pages[0]`，符合 V0；未来 `process_all_parts` 开关不在本轮实现 |
| SUB-05 | 字幕来源 | 保留人工/AI/未知及上游原始 type | CLI payload 不满足；SDK 轨道元数据包含 type，需包装层映射 |
| OUT-01 | 成功 envelope | `ok/schema_version/data` | 通过 |
| OUT-02 | 失败 envelope | `ok/schema_version/error`，退出码非零 | 通过 |
| OUT-03 | stdout/stderr 分离 | JSON stdout 不被日志污染 | 通过；目标样本 stdout 可解析且 stderr 为空 |
| ERR-01 | HTTP 412 映射 | `rate_limited` / RateLimitError | 隔离回归测试通过；未故意对真实 API 触发 412 |
| ERR-02 | 格式合法但不存在的 BV | 应返回 `not_found` | 不通过；实测返回 `internal_error` 和底层异常消息 |
| DELTA-01 | 基线差集 | 遍历分页，仅返回基线后新增 BV | 通过；当前新增和移除均为空 |

## 专门边界测试

`test_contract_boundaries.py`：3 passed。

- 证明当前字幕函数只请求第一个 `cid`，符合 V0；
- 证明轨道顺序为日文、英文且没有中文时，当前实现错误选择日文；
- 证明 SDK 的 `-412` 响应映射为 `RateLimitError`。
