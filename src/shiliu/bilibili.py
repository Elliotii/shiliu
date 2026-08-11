from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from shiliu.domain import FavoriteItem, FavoriteScan, FavoriteSourcePreview, PipelineError, VideoBundle


class BilibiliAdapter:
    """Read-only wrapper around the evaluated bilibili-cli snapshot."""

    def __init__(self, cli_root: Path, *, timeout_seconds: int = 60) -> None:
        self.cli_root = cli_root.resolve()
        self.python = self.cli_root / ".venv" / "bin" / "python"
        self.executable = self.cli_root / ".venv" / "bin" / "bili"
        self.timeout_seconds = timeout_seconds

    def _ensure_runtime(self) -> None:
        if not self.python.is_file() or not self.executable.is_file():
            raise PipelineError(
                "找不到已验证的 bilibili-cli 运行环境",
                code="bilibili_cli_missing",
                retryable=False,
            )

    def list_favorite_folders(self) -> list[dict[str, Any]]:
        data = self._run_bridge(["favorite-folders"])
        if not isinstance(data, list):
            raise PipelineError("收藏夹列表返回格式无效", code="upstream_schema", retryable=True)
        return [item for item in data if isinstance(item, dict)]

    def list_favorite_items(self, favorite_id: int) -> list[FavoriteItem]:
        scan = self.list_favorite_scan(favorite_id)
        if not scan.is_complete:
            raise PipelineError(
                "收藏夹分页结果不完整，已拒绝作为权威快照",
                code="incomplete_snapshot",
                retryable=True,
            )
        return scan.items

    def list_favorite_scan(self, favorite_id: int) -> FavoriteScan:
        data = self._run_bridge(
            ["favorites-scan", str(favorite_id)],
            timeout_seconds=max(self.timeout_seconds, 900),
        )
        if not isinstance(data, dict):
            raise PipelineError("收藏夹分页返回格式无效", code="upstream_schema", retryable=True)
        items: list[FavoriteItem] = []
        remote_total = _int_or_none(data.get("remote_total"))
        raw_item_count = 0
        invalid_item_count = 0
        for raw in data.get("items", []) or []:
            raw_item_count += 1
            if not isinstance(raw, dict) or not raw.get("bvid"):
                invalid_item_count += 1
                continue
            upper = raw.get("upper") or {}
            uploader = upper.get("name", "") if isinstance(upper, dict) else str(upper)
            items.append(
                FavoriteItem(
                    bvid=str(raw["bvid"]),
                    title=str(raw.get("title", "")),
                    uploader=str(uploader),
                    duration_seconds=_duration_seconds(
                        raw.get("duration_seconds", raw.get("duration", 0))
                    ),
                    favorite_time=_int_or_none(
                        raw.get("fav_time") or raw.get("favorite_time")
                    ),
                )
            )
        pages_fetched = max(1, int(data.get("pages_fetched") or 1))
        count_matches = remote_total is None or raw_item_count == remote_total
        return FavoriteScan(
            items=items,
            remote_total=remote_total,
            is_complete=invalid_item_count == 0 and count_matches,
            pages_fetched=pages_fetched,
            raw_item_count=raw_item_count,
        )

    def preview_favorite_url(self, url: str) -> FavoriteSourcePreview:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
            "space.bilibili.com",
            "www.bilibili.com",
        }:
            raise PipelineError(
                "请输入 bilibili.com 的公开收藏夹链接",
                code="invalid_favorite_url",
                retryable=False,
            )
        values = parse_qs(parsed.query)
        try:
            folder_id = int((values.get("fid") or [""])[0])
        except ValueError as exc:
            raise PipelineError(
                "收藏夹链接缺少合法 fid",
                code="invalid_favorite_url",
                retryable=False,
            ) from exc
        if folder_id <= 0:
            raise PipelineError(
                "收藏夹链接缺少合法 fid",
                code="invalid_favorite_url",
                retryable=False,
            )
        data = self._run_bridge(["favorite-preview", str(folder_id)])
        if not isinstance(data, dict) or not data.get("folder_id"):
            raise PipelineError("收藏夹预览返回格式无效", code="upstream_schema", retryable=True)
        data["original_url"] = url.strip()
        return FavoriteSourcePreview.model_validate(data)

    def fetch_video_bundle(self, bvid: str) -> VideoBundle:
        data = self._run_bridge(["fetch-video", bvid])
        if not isinstance(data, dict):
            raise PipelineError("视频详情返回格式无效", code="upstream_schema", retryable=True)
        return VideoBundle.model_validate(data)

    def download_audio(self, bvid: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._run_bridge(
            ["download-audio", bvid, str(output_path)], timeout_seconds=360
        )
        if not isinstance(data, dict) or int(data.get("bytes") or 0) <= 0:
            raise PipelineError("音频下载结果无效", code="audio_download_empty", retryable=True)
        if not output_path.is_file():
            raise PipelineError("音频文件没有落盘", code="audio_download_missing", retryable=True)
        return output_path

    def _run_bridge(self, arguments: list[str], *, timeout_seconds: int | None = None) -> Any:
        self._ensure_runtime()
        try:
            result = subprocess.run(
                [str(self.python), "-m", "shiliu.bilibili_bridge", *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds or self.timeout_seconds,
                env=self._bridge_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise PipelineError("B 站只读桥超时", code="upstream_timeout", retryable=True) from exc
        payload = _parse_json_output(result.stdout)
        if result.returncode != 0 or not payload.get("ok"):
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = str(error.get("code", "upstream_error"))
            message = _bounded_error_message(
                str(error.get("message", result.stderr.strip() or "B 站读取失败"))
            )
            raise PipelineError(
                message,
                code=code,
                retryable=code in {"upstream_retryable", "upstream_timeout", "upstream_error"},
            )
        return payload.get("data")

    def login(self) -> int:
        self._ensure_runtime()
        return subprocess.call([str(self.executable), "login"])

    def start_qr_login(self, qr_path: Path) -> subprocess.Popen[str]:
        self._ensure_runtime()
        if qr_path.exists():
            qr_path.unlink()
        env = self._bridge_env()
        process = subprocess.Popen(
            [str(self.python), "-m", "shiliu.bilibili_bridge", "qr-login-file", str(qr_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if qr_path.is_file():
                return process
            if process.poll() is not None:
                raise PipelineError("无法生成登录二维码", code="qr_login_failed", retryable=True)
            time.sleep(0.1)
        process.terminate()
        raise PipelineError("生成登录二维码超时", code="qr_login_timeout", retryable=True)

    def _run_cli(self, arguments: list[str]) -> dict[str, Any]:
        self._ensure_runtime()
        try:
            result = subprocess.run(
                [str(self.executable), *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise PipelineError("B 站命令超时", code="upstream_timeout", retryable=True) from exc
        payload = _parse_json_output(result.stdout)
        if result.returncode != 0 or payload.get("ok") is False:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = str(error.get("code", "upstream_error"))
            message = str(error.get("message", result.stderr.strip() or "B 站命令失败"))
            raise PipelineError(
                message,
                code=code,
                retryable=code not in {"authentication_required", "invalid_input"},
            )
        return payload

    def _bridge_env(self) -> dict[str, str]:
        project_src = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        python_path = [str(project_src), str(self.cli_root)]
        if env.get("PYTHONPATH"):
            python_path.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(python_path)
        return env


def _parse_json_output(output: str) -> dict[str, Any]:
    text = output.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineError("上游命令没有返回合法 JSON", code="upstream_schema", retryable=True) from exc
    return value if isinstance(value, dict) else {"data": value}


def _bounded_error_message(value: str, limit: int = 600) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _duration_seconds(value: object) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        parts = value.strip().split(":")
        try:
            numbers = [int(part) for part in parts]
        except ValueError:
            return 0
        if len(numbers) == 2:
            return max(0, numbers[0] * 60 + numbers[1])
        if len(numbers) == 3:
            return max(0, numbers[0] * 3600 + numbers[1] * 60 + numbers[2])
    return 0
