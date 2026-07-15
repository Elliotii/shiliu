from __future__ import annotations

import asyncio
import html
import json
import re
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from shiliu.app import Application
from shiliu.asr import ParaformerProvider
from shiliu.config import (
    ASR_KEYCHAIN_ACCOUNT,
    ASR_KEYCHAIN_SERVICE,
    load_api_key,
    public_config,
    save_config,
    store_api_key,
)
from shiliu.db import Database
from shiliu.domain import PipelineError, SyncMode
from shiliu.launchd import install_launch_agent
from shiliu.llm import OpenAICompatibleProvider
from shiliu.library import LibraryNotFound, LibraryValidationError
from shiliu.sync import ProcessLock, SyncAlreadyRunning


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


class ProviderRequest(BaseModel):
    base_url: str
    api_key: str = ""
    model: str = ""
    thinking_enabled: bool = True
    reasoning_effort: str = "max"


class SetupDraftRequest(ProviderRequest):
    content_dir: str
    favorite_id: int | None = Field(default=None, gt=0)
    favorite_title: str = ""
    fast_transcript_model: str = ""
    formal_transcript_model: str = ""
    formal_summary_model: str = ""


class SetupRequest(BaseModel):
    content_dir: str
    favorite_id: int = Field(gt=0)
    favorite_title: str = ""
    base_url: str
    api_key: str
    model: str
    fast_transcript_model: str = ""
    formal_transcript_model: str = ""
    formal_summary_model: str = ""
    confirm_baseline: bool
    install_scheduler: bool = True


class FavoriteUrlRequest(BaseModel):
    url: str


class AddFavoriteSourceRequest(FavoriteUrlRequest):
    history_policy: str = "future_only"
    history_limit: int | None = Field(default=None, ge=1)


class MoveFavoriteSourceRequest(BaseModel):
    direction: str


class ASRSettingsRequest(BaseModel):
    base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    api_key: str = ""
    model: str = "paraformer-v2"


class ReadingStateRequest(BaseModel):
    reading_state: str


class NoteRequest(BaseModel):
    content: str


