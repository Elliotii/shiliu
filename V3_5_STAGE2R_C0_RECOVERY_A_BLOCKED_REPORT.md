Stage 2R-C0 Recovery A Blocked  
Authorized Source Paths Not Resolved

停止原因：

- 未获准的 Frozen Snapshot DB 精确路径；
- 未获准的 Frozen Artifact Manifest 精确路径；
- 未指定应交给隔离 CLI 的保护资产精确路径；
- 因此无法证明 `protected_source_overlap = 0`，必须 fail-closed；
- 四条 Pilot 文件不足以恢复全部 Source Identity、原始 Query 和 Evidence Question。

审计结果：

- HEAD：`8287c8d92378b87290274d02605cdc704cb8c470`
- 分支：`codex/v3-domain-completion`
- Freeze Manifest SHA-256：符合预期 `d64d72...394`
- 仓库级搜索：未执行
- Quarantine 内容：未打开，仅验证目录存在
- Stage 3/4 内容：未打开
- Reviewer/Provider/LLM/Embedding 调用：全部为 0
- 本轮文件修改：无
- Inventory 和外部 Workspace：未创建
- 既有报告文件：检测到存在，但未打开、覆盖或修改
- 现有 dirty worktree：完整保留

若要解除阻塞，新的专用 Session 必须直接获得 Frozen Snapshot DB、Artifact Manifest、全部保护输入的精确路径，以及必要的安全 Pilot Coverage 投影；不得通过仓库搜索发现这些资产。
