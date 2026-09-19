from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from shiliu.db import Database
from shiliu.taxonomy.corpus import TaxonomyCorpusService


POLICY_VERSION = "v5-c-stage4-bounded-assistance-v1"
CONTROL_PREFIX = "assistance.control."
MASTERY_STATES = {"learned", "understood", "mastered", "familiar"}
OBSERVATION_TYPES = {
    "watched",
    "searched",
    "collected",
    "transcript_available",
    "research_activity",
    "fact_status",
}
OBSERVATION_STATES = {
    "discovered",
    "reviewed",
    "researched",
    "supported",
    "unresolved",
    "conflicted",
    "stale",
}


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _id(prefix: str, value: object) -> str:
    return f"{prefix}_{_hash(value)[:32]}"


def _normalized(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


class KnowledgeAssistanceProjection:
    """Read-only, request-time Stage 4 projection over existing durable boundaries."""

    def __init__(self, db: Database, *, taxonomy: TaxonomyCorpusService) -> None:
        self.db = db
        self.taxonomy = taxonomy

    def project(
        self,
        task_id: str,
        *,
        principal_id: str | None,
        records: list[dict[str, Any]],
        enabled: bool,
        baseline_snapshot_id: int | None,
        current_snapshot_id: int | None,
    ) -> dict[str, Any]:
        empty = self._empty(enabled=enabled)
        if not enabled:
            return empty
        if not principal_id:
            return self._failed(empty, "principal_missing")
        try:
            focus, focus_reasons = self._focus(records, principal_id)
            with self.db.connect() as connection:
                if connection.execute(
                    "SELECT 1 FROM research_tasks WHERE task_id=?", (task_id,)
                ).fetchone() is None:
                    return self._failed(empty, "task_missing")
                progress, progress_reasons = self._progress(
                    connection, records, principal_id, task_id
                )
                controls = self._controls(connection, records, principal_id)
                staleness = self._staleness(connection, task_id, principal_id)
                delta, added, delta_reason = self._delta(
                    connection,
                    principal_id=principal_id,
                    baseline_snapshot_id=baseline_snapshot_id,
                    current_snapshot_id=current_snapshot_id,
                )
                if focus is None:
                    radar, radar_reason = [], focus_reasons[0]
                else:
                    radar, radar_reason = self._radar(
                        connection, focus=focus, added=added
                    )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return self._failed(empty, "malformed_or_drifted_boundary")

        lanes = {
            "progress": self._lane(progress, progress_reasons, cap=5),
            "staleness": self._lane(
                self._suppress(staleness, controls),
                ["persisted_lineage_only"] if staleness else ["no_stale_lineage"],
                cap=2,
            ),
            "collection_delta": self._lane(
                self._suppress(delta, controls), [delta_reason], cap=3
            ),
            "radar": self._lane(
                self._suppress(radar, controls), [radar_reason], cap=1
            ),
        }
        identity = {
            "policy_version": POLICY_VERSION,
            "enabled": True,
            "task_id": task_id,
            "principal_id": principal_id,
            "baseline_snapshot_id": baseline_snapshot_id,
            "current_snapshot_id": current_snapshot_id,
            "lanes": {
                name: {
                    "status": lane["status"],
                    "candidate_ids": [card["candidate_id"] for card in lane["cards"]],
                    "boundary_hashes": [card["boundary_hash"] for card in lane["cards"]],
                    "reason_codes": lane["reason_codes"],
                }
                for name, lane in lanes.items()
            },
        }
        return {
            **identity,
            "status": (
                "ready"
                if any(value["cards"] for value in lanes.values())
                else "fail_closed"
                if any(value["status"] == "fail_closed" for value in lanes.values())
                else "baseline"
            ),
            "lanes": lanes,
            "context_hash": _hash(identity),
            "authority": self._authority(),
        }

    @staticmethod
    def _empty(*, enabled: bool) -> dict[str, Any]:
        reasons = ["assistance_disabled"] if not enabled else ["cold_start_baseline"]
        lanes = {
            name: {"status": "baseline", "cards": [], "reason_codes": reasons}
            for name in ("progress", "staleness", "collection_delta", "radar")
        }
        identity = {
            "policy_version": POLICY_VERSION,
            "enabled": enabled,
            "task_id": None,
            "principal_id": None,
            "baseline_snapshot_id": None,
            "current_snapshot_id": None,
            "lanes": {
                name: {
                    "status": "baseline",
                    "candidate_ids": [],
                    "boundary_hashes": [],
                    "reason_codes": reasons,
                }
                for name in lanes
            },
        }
        return {
            **identity,
            "status": "disabled" if not enabled else "baseline",
            "lanes": lanes,
            "context_hash": _hash(identity),
            "authority": KnowledgeAssistanceProjection._authority(),
        }

    @staticmethod
    def _failed(value: dict[str, Any], reason: str) -> dict[str, Any]:
        result = dict(value)
        result["status"] = "fail_closed"
        result["lanes"] = {
            name: {"status": "fail_closed", "cards": [], "reason_codes": [reason]}
            for name in value["lanes"]
        }
        result["context_hash"] = _hash(
            {"policy_version": POLICY_VERSION, "status": "fail_closed", "reason": reason}
        )
        return result

    @staticmethod
    def _authority() -> dict[str, Any]:
        return {
            "projection": "request_time_read_only_pull_only",
            "mastery": "explicit_current_principal_assertion_only",
            "activity": "observation_never_mastery",
            "staleness": "persisted_fact_artifact_page_lineage_only",
            "delta": "same_scope_immutable_snapshots_and_current_preview",
            "radar": "confirmed_focus_plus_added_delta_plus_current_transcript",
            "citation_or_verifier": False,
            "prompt_route_search_fact_page_skill_mutation": False,
            "execution_or_notification_authority": False,
        }

    @staticmethod
    def _lane(
        cards: list[dict[str, Any]], reasons: list[str], *, cap: int
    ) -> dict[str, Any]:
        reasons = list(dict.fromkeys(reasons))
        visible = cards[:cap]
        return {
            "status": (
                "treatment"
                if visible
                else "fail_closed"
                if any("fail_closed" in reason for reason in reasons)
                else "baseline"
            ),
            "cards": visible,
            "truncated_count": max(0, len(cards) - cap),
            "reason_codes": reasons,
        }

    def _progress(
        self,
        connection: Any,
        records: list[dict[str, Any]],
        principal_id: str,
        task_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        cards: list[dict[str, Any]] = []
        reasons: list[str] = []
        for record in records:
            if record.get("record_kind") != "progress_observation":
                continue
            if str(record.get("semantic_key") or "").startswith(CONTROL_PREFIX):
                continue
            if record.get("principal_id") != principal_id:
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or record.get("effective_status") != "current":
                continue
            state = str(payload.get("state") or "")
            mastery = state in MASTERY_STATES
            if mastery:
                valid = (
                    set(payload) == {"topic", "state", "user_asserted"}
                    and payload.get("user_asserted") is True
                    and record.get("authority_class") in {"user_authored", "user_confirmed"}
                    and not record.get("source_refs")
                )
            else:
                valid = (
                    set(payload) == {"topic", "state", "observation_type"}
                    and state in OBSERVATION_STATES
                    and payload.get("observation_type") in OBSERVATION_TYPES
                    and record.get("authority_class") == "evidence_backed_observation"
                    and bool(record.get("source_refs"))
                    and all(
                        value.get("task_id") == task_id
                        for value in record.get("source_refs", [])
                    )
                    and record.get("command_task_id") == task_id
                    and self._refs_are_current(
                        connection, record.get("source_refs"), expected_task_id=task_id
                    )
                )
            if not valid:
                reasons.append("malformed_or_unauthorized_progress_omitted")
                continue
            boundary = str(record["content_hash"])
            cards.append(
                {
                    "candidate_id": _id("progress", boundary),
                    "boundary_hash": boundary,
                    "kind": "progress",
                    "title": str(payload["topic"]),
                    "state": state,
                    "mastery": mastery,
                    "observation_type": None if mastery else payload["observation_type"],
                    "explanation": (
                        "由当前用户明确自述/确认" if mastery else "活动证据仅形成 observation，不表示掌握"
                    ),
                    "source_refs": record.get("source_refs", []),
                    "dismiss_control": None,
                }
            )
        cards.sort(
            key=lambda item: (
                not item["mastery"],
                item["title"],
                item["candidate_id"],
            )
        )
        return cards, reasons or (["explicit_progress_only"] if cards else ["no_progress"])

    @staticmethod
    def _focus(
        records: list[dict[str, Any]], principal_id: str
    ) -> tuple[dict[str, Any] | None, list[str]]:
        eligible = []
        for record in records:
            if (
                record.get("record_kind") != "focus_state"
                or record.get("principal_id") != principal_id
                or record.get("authority_class") not in {"user_authored", "user_confirmed"}
                or record.get("effective_status") not in {"current", "confirmed"}
            ):
                continue
            payload = record.get("payload")
            if (
                isinstance(payload, dict)
                and set(payload) == {"topic", "state"}
                and _normalized(payload.get("topic")) == record.get("semantic_key")
            ):
                eligible.append(
                    {
                        "topic": str(payload["topic"]),
                        "record_id": str(record["record_id"]),
                        "record_revision_id": str(record["record_revision_id"]),
                        "content_hash": str(record["content_hash"]),
                    }
                )
        if len(eligible) == 1:
            return eligible[0], ["confirmed_current_focus"]
        return None, [
            "no_confirmed_focus" if not eligible else "conflicting_focus_fail_closed"
        ]

    @classmethod
    def _controls(
        cls, connection: Any, records: list[dict[str, Any]], principal_id: str
    ) -> dict[str, tuple[bool, str, tuple[tuple[str, str, str, str], ...]]]:
        result: dict[
            str, tuple[bool, str, tuple[tuple[str, str, str, str], ...]]
        ] = {}
        for record in records:
            semantic = str(record.get("semantic_key") or "")
            if not semantic.startswith(CONTROL_PREFIX) or record.get("principal_id") != principal_id:
                continue
            payload = record.get("payload")
            if (
                not isinstance(payload, dict)
                or set(payload) != {
                    "topic", "state", "user_asserted", "control", "dismissed",
                    "candidate_id", "candidate_kind", "boundary_hash",
                }
                or payload.get("candidate_id") != semantic[len(CONTROL_PREFIX):]
                or payload.get("state") != "reviewed"
                or payload.get("user_asserted") is not True
                or payload.get("control") != "dismiss"
                or not isinstance(payload.get("dismissed"), bool)
                or payload.get("candidate_kind")
                not in {"staleness", "collection_delta", "early_project_radar"}
                or not str(payload.get("topic") or "").strip()
                or len(str(payload.get("boundary_hash") or "")) != 64
                or not cls._refs_are_current(connection, record.get("source_refs"))
            ):
                continue
            status = str(record.get("effective_status") or "")
            source_identity = cls._ref_identity(record["source_refs"])
            if status == "expired":
                result[str(payload["candidate_id"])] = (
                    False,
                    str(payload["boundary_hash"]),
                    source_identity,
                )
            elif status == "tombstoned":
                result[str(payload["candidate_id"])] = (
                    True,
                    str(payload["boundary_hash"]),
                    source_identity,
                )
            elif status == "current" and isinstance(payload.get("dismissed"), bool):
                result[str(payload["candidate_id"])] = (
                    bool(payload["dismissed"]),
                    str(payload["boundary_hash"]),
                    source_identity,
                )
        return result

    @staticmethod
    def _suppress(
        cards: list[dict[str, Any]],
        controls: dict[
            str, tuple[bool, str, tuple[tuple[str, str, str, str], ...]]
        ],
    ) -> list[dict[str, Any]]:
        return [
            card
            for card in cards
            if controls.get(card["candidate_id"])
            != (
                True,
                card["boundary_hash"],
                KnowledgeAssistanceProjection._ref_identity(card["source_refs"]),
            )
        ]

    @staticmethod
    def _ref_identity(refs: list[dict[str, Any]]) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            sorted(
                (
                    str(value.get("ref_type") or ""),
                    str(value.get("ref_id") or ""),
                    str(value.get("task_id") or ""),
                    str(value.get("boundary_hash") or ""),
                )
                for value in refs
            )
        )

    @staticmethod
    def _refs_are_current(
        connection: Any, refs: object, *, expected_task_id: str | None = None
    ) -> bool:
        if not isinstance(refs, list) or not refs:
            return False
        mapping = {
            "research_task": ("research_tasks", "task_id"),
            "research_event": ("research_events", "event_id"),
            "research_attempt": ("research_attempts", "attempt_id"),
            "research_trace": ("research_traces", "trace_id"),
            "research_result": ("research_results", "result_id"),
            "fact_revision": ("research_fact_revisions", "fact_revision_id"),
            "artifact_revision": (
                "research_knowledge_artifact_revisions", "artifact_revision_id"
            ),
            "taxonomy_snapshot": ("taxonomy_corpus_snapshots", "id"),
        }
        for ref in refs:
            if not isinstance(ref, dict) or ref.get("ref_type") not in mapping:
                return False
            if (
                expected_task_id is not None
                and ref.get("ref_type") != "taxonomy_snapshot"
                and ref.get("task_id") != expected_task_id
            ):
                return False
            table, key = mapping[str(ref["ref_type"])]
            lookup: object = (
                int(ref["ref_id"])
                if ref["ref_type"] == "taxonomy_snapshot"
                else ref["ref_id"]
            )
            row = connection.execute(
                f"SELECT * FROM {table} WHERE {key}=?", (lookup,)
            ).fetchone()
            if row is None or _hash(dict(row)) != ref.get("boundary_hash"):
                return False
        return True

    def _staleness(
        self, connection: Any, task_id: str, principal_id: str
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT fs.*, fr.claim_text, fr.content_hash AS fact_content_hash,
                   fr.fact_revision_id
            FROM research_knowledge_fact_states fs
            JOIN research_fact_revisions fr ON fr.fact_revision_id=fs.current_revision_id
            WHERE fs.task_id=? AND (
                fs.lifecycle_status!='current' OR fs.currentness_status!='current'
            )
            ORDER BY fs.updated_at DESC, fs.fact_id
            """,
            (task_id,),
        ).fetchall()
        cards = []
        for row in rows:
            fact_row = connection.execute(
                "SELECT * FROM research_fact_revisions WHERE fact_revision_id=?",
                (row["fact_revision_id"],),
            ).fetchone()
            if fact_row is None:
                continue
            artifacts = connection.execute(
                """
                SELECT ar.artifact_revision_id, ar.content_hash
                FROM research_artifact_fact_links l
                JOIN research_knowledge_artifact_revisions ar
                  ON ar.artifact_revision_id=l.artifact_revision_id
                WHERE l.task_id=? AND l.fact_revision_id=?
                  AND ar.revision=(
                    SELECT MAX(ar2.revision)
                    FROM research_knowledge_artifact_revisions ar2
                    WHERE ar2.artifact_id=ar.artifact_id
                  )
                ORDER BY ar.revision DESC, ar.artifact_revision_id
                """,
                (task_id, row["fact_revision_id"]),
            ).fetchall()
            pages = connection.execute(
                """
                SELECT pr.page_revision_id, pr.content_hash
                FROM research_topic_page_fact_links l
                JOIN research_topic_page_revisions pr ON pr.page_revision_id=l.page_revision_id
                JOIN research_topic_pages p ON p.page_id=pr.page_id AND p.current_version=pr.version
                WHERE l.task_id=? AND l.fact_revision_id=?
                ORDER BY pr.version DESC, pr.page_revision_id
                """,
                (task_id, row["fact_revision_id"]),
            ).fetchall()
            boundary_value = {
                "fact_revision_id": row["fact_revision_id"],
                "fact_content_hash": row["fact_content_hash"],
                "lifecycle_status": row["lifecycle_status"],
                "currentness_status": row["currentness_status"],
                "state_version": row["state_version"],
                "artifacts": [(value[0], value[1]) for value in artifacts],
                "pages": [(value[0], value[1]) for value in pages],
            }
            boundary = _hash(boundary_value)
            candidate_id = _id(
                "stale", {"principal_id": principal_id, **boundary_value}
            )
            refs = [self._ref("fact_revision", dict(fact_row), task_id)]
            if artifacts:
                artifact_row = connection.execute(
                    "SELECT * FROM research_knowledge_artifact_revisions WHERE artifact_revision_id=?",
                    (artifacts[0][0],),
                ).fetchone()
                if artifact_row is not None:
                    refs.append(self._ref("artifact_revision", dict(artifact_row), task_id))
            cards.append(
                self._candidate(
                    candidate_id=candidate_id,
                    boundary=boundary,
                    kind="staleness",
                    title=str(row["claim_text"]),
                    explanation=(
                        f"persisted Fact lineage: {row['lifecycle_status']} / {row['currentness_status']}; "
                        f"affected artifacts {len(artifacts)}, pages {len(pages)}"
                    ),
                    refs=refs,
                )
            )
        return cards

    def _delta(
        self,
        connection: Any,
        *,
        principal_id: str,
        baseline_snapshot_id: int | None,
        current_snapshot_id: int | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        if baseline_snapshot_id is None and current_snapshot_id is None:
            return [], [], "snapshot_pair_absent"
        if baseline_snapshot_id is None or current_snapshot_id is None:
            return [], [], "snapshot_pair_incomplete_fail_closed"
        baseline = self._snapshot(connection, baseline_snapshot_id)
        current = self._snapshot(connection, current_snapshot_id)
        if baseline is None or current is None:
            return [], [], "snapshot_missing_or_malformed_fail_closed"
        if baseline["selected_source_ids"] != current["selected_source_ids"]:
            return [], [], "snapshot_scope_mismatch_fail_closed"
        preview = self.taxonomy.preview(current["selected_source_ids"])
        preview_hash = _hash(
            {
                "schema_version": self.taxonomy.CARD_SCHEMA_VERSION,
                "selected_source_ids": sorted(preview.selected_source_ids),
                "card_hashes": sorted(card.card_hash for card in preview.cards),
            }
        )
        if preview_hash != current["snapshot_hash"]:
            return [], [], "current_preview_drift_fail_closed"
        left = {card["content_key"]: card for card in baseline["cards"]}
        right = {card["content_key"]: card for card in current["cards"]}
        changes: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
        for key in sorted(right, key=lambda value: (right[value]["ordinal"], value)):
            if key not in left:
                changes.append(("added", right[key], None))
            elif (
                right[key]["card_hash"] != left[key]["card_hash"]
                or right[key]["discovery_view_hash"] != left[key]["discovery_view_hash"]
            ):
                changes.append(("changed", right[key], left[key]))
        for key in sorted(left, key=lambda value: (left[value]["ordinal"], value)):
            if key not in right:
                changes.append(("removed", left[key], None))
        refs = [
            self._ref("taxonomy_snapshot", baseline["row"], None),
            self._ref("taxonomy_snapshot", current["row"], None),
        ]
        cards = []
        added = []
        for kind, card, previous in changes:
            boundary_value = {
                "kind": kind,
                "baseline_snapshot_hash": baseline["snapshot_hash"],
                "current_snapshot_hash": current["snapshot_hash"],
                "content_key": card["content_key"],
                "card_hash": card["card_hash"],
                "previous_card_hash": previous["card_hash"] if previous else None,
            }
            boundary = _hash(boundary_value)
            candidate_id = _id(
                "delta", {"principal_id": principal_id, **boundary_value}
            )
            value = self._candidate(
                candidate_id=candidate_id,
                boundary=boundary,
                kind="collection_delta",
                title=f"{kind}: {card['stored_card'].get('title') or card['content_key']}",
                explanation="same-scope immutable snapshot observation; no Fact/Profile mutation",
                refs=refs,
            )
            value.update(
                {
                    "delta_kind": kind,
                    "content_key": card["content_key"],
                    "video_id": card["video_id"],
                }
            )
            cards.append(value)
            if kind == "added":
                added.append({**card, "snapshot_refs": refs, "delta_boundary": boundary})
        return (
            cards,
            added,
            "verified_same_scope_snapshot_delta" if cards else "no_collection_delta",
        )

    def _snapshot(self, connection: Any, snapshot_id: int) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT * FROM taxonomy_corpus_snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        if row is None:
            return None
        value = dict(row)
        selected = json.loads(str(value["selected_source_ids_json"]))
        if not isinstance(selected, list) or any(
            not isinstance(item, int) for item in selected
        ):
            return None
        rows = connection.execute(
            "SELECT * FROM taxonomy_classification_cards WHERE snapshot_id=? ORDER BY ordinal",
            (snapshot_id,),
        ).fetchall()
        cards = []
        for card_row in rows:
            card_value = dict(card_row)
            stored = json.loads(str(card_value["stored_card_json"]))
            view = json.loads(str(card_value["discovery_view_json"]))
            if (
                not isinstance(stored, dict)
                or not isinstance(view, dict)
                or _hash(stored) != card_value["card_hash"]
                or _hash(view) != card_value["discovery_view_hash"]
                or stored.get("content_key") != card_value["content_key"]
            ):
                return None
            cards.append(
                {
                    "content_key": str(card_value["content_key"]),
                    "video_id": card_value["video_id"],
                    "ordinal": int(card_value["ordinal"]),
                    "selected_revision": card_value["selected_revision"],
                    "stored_card": stored,
                    "card_hash": str(card_value["card_hash"]),
                    "discovery_view_hash": str(card_value["discovery_view_hash"]),
                }
            )
        expected = _hash(
            {
                "schema_version": self.taxonomy.CARD_SCHEMA_VERSION,
                "selected_source_ids": sorted(selected),
                "card_hashes": sorted(card["card_hash"] for card in cards),
            }
        )
        if expected != value["snapshot_hash"] or len(cards) != int(value["content_count"]):
            return None
        return {
            "row": value,
            "selected_source_ids": selected,
            "snapshot_hash": str(value["snapshot_hash"]),
            "cards": cards,
        }

    def _radar(
        self,
        connection: Any,
        *,
        focus: dict[str, Any] | None,
        added: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        if focus is None:
            return [], "confirmed_focus_absent"
        focus_text = _normalized(focus["topic"])
        if len(focus_text) < 2:
            return [], "focus_too_short_fail_closed"
        for card in added:
            video_id = card.get("video_id")
            if not video_id:
                continue
            video = connection.execute(
                "SELECT * FROM videos WHERE id=?", (video_id,)
            ).fetchone()
            sync = connection.execute(
                "SELECT * FROM retrieval_sync_state WHERE video_id=?", (video_id,)
            ).fetchone()
            if (
                video is None
                or sync is None
                or sync["desired_state"] != "indexed"
                or sync["lexical_state"] != "current"
                or not video["raw_subtitle_path"]
            ):
                continue
            try:
                path = self.taxonomy.artifacts.managed_file(str(video["raw_subtitle_path"]))
                if path.parent.name != str(video["source_id"]):
                    continue
                raw = path.read_bytes()
                decoded = raw.decode("utf-8")
                if path.suffix == ".json":
                    segments = json.loads(decoded)
                else:
                    segments = [
                        {"content": line}
                        for line in decoded.splitlines()
                        if line.strip()
                    ]
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(segments, list):
                continue
            excerpt = None
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                content = str(segment.get("content") or segment.get("text") or "")
                if self._exact_overlap(focus_text, content):
                    excerpt = " ".join(content.split())[:240]
                    break
            if not excerpt:
                continue
            boundary_value = {
                "focus_hash": focus["content_hash"],
                "delta_boundary": card["delta_boundary"],
                "video_id": int(video_id),
                "active_revision": video["active_revision"],
                "raw_subtitle_sha256": hashlib.sha256(raw).hexdigest(),
                "sync_state_version": sync["sync_state_version"],
            }
            boundary = _hash(boundary_value)
            candidate_id = _id("radar", boundary_value)
            value = self._candidate(
                candidate_id=candidate_id,
                boundary=boundary,
                kind="early_project_radar",
                title=str(card["stored_card"].get("title") or card["content_key"]),
                explanation=(
                    "confirmed Focus 与 current transcript exact match: "
                    f"{excerpt}"
                ),
                refs=card["snapshot_refs"],
                topic=str(focus["topic"]),
            )
            value["focus_identity"] = focus
            value["snapshot_identity"] = {
                "content_key": card["content_key"],
                "delta_boundary": card["delta_boundary"],
            }
            value["evidence_identity"] = boundary_value
            value["matched_term"] = focus_text
            value["execution_authority"] = False
            return [value], "focus_added_delta_current_transcript_match"
        return [], "no_current_transcript_focus_match"

    @staticmethod
    def _exact_overlap(focus: str, content: str) -> bool:
        normalized_content = _normalized(content)
        if any("\u4e00" <= value <= "\u9fff" for value in focus):
            return focus in normalized_content
        focus_tokens = re.findall(r"\w+", focus, flags=re.UNICODE)
        content_tokens = re.findall(r"\w+", normalized_content, flags=re.UNICODE)
        if not focus_tokens:
            return False
        width = len(focus_tokens)
        return any(
            content_tokens[index : index + width] == focus_tokens
            for index in range(len(content_tokens) - width + 1)
        )

    @staticmethod
    def _ref(ref_type: str, row: dict[str, Any], task_id: str | None) -> dict[str, Any]:
        if ref_type == "taxonomy_snapshot":
            ref_id = str(row["id"])
        elif ref_type == "fact_revision":
            ref_id = str(row["fact_revision_id"])
        else:
            ref_id = str(row["artifact_revision_id"])
        return {
            "ref_type": ref_type,
            "ref_id": ref_id,
            "task_id": task_id,
            "boundary_hash": _hash(row),
        }

    @staticmethod
    def _candidate(
        *,
        candidate_id: str,
        boundary: str,
        kind: str,
        title: str,
        explanation: str,
        refs: list[dict[str, Any]],
        topic: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "topic": topic or title,
            "state": "reviewed",
            "user_asserted": True,
            "control": "dismiss",
            "dismissed": True,
            "candidate_id": candidate_id,
            "candidate_kind": kind,
            "boundary_hash": boundary,
        }
        return {
            "candidate_id": candidate_id,
            "boundary_hash": boundary,
            "kind": kind,
            "title": title,
            "explanation": explanation,
            "source_refs": refs,
            "dismiss_control": {
                "record_kind": "progress_observation",
                "semantic_key": f"{CONTROL_PREFIX}{candidate_id}",
                "payload": payload,
                "source_refs": refs,
            },
        }
