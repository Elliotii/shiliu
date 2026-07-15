from __future__ import annotations

import json
from typing import Any

from shiliu.db import Database, utc_now
from shiliu.taxonomy.domain import CorpusPreview, FrozenSnapshot


class TaxonomyRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def selectable_sources(self) -> list[dict[str, Any]]:
        return [
            source
            for source in self.db.list_sources()
            if source["status"] in {"active", "cooldown", "paused"}
        ]

    def load_active_memberships(self, source_ids: list[int]) -> list[dict[str, Any]]:
        if not source_ids:
            raise ValueError("至少选择一个收藏夹")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("收藏夹选择中存在重复项")
        placeholders = ",".join("?" for _ in source_ids)
        with self.db.connect() as connection:
            source_count = connection.execute(
                f"SELECT COUNT(*) FROM favorite_sources WHERE status IN ('active', 'cooldown', 'paused') AND id IN ({placeholders})",
                source_ids,
            ).fetchone()[0]
            if int(source_count) != len(source_ids):
                raise ValueError("所选收藏夹不存在或未启用")
            rows = connection.execute(
                f"""
                SELECT m.source_id, m.bvid, m.video_id,
                       m.title AS membership_title,
                       m.uploader AS membership_uploader,
                       m.favorite_time, m.source_position, m.first_observed_at,
                       s.account_id, s.account_name, s.folder_id, s.folder_title,
                       v.title AS video_title, v.uploader AS video_uploader,
                       v.description, v.summary_path, v.active_revision
                FROM video_source_memberships m
                JOIN favorite_sources s ON s.id=m.source_id
                LEFT JOIN videos v ON v.id=m.video_id
                WHERE m.removed_at IS NULL
                  AND s.status IN ('active', 'cooldown', 'paused')
                  AND m.source_id IN ({placeholders})
                ORDER BY s.sort_order, m.source_position, m.bvid
                """,
                source_ids,
            ).fetchall()
        return [dict(row) for row in rows]

    def freeze(self, preview: CorpusPreview, snapshot_hash: str) -> FrozenSnapshot:
        if preview.total_cards == 0:
            raise ValueError("不能创建空快照")
        now = utc_now()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM taxonomy_corpus_snapshots WHERE snapshot_hash=?",
                (snapshot_hash,),
            ).fetchone()
            if existing is not None:
                return self._snapshot_from_row(dict(existing), reused=True)
            cursor = connection.execute(
                """
                INSERT INTO taxonomy_corpus_snapshots(
                    selected_source_ids_json, membership_count, content_count,
                    duplicate_memberships_merged, discovery_eligible_count,
                    trial_assignment_only_count, evidence_counts_json,
                    snapshot_hash, created_at, frozen_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _compact_json(preview.selected_source_ids),
                    preview.membership_count,
                    preview.total_cards,
                    preview.duplicate_memberships_merged,
                    preview.discovery_eligible_count,
                    preview.trial_assignment_only_count,
                    _compact_json(preview.evidence_counts),
                    snapshot_hash,
                    now,
                    now,
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            for ordinal, card in enumerate(preview.cards):
                connection.execute(
                    """
                    INSERT INTO taxonomy_classification_cards(
                        snapshot_id, content_key, video_id, platform,
                        source_content_id, ordinal, evidence_level,
                        discovery_eligible, selected_revision, stored_card_json,
                        discovery_view_json, card_hash, discovery_view_hash, created_at
                    ) VALUES(?, ?, ?, 'bilibili', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        card.content_key,
                        card.video_id,
                        card.content_key.split(":", 2)[1],
                        ordinal,
                        card.evidence_level.value,
                        int(card.discovery_eligible),
                        card.selected_revision,
                        _compact_json(card.stored_card.model_dump(mode="json")),
                        _compact_json(card.discovery_view.model_dump(mode="json")),
                        card.card_hash,
                        card.discovery_view_hash,
                        now,
                    ),
                )
        return FrozenSnapshot(
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot_hash,
            reused=False,
            selected_source_ids=preview.selected_source_ids,
            membership_count=preview.membership_count,
            total_cards=preview.total_cards,
            duplicate_memberships_merged=preview.duplicate_memberships_merged,
            discovery_eligible_count=preview.discovery_eligible_count,
            trial_assignment_only_count=preview.trial_assignment_only_count,
            evidence_counts=preview.evidence_counts,
            created_at=now,
        )

    def list_snapshots(self) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM taxonomy_corpus_snapshots ORDER BY id DESC"
            ).fetchall()
        return [self._snapshot_row(dict(row)) for row in rows]

    def get_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            snapshot = connection.execute(
                "SELECT * FROM taxonomy_corpus_snapshots WHERE id=?", (snapshot_id,)
            ).fetchone()
            if snapshot is None:
                return None
            cards = connection.execute(
                """
                SELECT content_key, video_id, ordinal, evidence_level,
                       discovery_eligible, selected_revision, stored_card_json,
                       discovery_view_json, card_hash, discovery_view_hash
                FROM taxonomy_classification_cards
                WHERE snapshot_id=? ORDER BY ordinal
                """,
                (snapshot_id,),
            ).fetchall()
        result = self._snapshot_row(dict(snapshot))
        result["cards"] = [
            {
                "content_key": str(row["content_key"]),
                "video_id": row["video_id"],
                "ordinal": int(row["ordinal"]),
                "evidence_level": str(row["evidence_level"]),
                "discovery_eligible": bool(row["discovery_eligible"]),
                "selected_revision": row["selected_revision"],
                "stored_card": json.loads(row["stored_card_json"]),
                "discovery_view": json.loads(row["discovery_view_json"]),
                "card_hash": str(row["card_hash"]),
                "discovery_view_hash": str(row["discovery_view_hash"]),
            }
            for row in cards
        ]
        return result

    def candidate_rows(self, snapshot_id: int) -> list[dict[str, str]]:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise LookupError("快照不存在")
        return [
            {
                "content_key": card["content_key"],
                "title": card["stored_card"]["title"],
                "uploader": card["stored_card"]["uploader"],
                "evidence_level": card["evidence_level"],
            }
            for card in snapshot["cards"]
        ]

    @staticmethod
    def _snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
        row["selected_source_ids"] = json.loads(row.pop("selected_source_ids_json"))
        row["evidence_counts"] = json.loads(row.pop("evidence_counts_json"))
        return row

    @classmethod
    def _snapshot_from_row(cls, row: dict[str, Any], *, reused: bool) -> FrozenSnapshot:
        value = cls._snapshot_row(row)
        return FrozenSnapshot(
            snapshot_id=int(value["id"]),
            snapshot_hash=str(value["snapshot_hash"]),
            reused=reused,
            selected_source_ids=value["selected_source_ids"],
            membership_count=int(value["membership_count"]),
            total_cards=int(value["content_count"]),
            duplicate_memberships_merged=int(value["duplicate_memberships_merged"]),
            discovery_eligible_count=int(value["discovery_eligible_count"]),
            trial_assignment_only_count=int(value["trial_assignment_only_count"]),
            evidence_counts=value["evidence_counts"],
            created_at=str(value["created_at"]),
        )


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
