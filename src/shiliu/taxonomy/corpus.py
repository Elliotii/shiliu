from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import SummaryResult
from shiliu.taxonomy.domain import (
    CardPreview,
    CorpusPreview,
    EvidenceLevel,
    FolderMembership,
    FrozenSnapshot,
    StoredClassificationCard,
    build_discovery_view,
)
from shiliu.taxonomy.repository import TaxonomyRepository


class TaxonomyCorpusService:
    """Build frozen corpus inputs without network or model calls."""

    CARD_SCHEMA_VERSION = "classification-card-v1"

    def __init__(self, db: Database, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts
        self.repository = TaxonomyRepository(db)

    def preview(self, source_ids: list[int]) -> CorpusPreview:
        selected = _unique_ints(source_ids)
        rows = self.repository.load_active_memberships(selected)
        grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        for row in rows:
            key = f"bilibili:{row['bvid']}:p1"
            grouped.setdefault(key, []).append(row)
        cards = [self._build_card(key, memberships) for key, memberships in grouped.items()]
        counts = {level.value: 0 for level in EvidenceLevel}
        for card in cards:
            counts[card.evidence_level.value] += 1
        eligible = sum(int(card.discovery_eligible) for card in cards)
        return CorpusPreview(
            selected_source_ids=selected,
            membership_count=len(rows),
            total_cards=len(cards),
            duplicate_memberships_merged=len(rows) - len(cards),
            discovery_eligible_count=eligible,
            trial_assignment_only_count=len(cards) - eligible,
            evidence_counts=counts,
            cards=cards,
        )

    def freeze(self, source_ids: list[int]) -> FrozenSnapshot:
        preview = self.preview(source_ids)
        snapshot_hash = _hash_json(
            {
                "schema_version": self.CARD_SCHEMA_VERSION,
                "selected_source_ids": sorted(preview.selected_source_ids),
                "card_hashes": sorted(card.card_hash for card in preview.cards),
            }
        )
        return self.repository.freeze(preview, snapshot_hash)

    def _build_card(self, content_key: str, rows: list[dict[str, Any]]) -> CardPreview:
        materialized = next((row for row in rows if row.get("video_id") is not None), rows[0])
        title = _first_text(materialized.get("video_title"), *(row.get("membership_title") for row in rows))
        uploader = _first_text(materialized.get("video_uploader"), *(row.get("membership_uploader") for row in rows))
        description = _description(materialized.get("description"))
        summary = self._load_summary(materialized)
        evidence = _evidence(bool(description), summary is not None)
        memberships = [
            FolderMembership(
                source_id=int(row["source_id"]),
                account_id=int(row["account_id"]) if row.get("account_id") is not None else None,
                account_name=str(row.get("account_name") or ""),
                folder_id=int(row["folder_id"]),
                folder_name=str(row.get("folder_title") or ""),
                favorite_time=int(row["favorite_time"]) if row.get("favorite_time") is not None else None,
                source_position=int(row.get("source_position") or 0),
                first_observed_at=str(row.get("first_observed_at") or ""),
            )
            for row in rows
        ]
        stored = StoredClassificationCard(
            content_key=content_key,
            video_id=int(materialized["video_id"]) if materialized.get("video_id") is not None else None,
            title=title,
            uploader=uploader,
            description=description,
            one_line_summary=summary.conclusion if summary else "",
            key_points=list(summary.key_points) if summary else [],
            projects_tools_models=_unique_texts(item.name for item in summary.entities) if summary else [],
            source_ids=_unique_ints(item.source_id for item in memberships),
            folder_names=_unique_texts(item.folder_name for item in memberships),
            memberships=memberships,
            evidence_level=evidence,
        )
        discovery_view = build_discovery_view(stored)
        return CardPreview(
            content_key=content_key,
            video_id=stored.video_id,
            evidence_level=evidence,
            discovery_eligible=evidence.discovery_eligible,
            selected_revision=(str(materialized.get("active_revision") or "") or None),
            stored_card=stored,
            discovery_view=discovery_view,
            card_hash=_hash_json(stored.model_dump(mode="json")),
            discovery_view_hash=_hash_json(discovery_view.model_dump(mode="json")),
        )

    def _load_summary(self, row: dict[str, Any]) -> SummaryResult | None:
        if not row.get("summary_path"):
            return None
        directory = Path(str(row["summary_path"])).expanduser().resolve().parent
        if not directory.is_relative_to(self.artifacts.videos_dir):
            return None
        revision = str(row.get("active_revision") or "refined")
        for path in (directory / f"summary.{revision}.json", directory / "summary.json"):
            if not path.is_file():
                continue
            try:
                return SummaryResult.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError):
                return None
        return None


def _evidence(has_description: bool, has_summary: bool) -> EvidenceLevel:
    if has_description and has_summary:
        return EvidenceLevel.A
    if has_summary:
        return EvidenceLevel.B
    if has_description:
        return EvidenceLevel.C
    return EvidenceLevel.D


def _description(value: object) -> str:
    text = str(value or "").strip()
    return "" if text == "-" else text


def _first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _unique_texts(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _unique_ints(values: Iterable[int]) -> list[int]:
    result: list[int] = []
    for value in values:
        number = int(value)
        if number not in result:
            result.append(number)
    return result


def _hash_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
