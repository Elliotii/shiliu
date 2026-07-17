from __future__ import annotations

import argparse
import getpass
import json
from dataclasses import replace
from pathlib import Path

from shiliu.app import Application
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import AppConfig, AppPaths, save_config, store_api_key
from shiliu.db import Database
from shiliu.domain import SyncMode
from shiliu.launchd import install_launch_agent
from shiliu.llm import OpenAICompatibleProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shiliu", description="拾流本地收藏整理工具")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("setup", help="交互式首次设置")
    sync = subcommands.add_parser("sync", help="执行一次同步后退出")
    mode = sync.add_mutually_exclusive_group()
    mode.add_argument("--scheduled", action="store_true", help="定时同步（历史积压 24 小时可处理）")
    mode.add_argument("--manual", action="store_true", help="立即同步，不受暂停时段限制")
    serve = subcommands.add_parser("serve", help="启动本地页面")
    serve.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"], help="V0 只允许本机监听")
    serve.add_argument("--port", type=int, default=18520)
    subcommands.add_parser("install-launchd", help="安装每小时同步任务")
    taxonomy = subcommands.add_parser("taxonomy", help="运行可恢复的 V3 Taxonomy 工作流")
    taxonomy_commands = taxonomy.add_subparsers(dest="taxonomy_command", required=True)
    facet_spike = taxonomy_commands.add_parser("facet-spike", help="运行 10～20 条 Facet 小样本 Spike")
    facet_spike.add_argument("--snapshot-id", type=int, required=True)
    facet_spike.add_argument("--limit", type=int, default=12, choices=range(10, 21))
    facet_spike.add_argument("--seed", type=int, default=42)
    facet_spike.add_argument("--batch-size", type=int, default=4, choices=range(1, 6))
    profile_spike = taxonomy_commands.add_parser(
        "profile-spike", help="运行 Checkpoint 3.7A Classification Profile Spike"
    )
    profile_spike.add_argument("--snapshot-id", type=int, required=True)
    profile_spike.add_argument("--limit", type=int, default=48, choices=range(1, 49))
    profile_spike.add_argument("--seed", type=int, default=73)
    profile_spike.add_argument("--batch-size", type=int, default=12, choices=range(1, 13))
    profile_resume = taxonomy_commands.add_parser(
        "profile-resume", help="恢复指定 Classification Profile Spike"
    )
    profile_resume.add_argument("run_id")
    discovery_spike = taxonomy_commands.add_parser(
        "discovery-spike", help="运行紧凑视图、分批候选发现和试分类 Spike"
    )
    discovery_spike.add_argument("--snapshot-id", type=int, required=True)
    discovery_spike.add_argument("--batch-size", type=int, default=24, choices=range(20, 33))
    discovery_spike.add_argument("--seed", type=int, default=73)
    discovery_spike.add_argument("--limit", type=int)
    discovery_spike.add_argument("--skip-assignment", action="store_true")
    create_taxonomy_run = taxonomy_commands.add_parser(
        "create-run", help="创建数据库持久化的 Taxonomy Run"
    )
    create_taxonomy_run.add_argument("--snapshot-id", type=int, required=True)
    create_taxonomy_run.add_argument("--kind", default="regression")
    create_taxonomy_run.add_argument("--seed", type=int, default=73)
    create_taxonomy_run.add_argument("--batch-size", type=int, default=24, choices=range(20, 33))
    create_taxonomy_run.add_argument("--limit", type=int, default=48)
    create_taxonomy_run.add_argument(
        "--discovery-only", action="store_true", help=argparse.SUPPRESS
    )
    taxonomy_run = taxonomy_commands.add_parser("run", help="执行指定 Taxonomy Run")
    taxonomy_run.add_argument("run_id", type=int)
    taxonomy_resume = taxonomy_commands.add_parser("resume", help="恢复指定 Taxonomy Run")
    taxonomy_resume.add_argument("run_id", type=int)
    taxonomy_status = taxonomy_commands.add_parser("status", help="查看 Taxonomy Run 状态")
    taxonomy_status.add_argument("run_id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "setup":
        return run_setup()
    if arguments.command == "sync":
        app = Application()
        mode = SyncMode.MANUAL if arguments.manual else SyncMode.SCHEDULED
        result = app.sync_service.sync(mode)
        print(result.model_dump_json(indent=2))
        return 0
    if arguments.command == "serve":
        import uvicorn

        from shiliu.web import create_web_app

        uvicorn.run(create_web_app(), host=arguments.host, port=arguments.port)
        return 0
    if arguments.command == "install-launchd":
        app = Application()
        destination = install_launch_agent(app.paths)
        print(destination)
        return 0
    if arguments.command == "taxonomy" and arguments.taxonomy_command == "facet-spike":
        app = Application()
        result = app.taxonomy_facets.run_spike(
            arguments.snapshot_id,
            limit=arguments.limit,
            seed=arguments.seed,
            batch_size=arguments.batch_size,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if arguments.command == "taxonomy" and arguments.taxonomy_command == "profile-spike":
        app = Application()
        result = app.taxonomy_profiles.run_spike(
            arguments.snapshot_id,
            limit=arguments.limit,
            seed=arguments.seed,
            batch_size=arguments.batch_size,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if arguments.command == "taxonomy" and arguments.taxonomy_command == "profile-resume":
        app = Application()
        result = app.taxonomy_profiles.resume_spike(arguments.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if arguments.command == "taxonomy" and arguments.taxonomy_command == "discovery-spike":
        app = Application()
        result = app.taxonomy_discovery_spikes.run_spike(
            arguments.snapshot_id,
            batch_size=arguments.batch_size,
            seed=arguments.seed,
            limit=arguments.limit,
            include_assignment=not arguments.skip_assignment,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if arguments.command == "taxonomy" and arguments.taxonomy_command == "create-run":
        app = Application()
        run_id = app.taxonomy_workflow.create_run(
            snapshot_id=arguments.snapshot_id,
            run_kind=arguments.kind,
            seed=arguments.seed,
            batch_size=arguments.batch_size,
            limit=arguments.limit,
            include_assignment=False,
        )
        print(json.dumps({"run_id": run_id}, ensure_ascii=False, indent=2))
        return 0
    if arguments.command == "taxonomy" and arguments.taxonomy_command in {
        "run", "resume", "status"
    }:
        app = Application()
        if arguments.taxonomy_command == "status":
            result = app.taxonomy_workflow.status(arguments.run_id)
        else:
            result = app.taxonomy_workflow.execute(
                arguments.run_id,
                resume=arguments.taxonomy_command == "resume",
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2


def run_setup() -> int:
    paths = AppPaths.defaults()
    config = AppConfig.default(paths)
    content = input(f"内容目录 [{config.content_dir}]: ").strip() or config.content_dir
    config = replace(config, content_dir=str(Path(content).expanduser()))

    adapter = BilibiliAdapter(Path(config.bili_cli_root))
    login_answer = input("现在进行 B 站二维码登录？[Y/n]: ").strip().lower()
    if login_answer not in {"n", "no"} and adapter.login() != 0:
        raise SystemExit("B 站登录失败")
    folders = adapter.list_favorite_folders()
    if not folders:
        raise SystemExit("没有读取到收藏夹")
    for folder in folders:
        print(f"{folder.get('id')}\t{folder.get('title', '')}\t{folder.get('media_count', 0)} 条")
    favorite_id = int(input("请输入要监控的收藏夹 ID: ").strip())
    selected = next((item for item in folders if int(item.get("id", 0)) == favorite_id), None)
    if selected is None:
        raise SystemExit("收藏夹 ID 不在当前列表中")

    base_url = input("OpenAI-compatible Base URL [https://api.openai.com/v1]: ").strip() or "https://api.openai.com/v1"
    model = input("模型名称: ").strip()
    api_key = getpass.getpass("API Key（只写入 macOS Keychain）: ")
    store_api_key(api_key)
    provider = OpenAICompatibleProvider(base_url=base_url, api_key=api_key, model=model)
    print(f"模型连接测试：{provider.test_connection()}")

    items = adapter.list_favorite_items(favorite_id)
    print(f"当前收藏夹共 {len(items)} 条。首次确认只建立基线，不处理这些历史内容。")
    if input("输入 BASELINE 确认: ").strip() != "BASELINE":
        raise SystemExit("未确认基线，设置已取消")
    config = replace(
        config,
        favorite_id=favorite_id,
        favorite_title=str(selected.get("title", "")),
        llm_base_url=base_url.rstrip("/"),
        llm_model=model,
        baseline_confirmed=True,
    )
    resolved = save_config(config, paths)
    database = Database(resolved.database)
    database.initialize()
    database.establish_baseline([item.bvid for item in items])
    print(f"设置完成，基线 {len(items)} 条，配置保存在 {resolved.config}")
    if input("安装每小时 launchd 同步任务？[Y/n]: ").strip().lower() not in {"n", "no"}:
        install_launch_agent(resolved)
        config = replace(config, auto_sync_enabled=True)
        save_config(config, paths)
        print("launchd 已安装；当前已临时取消静默时段，历史积压和自动处理均可全天运行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