def create_web_app(application: Application | None = None) -> FastAPI:
    web = FastAPI(title="拾流 Shiliu", docs_url=None, redoc_url=None)
    web.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    web.state.core = application or Application()
    web.state.login_process = None
    web.state.background_lock = threading.Lock()
    web.state.background_thread = None
    try:
        with ProcessLock(web.state.core.paths.sync_lock):
            web.state.core.db.recover_stale_sync_runs()
    except SyncAlreadyRunning:
        pass

    @web.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        core = _core(request)
        selected_view = request.query_params.get("view", "feed")
        if selected_view not in {"feed", "marked", "noted", "archived"}:
            selected_view = "feed"
        selected_source = request.query_params.get("source")
        source_db_id = int(selected_source) if selected_source and selected_source.isdigit() else None
        rows = core.db.list_video_cards(view=selected_view, source_db_id=source_db_id)
        notes_by_video = core.db.list_notes_for_videos([int(item["id"]) for item in rows])
        cards = [
            _video_view(core, item, notes=notes_by_video.get(int(item["id"]), []))
            for item in rows
        ]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "videos": cards,
                "latest_sync": core.db.latest_sync_run(),
                "config": public_config(core.config),
                "sources": core.db.list_sources(),
                "selected_source": source_db_id,
                "selected_view": selected_view,
                "history_pending_count": core.db.history_pending_count(),
            },
        )

    @web.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {
                "config": public_config(_core(request).config),
                "sources": _core(request).db.list_sources(),
            },
        )

    @web.get("/videos/{video_id}/transcript", response_class=HTMLResponse)
    async def transcript_page(video_id: int, request: Request) -> HTMLResponse:
        core = _core(request)
        video = core.db.get_video(video_id)
        if video is None:
            raise HTTPException(404, "视频不存在")
        transcript_path = video.get("transcript_path")
        rendered = "<p>整理原文尚未生成。</p>"
        if transcript_path:
            path = core.artifacts.managed_file(transcript_path)
            safe_markdown = html.escape(path.read_text(encoding="utf-8"))
            rendered = markdown.markdown(safe_markdown, extensions=["extra", "sane_lists"])
        return templates.TemplateResponse(
            request,
            "transcript.html",
            {"video": video, "transcript_html": rendered},
        )

    @web.get("/media/{video_id}/cover")
    async def cover(video_id: int, request: Request) -> FileResponse:
        core = _core(request)
        video = core.db.get_video(video_id)
        if not video or not video.get("cover_path"):
            raise HTTPException(404, "没有封面")
        try:
            path = core.artifacts.managed_file(video["cover_path"])
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, "封面文件不可用") from exc
        return FileResponse(path)

    @web.get("/media/{video_id}/raw-subtitle")
    async def raw_subtitle(video_id: int, request: Request) -> FileResponse:
        core = _core(request)
        video = core.db.get_video(video_id)
        if not video or not video.get("raw_subtitle_path"):
            raise HTTPException(404, "没有原始字幕")
        try:
            path = core.artifacts.managed_file(video["raw_subtitle_path"])
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, "字幕文件不可用") from exc
        return FileResponse(path, media_type="text/plain; charset=utf-8", filename=path.name)

    @web.post("/api/sync")
    async def sync_now(request: Request) -> JSONResponse:
        return JSONResponse(_start_background_sync(request.app, _core(request), None), status_code=202)

    @web.post("/api/sources/{source_db_id}/sync")
    async def sync_source(source_db_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        if core.db.get_source(source_db_id) is None:
            raise HTTPException(404, "来源不存在")
        return JSONResponse(
            _start_background_sync(request.app, core, source_db_id),
            status_code=202,
        )

    @web.get("/api/sync-runs/{run_id}")
    async def sync_run_status(run_id: int, request: Request) -> JSONResponse:
        run = _core(request).db.get_sync_run(run_id)
        if run is None:
            raise HTTPException(404, "同步任务不存在")
        return JSONResponse({"ok": True, "run": run})

    @web.post("/api/videos/{video_id}/ignore")
    async def ignore(video_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        if core.db.get_video(video_id) is None:
            raise HTTPException(404, "视频不存在")
        core.db.set_ignored(video_id, True)
        return JSONResponse({"ok": True})

    @web.post("/api/videos/{video_id}/restore")
    async def restore(video_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        if core.db.get_video(video_id) is None:
            raise HTTPException(404, "视频不存在")
        core.db.set_ignored(video_id, False)
        return JSONResponse({"ok": True})

    @web.patch("/api/videos/{video_id}/reading-state")
    async def reading_state(
        video_id: int, payload: ReadingStateRequest, request: Request
    ) -> JSONResponse:
        try:
            video = _core(request).library.set_reading_state(video_id, payload.reading_state)
        except (LibraryNotFound, LibraryValidationError) as exc:
            raise HTTPException(404 if isinstance(exc, LibraryNotFound) else 400, str(exc)) from exc
        return JSONResponse({"ok": True, "video": _library_state(video)})

    @web.post("/api/videos/{video_id}/mark")
    async def mark(video_id: int, request: Request) -> JSONResponse:
        return _library_video_response(_core(request), video_id, "mark", True)

    @web.delete("/api/videos/{video_id}/mark")
    async def unmark(video_id: int, request: Request) -> JSONResponse:
        return _library_video_response(_core(request), video_id, "mark", False)

    @web.post("/api/videos/{video_id}/archive")
    async def archive(video_id: int, request: Request) -> JSONResponse:
        return _library_video_response(_core(request), video_id, "archive", True)

    @web.delete("/api/videos/{video_id}/archive")
    async def unarchive(video_id: int, request: Request) -> JSONResponse:
        return _library_video_response(_core(request), video_id, "archive", False)

    @web.get("/api/videos/{video_id}/notes")
    async def list_notes(video_id: int, request: Request) -> JSONResponse:
        if _core(request).db.get_video(video_id) is None:
            raise HTTPException(404, "视频不存在")
        return JSONResponse({"ok": True, "notes": [_note_view(item) for item in _core(request).db.list_notes(video_id)]})

    @web.post("/api/videos/{video_id}/notes")
    async def add_note(video_id: int, payload: NoteRequest, request: Request) -> JSONResponse:
        try:
            note = _core(request).library.add_note(video_id, payload.content)
        except (LibraryNotFound, LibraryValidationError) as exc:
            raise HTTPException(404 if isinstance(exc, LibraryNotFound) else 400, str(exc)) from exc
        return JSONResponse({"ok": True, "note": _note_view(note)}, status_code=201)

    @web.patch("/api/notes/{note_id}")
    async def update_note(note_id: int, payload: NoteRequest, request: Request) -> JSONResponse:
        try:
            note = _core(request).library.update_note(note_id, payload.content)
        except (LibraryNotFound, LibraryValidationError) as exc:
            raise HTTPException(404 if isinstance(exc, LibraryNotFound) else 400, str(exc)) from exc
        return JSONResponse({"ok": True, "note": _note_view(note)})

    @web.delete("/api/notes/{note_id}")
    async def delete_note(note_id: int, request: Request) -> JSONResponse:
        try:
            note = _core(request).library.delete_note(note_id)
        except LibraryNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        return JSONResponse({"ok": True, "video_id": note["video_id"]})

    @web.post("/api/videos/{video_id}/retry")
    async def retry(video_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        if core.db.get_video(video_id) is None:
            raise HTTPException(404, "视频不存在")
        core.db.reset_failed_stages(video_id)
        try:
            await asyncio.to_thread(core.pipeline.process_video, video_id)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=400)
        return JSONResponse({"ok": True})

    @web.post("/api/videos/{video_id}/refine")
    async def refine(video_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        video = core.db.get_video(video_id)
        if video is None:
            raise HTTPException(404, "视频不存在")
        if video.get("active_revision") != "fast":
            return JSONResponse({"ok": False, "error": "该视频当前不是快速版"}, status_code=400)
        return JSONResponse(
            _start_background_refinement(request.app, core, video_id),
            status_code=202,
        )

    @web.post("/api/videos/{video_id}/asr")
    async def generate_asr(video_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        video = core.db.get_video(video_id)
        if video is None:
            raise HTTPException(404, "视频不存在")
        if video.get("raw_subtitle_path"):
            return JSONResponse({"ok": False, "error": "该视频已经有字幕"}, status_code=400)
        job = core.db.get_asr_job(video_id)
        if job and job["status"] in {"audio_downloading", "uploading", "submitted", "processing"}:
            active = core.db.active_sync_run()
            return JSONResponse(
                {
                    "ok": True,
                    "run_id": int(active["id"]) if active else None,
                    "reused": True,
                    "message": "语音识别已经在进行中",
                },
                status_code=202,
            )
        return JSONResponse(_start_background_asr(request.app, core, video_id), status_code=202)

    @web.post("/api/setup/bilibili-login")
    async def start_bilibili_login(request: Request) -> JSONResponse:
        core = _core(request)
        existing = request.app.state.login_process
        qr_path = core.paths.state_dir / "bilibili-login-qr.png"
        if existing is not None and existing.poll() is None:
            if qr_path.is_file():
                return JSONResponse(
                    {
                        "ok": True,
                        "qr_url": "/api/setup/bilibili-login/qr",
                        "reused": True,
                    }
                )
            return JSONResponse(
                {"ok": False, "error": "登录流程正在启动，请稍后重试"},
                status_code=409,
            )
        try:
            process = await asyncio.to_thread(core.adapter.start_qr_login, qr_path)
        except PipelineError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        request.app.state.login_process = process
        return JSONResponse(
            {
                "ok": True,
                "qr_url": "/api/setup/bilibili-login/qr",
                "reused": False,
            }
        )

    @web.get("/api/setup/bilibili-login/qr")
    async def bilibili_login_qr(request: Request) -> FileResponse:
        path = _core(request).paths.state_dir / "bilibili-login-qr.png"
        if not path.is_file():
            raise HTTPException(404, "二维码尚未生成")
        return FileResponse(path, media_type="image/png")

    @web.get("/api/setup/bilibili-login/status")
    async def bilibili_login_status(request: Request) -> JSONResponse:
        process = request.app.state.login_process
        if process is None:
            return JSONResponse({"status": "not_started"})
        code = process.poll()
        if code is None:
            qr_path = _core(request).paths.state_dir / "bilibili-login-qr.png"
            return JSONResponse(
                {
                    "status": "waiting",
                    "qr_url": "/api/setup/bilibili-login/qr" if qr_path.is_file() else None,
                }
            )
        return JSONResponse({"status": "completed" if code == 0 else "failed"})

    @web.get("/api/setup/folders")
    async def favorite_folders(request: Request) -> JSONResponse:
        try:
            folders = await asyncio.to_thread(_core(request).adapter.list_favorite_folders)
        except PipelineError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "folders": folders})

    @web.post("/api/sources/preview")
    async def preview_source(payload: FavoriteUrlRequest, request: Request) -> JSONResponse:
        core = _core(request)
        try:
            preview = await asyncio.to_thread(core.adapter.preview_favorite_url, payload.url)
        except PipelineError as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "code": exc.code}, status_code=400
            )
        existing = core.db.get_source_by_folder(preview.folder_id)
        return JSONResponse(
            {
                "ok": True,
                "preview": preview.model_dump(mode="json"),
                "already_added": existing is not None,
            }
        )

    @web.post("/api/sources")
    async def add_source(payload: AddFavoriteSourceRequest, request: Request) -> JSONResponse:
        core = _core(request)
        if payload.history_policy not in {"future_only", "latest_n", "all"}:
            return JSONResponse({"ok": False, "error": "历史导入策略无效"}, status_code=400)
        if payload.history_policy == "latest_n" and payload.history_limit is None:
            return JSONResponse({"ok": False, "error": "请填写历史导入数量"}, status_code=400)
        try:
            preview = await asyncio.to_thread(core.adapter.preview_favorite_url, payload.url)
            if core.db.get_source_by_folder(preview.folder_id):
                return JSONResponse({"ok": False, "error": "该收藏夹已经添加"}, status_code=409)
            items = await asyncio.to_thread(core.adapter.list_favorite_items, preview.folder_id)
            source_db_id = core.db.create_favorite_source(
                folder_id=preview.folder_id,
                folder_title=preview.folder_title,
                account_id=preview.account_id,
                account_name=preview.account_name,
                original_url=payload.url,
                media_count=preview.media_count,
                history_policy=payload.history_policy,
                history_limit=payload.history_limit,
            )
            queued = core.db.initialize_source_memberships(source_db_id, items)
        except PipelineError as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "code": exc.code}, status_code=400
            )
        return JSONResponse(
            {
                "ok": True,
                "source_id": source_db_id,
                "baseline_count": len(items),
                "history_queued": queued,
            }
        )

    @web.post("/api/sources/{source_db_id}/pause")
    async def pause_source(source_db_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        if core.db.get_source(source_db_id) is None:
            raise HTTPException(404, "来源不存在")
        core.db.set_source_status(source_db_id, "paused")
        return JSONResponse({"ok": True})

    @web.post("/api/sources/{source_db_id}/resume")
    async def resume_source(source_db_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        if core.db.get_source(source_db_id) is None:
            raise HTTPException(404, "来源不存在")
        core.db.set_source_status(source_db_id, "active")
        return JSONResponse({"ok": True})

    @web.post("/api/sources/{source_db_id}/move")
    async def move_source(
        source_db_id: int,
        payload: MoveFavoriteSourceRequest,
        request: Request,
    ) -> JSONResponse:
        core = _core(request)
        if payload.direction not in {"up", "down"}:
            return JSONResponse({"ok": False, "error": "排序方向无效"}, status_code=400)
        if core.db.get_source(source_db_id) is None:
            raise HTTPException(404, "来源不存在")
        moved = core.db.move_source(source_db_id, payload.direction)
        return JSONResponse({"ok": True, "moved": moved})

    @web.post("/api/sources/{source_db_id}/remove")
    async def remove_source(source_db_id: int, request: Request) -> JSONResponse:
        core = _core(request)
        source = core.db.get_source(source_db_id)
        if source is None:
            raise HTTPException(404, "来源不存在")
        if core.config.favorite_id == int(source["folder_id"]):
            config = replace(core.config, favorite_id=None, favorite_title="")
            save_config(config, core.paths)
            core.config = config
            core.sync_service.favorite_id = None
        core.db.remove_source(source_db_id)
        return JSONResponse({"ok": True})

    @web.post("/api/setup/models")
    async def model_list(payload: ProviderRequest, request: Request) -> JSONResponse:
        try:
            api_key = _resolve_api_key(payload.api_key, _core(request))
        except RuntimeError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        provider = OpenAICompatibleProvider(
            base_url=payload.base_url, api_key=api_key, model=payload.model or "placeholder",
            thinking_enabled=payload.thinking_enabled,
            reasoning_effort=payload.reasoning_effort if payload.thinking_enabled else None,
        )
        try:
            models = await asyncio.to_thread(provider.list_models)
        except PipelineError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "models": models})

    @web.post("/api/setup/test-provider")
    async def test_provider(payload: ProviderRequest, request: Request) -> JSONResponse:
        try:
            api_key = _resolve_api_key(payload.api_key, _core(request))
            provider = OpenAICompatibleProvider(
                base_url=payload.base_url,
                api_key=api_key,
                model=payload.model,
                thinking_enabled=payload.thinking_enabled,
                reasoning_effort=payload.reasoning_effort if payload.thinking_enabled else None,
            )
            result = await asyncio.to_thread(provider.test_connection)
        except (PipelineError, RuntimeError) as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "code": getattr(exc, "code", "api_key_missing")},
                status_code=400,
            )
        return JSONResponse({"ok": True, "result": result})

    @web.post("/api/setup/asr")
    async def save_asr_settings(payload: ASRSettingsRequest, request: Request) -> JSONResponse:
        core = _core(request)
        try:
            if payload.api_key.strip():
                key = payload.api_key.strip()
            else:
                try:
                    key = load_api_key(core.config.asr_api_key_ref)
                except RuntimeError as exc:
                    raise RuntimeError("macOS Keychain 中没有找到 Paraformer API Key") from exc
            provider = ParaformerProvider(
                base_url=payload.base_url, api_key=key, model=payload.model
            )
            await asyncio.to_thread(provider.test_connection)
            if payload.api_key.strip():
                await asyncio.to_thread(
                    store_api_key,
                    payload.api_key,
                    service=ASR_KEYCHAIN_SERVICE,
                    account=ASR_KEYCHAIN_ACCOUNT,
                )
            config = replace(
                core.config,
                asr_base_url=payload.base_url.rstrip("/"),
                asr_model=payload.model,
            )
            save_config(config, core.paths)
            core.config = config
        except (PipelineError, RuntimeError, OSError, ValueError) as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc), "code": getattr(exc, "code", "asr_error")},
                status_code=400,
            )
        return JSONResponse({"ok": True, "result": "Paraformer 连接成功，设置已保存"})

    @web.post("/api/setup/draft")
    async def save_setup_draft(payload: SetupDraftRequest, request: Request) -> JSONResponse:
        core = _core(request)
        try:
            if payload.api_key.strip():
                await asyncio.to_thread(store_api_key, payload.api_key)
            else:
                _resolve_api_key("", core)
            config = replace(
                core.config,
                content_dir=str(Path(payload.content_dir).expanduser()),
                favorite_id=payload.favorite_id,
                favorite_title=payload.favorite_title,
                llm_base_url=payload.base_url.rstrip("/"),
                llm_model=payload.model,
                fast_transcript_model=payload.fast_transcript_model or payload.model,
                formal_transcript_model=payload.formal_transcript_model or payload.model,
                formal_summary_model=payload.formal_summary_model or payload.model,
                formal_reasoning_effort="max",
            )
            save_config(config, core.paths)
            core.config = config
        except (RuntimeError, OSError, ValueError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "api_key_saved": True})

    @web.post("/api/setup/complete")
    async def complete_setup(payload: SetupRequest, request: Request) -> JSONResponse:
        if not payload.confirm_baseline:
            return JSONResponse({"ok": False, "error": "必须确认首次只建立基线"}, status_code=400)
        core = _core(request)
        try:
            api_key = _resolve_api_key(payload.api_key, core)
            provider = OpenAICompatibleProvider(
                base_url=payload.base_url,
                api_key=api_key,
                model=payload.formal_summary_model or payload.model,
                timeout_seconds=600,
                thinking_enabled=True,
                reasoning_effort="max",
            )
            test_result = await asyncio.to_thread(provider.test_connection)
            folders = await asyncio.to_thread(core.adapter.list_favorite_folders)
            selected = next((item for item in folders if int(item.get("id", 0)) == payload.favorite_id), None)
            if selected is None:
                raise PipelineError("收藏夹不在当前账号列表中", code="favorite_not_found", retryable=False)
            items = await asyncio.to_thread(core.adapter.list_favorite_items, payload.favorite_id)
            if payload.api_key.strip():
                await asyncio.to_thread(store_api_key, payload.api_key)
            config = replace(
                core.config,
                content_dir=str(Path(payload.content_dir).expanduser()),
                favorite_id=payload.favorite_id,
                favorite_title=payload.favorite_title or str(selected.get("title", "")),
                llm_base_url=payload.base_url.rstrip("/"),
                llm_model=payload.model,
                fast_transcript_model=payload.fast_transcript_model or payload.model,
                formal_transcript_model=payload.formal_transcript_model or payload.model,
                formal_summary_model=payload.formal_summary_model or payload.model,
                formal_reasoning_effort="max",
                baseline_confirmed=True,
                auto_sync_enabled=payload.install_scheduler,
            )
            new_paths = save_config(config, core.paths)
            database = Database(new_paths.database)
            database.initialize()
            database.establish_baseline([item.bvid for item in items])
            scheduler_path = None
            if payload.install_scheduler:
                scheduler_path = str(await asyncio.to_thread(install_launch_agent, new_paths))
            request.app.state.core = Application()
        except (PipelineError, RuntimeError, OSError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return JSONResponse(
            {
                "ok": True,
                "baseline_count": len(items),
                "connection_result": test_result,
                "scheduler_path": scheduler_path,
            }
        )

    return web


def _core(request: Request) -> Application:
    return request.app.state.core


def _resolve_api_key(submitted: str, core: Application) -> str:
    if submitted.strip():
        return submitted.strip()
    return load_api_key(core.config.api_key_ref)


def _video_view(
    core: Application, video: dict[str, Any], *, notes: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    value = dict(video)
    value["summary"] = None
    value.setdefault("sources", core.db.video_sources(int(video["id"])))
    value["asr_job"] = core.db.get_asr_job(int(video["id"]))
    value["notes"] = [_note_view(item) for item in (notes or [])]
    if video.get("summary_path"):
        revision = str(video.get("active_revision") or "refined")
        json_path = core.artifacts.video_dir(str(video["source_id"])) / f"summary.{revision}.json"
        if not json_path.is_file():
            json_path = core.artifacts.video_dir(str(video["source_id"])) / "summary.json"
        if json_path.is_file():
            try:
                value["summary"] = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                value["summary"] = None
    return value


def _note_view(note: dict[str, Any]) -> dict[str, Any]:
    value = dict(note)
    value["display_updated_at"] = _display_minute(str(note["updated_at"]))
    safe_markdown = html.escape(str(note["content"]))
    rendered = markdown.markdown(
        safe_markdown, extensions=["extra", "sane_lists"]
    )
    rendered = re.sub(r"<img\b[^>]*>", "", rendered, flags=re.IGNORECASE)
    rendered = re.sub(
        r'href="(?!https?://|#)[^"]*"', 'href="#"', rendered, flags=re.IGNORECASE
    )
    value["rendered_html"] = rendered
    return value


def _display_minute(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value[:16].replace("T", " ")


def _library_state(video: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": video["id"],
        "reading_state": video["reading_state"],
        "is_marked": bool(video["is_marked"]),
        "archived": bool(video["archived_at"]),
    }


def _library_video_response(
    core: Application, video_id: int, action: str, enabled: bool
) -> JSONResponse:
    try:
        if action == "mark":
            video = core.library.set_marked(video_id, enabled)
        else:
            video = core.library.set_archived(video_id, enabled)
    except LibraryNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return JSONResponse({"ok": True, "video": _library_state(video)})


def _start_background_sync(app: FastAPI, core: Application, source_db_id: int | None) -> dict[str, Any]:
    with app.state.background_lock:
        active = core.db.active_sync_run()
        if active is not None:
            return {"ok": True, "run_id": int(active["id"]), "reused": True}
        run_id = core.db.start_sync_run("manual", scope_source_id=source_db_id)

        def target() -> None:
            try:
                core.sync_service.sync(
                    SyncMode.MANUAL,
                    source_db_id=source_db_id,
                    run_id=run_id,
                )
            except Exception as exc:
                run = core.db.get_sync_run(run_id)
                if run and run.get("status") == "running":
                    core.db.finish_sync_run(
                        run_id,
                        status="failed",
                        current_phase="failed",
                        error_summary=f"{type(exc).__name__}: {exc}",
                    )

        thread = threading.Thread(target=target, name=f"shiliu-sync-{run_id}", daemon=True)
        app.state.background_thread = thread
        thread.start()
    return {"ok": True, "run_id": run_id, "reused": False}


def _start_background_refinement(
    app: FastAPI, core: Application, video_id: int
) -> dict[str, Any]:
    with app.state.background_lock:
        active = core.db.active_sync_run()
        if active is not None:
            return {"ok": True, "run_id": int(active["id"]), "reused": True}
        run_id = core.db.start_sync_run("manual")
        core.db.update_sync_run(
            run_id,
            current_phase="refinement",
            current_video_id=video_id,
            message="正在立即精修",
        )

        def target() -> None:
            try:
                with ProcessLock(core.paths.sync_lock):
                    changed = core.pipeline.process_refinement(video_id, force=True)
                core.db.finish_sync_run(
                    run_id,
                    status="completed",
                    current_phase="completed",
                    processed_count=int(changed),
                    message="精修完成" if changed else "没有可执行的精修阶段",
                )
            except Exception as exc:
                core.db.finish_sync_run(
                    run_id,
                    status="failed",
                    current_phase="failed",
                    error_summary=f"{type(exc).__name__}: {exc}",
                )

        thread = threading.Thread(target=target, name=f"shiliu-refine-{run_id}", daemon=True)
        app.state.background_thread = thread
        thread.start()
    return {"ok": True, "run_id": run_id, "reused": False}


def _start_background_asr(
    app: FastAPI, core: Application, video_id: int
) -> dict[str, Any]:
    with app.state.background_lock:
        active = core.db.active_sync_run()
        if active is not None:
            return {"ok": True, "run_id": int(active["id"]), "reused": True}
        run_id = core.db.start_sync_run("manual")
        core.db.update_sync_run(
            run_id,
            current_phase="asr",
            current_video_id=video_id,
            message="正在下载音频并生成字幕",
        )

        def target() -> None:
            try:
                with ProcessLock(core.paths.sync_lock):
                    changed = core.pipeline.process_manual_asr(video_id)
                job = core.db.get_asr_job(video_id) or {}
                completed = job.get("status") == "completed"
                core.db.finish_sync_run(
                    run_id,
                    status="completed" if completed else "completed_with_errors",
                    current_phase="completed",
                    processed_count=int(changed),
                    message=(
                        "语音识别及内容处理完成"
                        if completed
                        else str(job.get("last_error_message") or "识别尚未完成，将在后续同步恢复")
                    ),
                )
            except Exception as exc:
                core.db.finish_sync_run(
                    run_id,
                    status="failed",
                    current_phase="failed",
                    error_summary=f"{type(exc).__name__}: {exc}",
                )

        thread = threading.Thread(target=target, name=f"shiliu-asr-{run_id}", daemon=True)
        app.state.background_thread = thread
        thread.start()
    return {"ok": True, "run_id": run_id, "reused": False}
