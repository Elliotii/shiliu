from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from shiliu.domain import SubtitleSegment, SummaryResult, TranscriptResult, VideoBundle


URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"'，。；：！？、]+")


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in URL_PATTERN.findall(text or ""):
        url = match.rstrip(".,;:!?，。；：！？")
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


class ArtifactStore:
    def __init__(self, videos_dir: Path) -> None:
        self.videos_dir = videos_dir.resolve()
        self.videos_dir.mkdir(parents=True, exist_ok=True)

    def video_dir(self, bvid: str) -> Path:
        if not re.fullmatch(r"BV[0-9A-Za-z]{10}", bvid):
            raise ValueError("无效 BV 号")
        path = self.videos_dir / bvid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_metadata(self, bundle: VideoBundle) -> Path:
        path = self.video_dir(bundle.bvid) / "metadata.json"
        self.write_json(path, bundle.model_dump(mode="json", by_alias=True))
        return path

    def save_raw_subtitle(self, bvid: str, segments: list[SubtitleSegment]) -> tuple[Path, Path]:
        directory = self.video_dir(bvid)
        json_path = directory / "subtitle-raw.json"
        text_path = directory / "subtitle-raw.txt"
        self.write_json(
            json_path,
            [segment.model_dump(mode="json", by_alias=True) for segment in segments],
        )
        lines = [
            f"[{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}] {segment.content}"
            for segment in segments
        ]
        self.write_text(text_path, "\n".join(lines) + ("\n" if lines else ""))
        return json_path, text_path

    def save_asr_raw(self, bvid: str, payload: Any) -> Path:
        path = self.video_dir(bvid) / "asr-raw.json"
        self.write_json(path, payload)
        return path

    def save_transcript(
        self, bvid: str, transcript: TranscriptResult, *, revision: str | None = None
    ) -> tuple[Path, Path]:
        directory = self.video_dir(bvid)
        suffix = f".{revision}" if revision else ""
        json_path = directory / f"transcript{suffix}.json"
        markdown_path = directory / f"transcript{suffix}.md"
        self.write_json(json_path, transcript.model_dump(mode="json"))
        self.write_text(markdown_path, render_transcript_markdown(transcript))
        return json_path, markdown_path

    def save_summary(
        self, bvid: str, summary: SummaryResult, *, revision: str | None = None
    ) -> tuple[Path, Path]:
        directory = self.video_dir(bvid)
        suffix = f".{revision}" if revision else ""
        json_path = directory / f"summary{suffix}.json"
        markdown_path = directory / f"summary{suffix}.md"
        self.write_json(json_path, summary.model_dump(mode="json"))
        self.write_text(markdown_path, render_summary_markdown(summary))
        return json_path, markdown_path

    def save_generation_provenance(
        self,
        bvid: str,
        artifact_kind: str,
        metadata: dict[str, Any],
        *,
        revision: str | None = None,
    ) -> Path:
        if artifact_kind not in {"transcript", "summary"}:
            raise ValueError("不支持的生成 Artifact 类型")
        suffix = f".{revision}" if revision else ""
        path = self.video_dir(bvid) / f"{artifact_kind}{suffix}.provenance.json"
        self.write_json(path, metadata)
        return path

    def load_generation_provenance(
        self, bvid: str, artifact_kind: str, *, revision: str | None = None
    ) -> dict[str, Any]:
        suffix = f".{revision}" if revision else ""
        path = self.video_dir(bvid) / f"{artifact_kind}{suffix}.provenance.json"
        if not path.exists():
            return {
                "provenance_status": "legacy_unknown",
                "provider": "unknown",
                "model": "unknown",
                "prompt_version": "unknown",
                "schema": "unknown",
                "generated_at": None,
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def load_transcript(self, bvid: str, *, revision: str | None = None) -> TranscriptResult:
        suffix = f".{revision}" if revision else ""
        path = self.video_dir(bvid) / f"transcript{suffix}.json"
        return TranscriptResult.model_validate_json(path.read_text(encoding="utf-8"))

    def load_summary(self, bvid: str, *, revision: str | None = None) -> SummaryResult:
        suffix = f".{revision}" if revision else ""
        path = self.video_dir(bvid) / f"summary{suffix}.json"
        return SummaryResult.model_validate_json(path.read_text(encoding="utf-8"))

    def download_cover(self, bvid: str, cover_url: str | None) -> Path | None:
        if not cover_url:
            return None
        url = "https:" + cover_url if cover_url.startswith("//") else cover_url
        path = self.video_dir(bvid) / "cover.jpg"
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": "Mozilla/5.0 Shiliu/0.1"})
                response.raise_for_status()
                if not response.content:
                    return None
                self.write_bytes(path, response.content)
        except (httpx.HTTPError, OSError):
            return None
        return path

    def managed_file(self, candidate: str | Path) -> Path:
        resolved = Path(candidate).expanduser().resolve()
        if not resolved.is_relative_to(self.videos_dir):
            raise ValueError("文件不在拾流内容目录中")
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        return resolved

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        ArtifactStore.write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def write_text(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def write_bytes(path: Path, value: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(value)
        temporary.replace(path)


def format_timestamp(seconds: float | int) -> str:
    milliseconds = round(float(seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def render_transcript_markdown(transcript: TranscriptResult) -> str:
    chunks: list[str] = []
    for section in transcript.sections:
        timestamp = f" · {format_timestamp(section.start_seconds)}" if section.start_seconds is not None else ""
        chunks.append(f"## {section.title}{timestamp}")
        chunks.extend(section.paragraphs)
    return "\n\n".join(chunks).strip() + "\n"


def render_summary_markdown(summary: SummaryResult) -> str:
    chunks = ["## 一句话结论", summary.conclusion, "## 核心观点"]
    chunks.append("\n".join(f"- {point}" for point in summary.key_points))
    chunks.extend(["## 详细笔记", "\n\n".join(summary.detailed_notes)])
    if summary.important_chapters:
        chunks.append("## 重要章节")
        chunks.append(
            "\n".join(
                f"- `{format_timestamp(item.start_seconds)}` {item.title}"
                + (f"：{item.summary}" if item.summary else "")
                for item in summary.important_chapters
            )
        )
    if summary.entities:
        chunks.append("## 涉及的模型、工具与项目")
        chunks.append(
            "\n".join(
                f"- **{item.name}**" + (f"（{item.kind}）" if item.kind else "") + (f"：{item.note}" if item.note else "")
                for item in summary.entities
            )
        )
    if summary.action_items:
        chunks.append("## 可执行事项")
        chunks.append(
            "\n".join(
                f"- {item.action}" + (f"：{item.rationale}" if item.rationale else "")
                for item in summary.action_items
            )
        )
    if summary.limitations:
        chunks.extend(["## 局限、争议与时效性", "\n".join(f"- {item}" for item in summary.limitations)])
    if summary.related_links:
        chunks.extend(["## 相关链接", "\n".join(f"- [{url}]({url})" for url in summary.related_links)])
    return "\n\n".join(chunks).strip() + "\n"
