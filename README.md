# 拾流 Shiliu — Grounded Ask 与字幕证据搜索

拾流是一个本地运行的 Bilibili 收藏阅读、检索和问答系统。V4 在既有
Retrieval、Evidence、Source Version 和时间轴能力上提供两个互补入口：

```text
/ask    基于权威字幕生成有时间戳引用的回答
/search 直接搜索字幕证据，供手动查证与调试
```

## `/ask`：快速回答与深入搜索

`/ask` 使用同一个页面和同一个结构化 `AskResponse` 渲染两种模式：

- **快速回答（默认）**：一次 Query Analysis、有限 Rewrite、字幕检索和
  Grounded Answer，适合明确事实、概念和单主题问题。
- **深入搜索（显式选择）**：先导航可能相关的视频，再逐步搜索或读取原字幕
  窗口，并在确定性 Round、Tool、Context 和时间预算内停止，适合跨视频比较
  或复杂问题。

系统不会自动把 Fast 升级成 Deep。Fast 返回 `partial` 或 `insufficient` 时，
页面会提供“使用深入搜索继续”，保留问题和限定范围；只有用户再次提交才会
运行 Deep。

回答状态：

- `complete`：当前字幕证据覆盖了材料性回答；
- `partial`：只回答了证据支持的部分，限制会单独列出；
- `insufficient`：没有生成事实答案，避免把噪声或不可验证内容包装成成功。

`status` 表示回答充分度，`termination_reason` 则解释运行为何停止，例如证据
已足够、后续搜索重复、没有新证据、预算耗尽、Provider 错误或当前字幕证据
不可用。

## Citation 与事实权威

每个 Answer Block 都绑定本次响应中的 Stable Citation ID。页面用 `[1][2]`
作为本次响应内的阅读编号；点击编号会展开、滚动并高亮对应 Evidence Card。
Evidence Card 展示：

- 视频标题；
- 人工字幕、AI 字幕或 ASR 来源；
- 权威字幕 Quote 与时间范围；
- 当前 Source Version / Timeline / Segment 等折叠身份信息；
- 带 `t=` 时间参数的 Bilibili 跳转链接。

事实权威只来自当前 Source Version 可重建的原字幕或 ASR Segment。标题、
简介、AI 总结、User Notes 和整理稿可以帮助 Deep 导航与选视频，但不会进入
事实 Evidence Card，也不能成为最终 Citation。

`/ask` 与 `/search` 共用薄 `evidence-ui.js` / `evidence-ui.css` 渲染基础，
包括时间格式、字幕来源、证据卡和 Bilibili 跳转；两页仍保留各自的产品状态机。

## Trace 与运行边界

结果页默认显示面向用户的运行摘要，包括模式、耗时、检索/证据数量、停止原因
以及 Deep 的 Decision、Tool、访问范围和被预算包络丢弃的候选数。

开发者 Trace 默认折叠，展开时才请求：

```text
GET /api/ask/traces/{run_id}
```

它展示有界 Action、Observation Summary、Usage、Guard、错误和静态 Deep
Policy Version `v4-deep-policy-v1`，不展示隐藏推理、Secrets、完整 Prompt 或
无界字幕 Corpus。Trace 只保存在当前进程内；服务重启后 404 不影响已经返回的
Answer 和 Citation。

V4 最终答案一次性返回，不做 Token Streaming，也没有服务器端取消、任务队列、
Checkpoint 或 Durable Resume。浏览器离开页面只会忽略旧 Response，不表示
服务器端运行已经取消。真实 Provider 延迟可能达到数十秒或数分钟，Deep 页面
会显示本地真实等待时间，但不会伪造 Round 或 Tool 进度。

## 本地运行

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/shiliu serve
```

默认监听 `127.0.0.1:18520`：

```text
http://127.0.0.1:18520/ask
http://127.0.0.1:18520/search
```

本地状态和内容目录可通过 `SHILIU_STATE_DIR` 与 `SHILIU_CONTENT_DIR` 覆盖。

## 验证

Goal 3 页面、Fast/Deep、Search 与共享 Evidence 定向回归：

```bash
.venv/bin/python -m pytest \
  tests/test_v4_ask_page.py \
  tests/test_v4_ask_contracts.py \
  tests/test_v4_fast_ask_api.py \
  tests/test_v4_deep_search.py \
  tests/test_product_search_api.py \
  tests/test_boundaries_and_web.py \
  tests/test_v1.py
```

默认确定性全套：

```bash
.venv/bin/python -m pytest
```

使用完全虚构的字幕与响应验证 Loading、Complete、Partial、Insufficient、
Citation 定位、Trace 404、Deep Trace 和 `/search` 展开：

```bash
.venv/bin/python scripts/run_v4_goal3_ui_fixture.py
# 打开 http://127.0.0.1:18522/ask 或 /search
```

六条普通 Query Manifest 位于 `eval/v4_goal3_cases.json`。真实 Eval Runner
使用本机数据库临时快照，不修改产品数据库：

```bash
.venv/bin/python scripts/run_v4_goal3_eval.py --mode fast
.venv/bin/python scripts/run_v4_goal3_eval.py --mode deep
```

真实 Eval 会把普通 Query 与有界字幕 Evidence Context 发送到当前配置的
DeepSeek Provider；只应在数据持有者明确授权后运行。结果按 Case 保留合同、
Citation、Identity/Version、预算、Latency、Usage 和人工审阅，不计算生产
SLA 或大型总分。

默认 `pytest` 不调用实时 Provider。需要外部历史 workspace 或本机产品数据库
的测试仍使用 `external_artifact` 标记；实时 Provider 测试使用
`live_provider` 标记并须显式执行。

## 历史基础与数据政策

V0–V3.5 完成了收藏同步、字幕/ASR、内容整理、FTS5/Qwen/RRF Retrieval、
Evidence Identity、Source Version、Timeline 和 Segment 基础。V4 复用这些
技术资产，但不把历史 Candidate Builder、Semantic Judge 或重型 Eval 治理
接入 Ask Runtime。

仓库不提交个人数据库、完整收藏数据、Provider 原始日志、模型缓存、批量中间
Trace 或 Secrets。Goal 3 Eval 结果只保留有界回答与 Quote 摘录。V4 不宣称
生产 SLA、通用 Research Agent，也不包含 V5 个性化或主动行为。
