# 可复现命令与结果

以下命令均在 `$REPO_ROOT` 下执行。真实凭证参数和 Cookie 从未出现在命令行中。

## 上游快照

```bash
git clone https://github.com/public-clis/bilibili-cli.git references/upstreams/bilibili-cli
git -C references/upstreams/bilibili-cli rev-parse HEAD
git -C references/upstreams/bilibili-cli describe --tags --always
```

结果：commit `dbe28551930df43b633baa52e9639832aeada967`，`v0.6.2-4-gdbe2855`。tag 后仅有文档/CI 变化。

## 环境与安装

```bash
<bundled-python-3.12> -m venv references/upstreams/bilibili-cli/.venv
references/upstreams/bilibili-cli/.venv/bin/python -m pip install -e 'references/upstreams/bilibili-cli[dev]'
references/upstreams/bilibili-cli/.venv/bin/bili --version
```

结果：`bili, version 0.6.2`。正式拾流不需要 `[dev]` 或 `[audio]`；这里的 dev extra 只用于运行上游测试。

## 聚焦测试

```bash
references/upstreams/bilibili-cli/.venv/bin/python -m pytest -q \
  references/upstreams/bilibili-cli/tests/test_auth.py \
  references/upstreams/bilibili-cli/tests/test_subtitle.py \
  references/upstreams/bilibili-cli/tests/test_client.py \
  references/upstreams/bilibili-cli/tests/test_cli.py \
  spikes/bilibili-cli-evaluation/test_contract_boundaries.py \
  -k 'status or login or video or favorites or structured_output or version or http_412 or v0_subtitle or current_fallback'
```

结果：`64 passed, 108 deselected`。

## 认证

```bash
HOME=<empty-temp-home> references/upstreams/bilibili-cli/.venv/bin/bili status --json
references/upstreams/bilibili-cli/.venv/bin/bili login
references/upstreams/bilibili-cli/.venv/bin/bili status --json
references/upstreams/bilibili-cli/.venv/bin/python spikes/bilibili-cli-evaluation/probe_expired_credential.py
```

结果：

- 空 HOME：`not_authenticated`，退出码 1；
- 浏览器 Cookie 自动提取：15 秒超时；
- 二维码登录：成功；
- 新进程验证：authenticated；
- 隔离无效凭证：被清理，`not_authenticated`，测试 secret 未进入 stderr。

## 收藏夹与基线

```bash
references/upstreams/bilibili-cli/.venv/bin/bili favorites --json
references/upstreams/bilibili-cli/.venv/bin/bili favorites <LLM_FOLDER_ID> --page 1 --json
references/upstreams/bilibili-cli/.venv/bin/python spikes/bilibili-cli-evaluation/compare_baseline.py
```

结果：目标 `llm` 首次基线 1 项；连续扫描稳定；当前新增 0、移除 0。

## 视频与字幕

```bash
references/upstreams/bilibili-cli/.venv/bin/bili video BV1ABcsztEcY --json
references/upstreams/bilibili-cli/.venv/bin/bili video BV0000000000 --json
references/upstreams/bilibili-cli/.venv/bin/python spikes/bilibili-cli-evaluation/summarize_video_probe.py BV1FPTT6uEd2
references/upstreams/bilibili-cli/.venv/bin/python spikes/bilibili-cli-evaluation/summarize_video_probe.py BV1MW4y1z7Tk
references/upstreams/bilibili-cli/.venv/bin/python spikes/bilibili-cli-evaluation/inspect_video_tracks.py BV15t4y1m7Eo
references/upstreams/bilibili-cli/.venv/bin/python spikes/bilibili-cli-evaluation/inspect_video_tracks.py BV1QA411N7Vu
```

结果：

- 公开视频元数据合法；
- 格式合法但不存在的 BV 错误分类不正确：返回 `internal_error` 和底层异常，而非 `not_found`；
- 目标样本字幕 525 段，覆盖 0.08–944.52 秒；
- 无字幕样本 `available=false`，退出码 0；
- 5P 和 8P 样本证明 CLI 当前只读取第一 P，符合拾流 V0；SDK 能看到其他 P，可为未来 `process_all_parts` 开关提供实现路径。

## 上游修改

没有修改 `references/upstreams/bilibili-cli` 的跟踪文件；`git status --short` 为空。所有探针和回归测试都位于 `spikes/bilibili-cli-evaluation/`。
