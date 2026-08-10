from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Sequence

from shiliu.db import Database
from shiliu.research.schema import PERSONAL_WORKSPACE_POLICY_VERSION
from shiliu.taxonomy.corpus import TaxonomyCorpusService


CORPUS_SEARCH_POLICY_VERSION = "v5-c-stage2-corpus-search-v1"
_CONSUMED_TYPES = {
    "folder",
    "topic",
    "uploader",
    "series",
    "source_availability",
    "search_term",
    "limitation",
}
_TOKEN = re.compile(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff]+")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decode(value: object, expected: type) -> Any:
    decoded = json.loads(str(value))
    if not isinstance(decoded, expected):
        raise ValueError("invalid persisted JSON shape")
    return decoded


def _normalized(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _overlaps(left: object, right: object) -> bool:
    first = _normalized(left)
    second = _normalized(right)
    if not first or not second:
        return False
    if first in second or second in first:
        return True
    return bool(set(_TOKEN.findall(first)) & set(_TOKEN.findall(second)))


@dataclass(frozen=True)
class ProjectedCorpusSearchContext:
    context: dict[str, Any]
    matches_by_video: dict[int, tuple[dict[str, Any], ...]]


class CorpusSearchContextProjection:
    """Read-only Stage 2 projection over task-scoped Workspace corpus priors."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def project(
        self,
        *,
        task_id: str | None,
        principal_id: str | None,
        normalized_query: str,
        enabled: bool,
    ) -> ProjectedCorpusSearchContext:
        if not enabled:
            return self._outcome(
                task_id=task_id,
                enabled=False,
                status="disabled",
                reasons=["corpus_aware_disabled"],
            )
        if task_id is None:
            return self._outcome(
                task_id=None,
                enabled=True,
                status="baseline",
                reasons=["no_corpus_task_context"],
            )
        if principal_id is None:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="fail_closed",
                reasons=["principal_context_missing"],
            )

        with self.db.connect() as connection:
            task = connection.execute(
                "SELECT task_id FROM research_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if task is None:
                return self._outcome(
                    task_id=task_id,
                    enabled=True,
                    status="fail_closed",
                    reasons=["corpus_task_not_found"],
                )
            rows = connection.execute(
                """
                SELECT w.* FROM research_workspace_records w
                JOIN (
                    SELECT record_id, MAX(version) AS version
                    FROM research_workspace_records GROUP BY record_id
                ) latest
                  ON latest.record_id=w.record_id AND latest.version=w.version
                WHERE w.command_task_id=? AND w.record_kind='corpus_observation'
                ORDER BY w.semantic_key, w.record_id
                """,
                (task_id,),
            ).fetchall()
            if not rows:
                return self._outcome(
                    task_id=task_id,
                    enabled=True,
                    status="baseline",
                    reasons=["no_current_corpus_prior"],
                )

            cues: list[dict[str, Any]] = []
            matches: dict[int, list[dict[str, Any]]] = {}
            values_by_key: dict[str, str] = {}
            terminal = 0
            unrelated = 0
            snapshot_cache: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                if str(row["status"]) != "current":
                    terminal += 1
                    continue
                try:
                    cue, cards = self._validated_cue(
                        connection,
                        row=dict(row),
                        principal_id=principal_id,
                        snapshot_cache=snapshot_cache,
                    )
                except (
                    AttributeError,
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    return self._outcome(
                        task_id=task_id,
                        enabled=True,
                        status="fail_closed",
                        reasons=["malformed_or_drifted_corpus_prior"],
                    )
                key = _normalized(cue["semantic_key"])
                value = _normalized(cue["value"])
                previous = values_by_key.get(key)
                if previous is not None and previous != value:
                    return self._outcome(
                        task_id=task_id,
                        enabled=True,
                        status="fail_closed",
                        reasons=["conflicting_corpus_prior"],
                    )
                values_by_key[key] = value
                if not _overlaps(value, normalized_query):
                    unrelated += 1
                    continue
                cues.append(cue)
                for card in cards:
                    video_id = card.get("video_id")
                    if (
                        not isinstance(video_id, int)
                        or not card.get("discovery_eligible")
                        or not self._card_matches(cue, card)
                    ):
                        continue
                    matches.setdefault(video_id, []).append(
                        {
                            "record_id": cue["record_id"],
                            "record_revision_id": cue["record_revision_id"],
                            "snapshot_id": cue["snapshot_id"],
                            "snapshot_hash": cue["snapshot_hash"],
                            "cue_type": cue["observation_type"],
                            "cue_value": cue["value"],
                        }
                    )

        if not cues:
            reason = (
                "unrelated_corpus_prior"
                if unrelated
                else "terminal_corpus_prior_not_applied"
                if terminal
                else "no_current_corpus_prior"
            )
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="baseline",
                reasons=[reason],
            )
        if not matches:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="baseline",
                reasons=["no_matching_baseline_candidate"],
                cues=cues,
            )
        stable_matches = {
            video_id: tuple(
                sorted(
                    values,
                    key=lambda item: (
                        item["cue_type"],
                        _normalized(item["cue_value"]),
                        item["record_revision_id"],
                    ),
                )
            )
            for video_id, values in sorted(matches.items())
        }
        return self._outcome(
            task_id=task_id,
            enabled=True,
            status="eligible",
            reasons=["bounded_soft_prior_eligible"],
            cues=cues,
            matches=stable_matches,
        )

    def _validated_cue(
        self,
        connection: Any,
        *,
        row: dict[str, Any],
        principal_id: str,
        snapshot_cache: dict[int, list[dict[str, Any]]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if (
            row["authority_class"] != "corpus_soft_prior"
            or row["principal_id"] != principal_id
            or row["policy_version"] != PERSONAL_WORKSPACE_POLICY_VERSION
        ):
            raise ValueError("corpus authority mismatch")
        payload = _decode(row["payload_json"], dict)
        if set(payload) != {"observation_type", "value"}:
            raise ValueError("corpus payload is not exact")
        if not isinstance(payload["observation_type"], str) or not isinstance(
            payload["value"], str
        ):
            raise ValueError("corpus payload values must be strings")
        observation_type = _normalized(payload["observation_type"])
        value = _normalized(payload["value"])
        if observation_type not in _CONSUMED_TYPES or not value:
            raise ValueError("unsupported corpus cue")
        refs = _decode(row["source_refs_json"], list)
        if len(refs) != 1 or refs[0].get("ref_type") != "taxonomy_snapshot":
            raise ValueError("corpus source is not one snapshot")
        if row["source_boundary_hash"] != _hash(refs):
            raise ValueError("workspace source boundary drift")
        expected_content_hash = _hash(
            {
                "record_kind": row["record_kind"],
                "authority_class": row["authority_class"],
                "status": row["status"],
                "semantic_key": row["semantic_key"],
                "payload": payload,
                "source_refs": refs,
                "confidence": row["confidence"],
                "expires_at": row["expires_at"],
                "policy_version": row["policy_version"],
            }
        )
        if row["content_hash"] != expected_content_hash:
            raise ValueError("workspace content hash drift")
        snapshot_id = int(refs[0]["ref_id"])
        snapshot_row = connection.execute(
            "SELECT * FROM taxonomy_corpus_snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
        if snapshot_row is None:
            raise ValueError("snapshot missing")
        snapshot = dict(snapshot_row)
        if refs[0].get("boundary_hash") != _hash(snapshot):
            raise ValueError("snapshot boundary drift")
        if snapshot_id not in snapshot_cache:
            snapshot_cache[snapshot_id] = self._validated_cards(
                connection, snapshot=snapshot
            )
        return (
            {
                "record_id": str(row["record_id"]),
                "record_revision_id": str(row["record_revision_id"]),
                "version": int(row["version"]),
                "content_hash": str(row["content_hash"]),
                "semantic_key": str(row["semantic_key"]),
                "observation_type": observation_type,
                "value": value,
                "snapshot_id": snapshot_id,
                "snapshot_hash": str(snapshot["snapshot_hash"]),
                "authority_class": "corpus_soft_prior",
            },
            snapshot_cache[snapshot_id],
        )

    @staticmethod
    def _validated_cards(connection: Any, *, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT video_id, evidence_level, discovery_eligible, stored_card_json,
                   discovery_view_json, card_hash, discovery_view_hash
            FROM taxonomy_classification_cards
            WHERE snapshot_id=? ORDER BY ordinal
            """,
            (snapshot["id"],),
        ).fetchall()
        cards: list[dict[str, Any]] = []
        card_hashes: list[str] = []
        for row in rows:
            stored = _decode(row["stored_card_json"], dict)
            discovery = _decode(row["discovery_view_json"], dict)
            if row["card_hash"] != _hash(stored) or row["discovery_view_hash"] != _hash(
                discovery
            ):
                raise ValueError("frozen card hash drift")
            card_hashes.append(str(row["card_hash"]))
            cards.append(
                {
                    "video_id": row["video_id"],
                    "evidence_level": str(row["evidence_level"]),
                    "discovery_eligible": bool(row["discovery_eligible"]),
                    "stored": stored,
                }
            )
        if len(cards) != int(snapshot["content_count"]):
            raise ValueError("snapshot card count drift")
        selected_source_ids = _decode(snapshot["selected_source_ids_json"], list)
        expected_snapshot_hash = _hash(
            {
                "schema_version": TaxonomyCorpusService.CARD_SCHEMA_VERSION,
                "selected_source_ids": sorted(selected_source_ids),
                "card_hashes": sorted(card_hashes),
            }
        )
        if snapshot["snapshot_hash"] != expected_snapshot_hash:
            raise ValueError("snapshot hash drift")
        return cards

    @staticmethod
    def _card_matches(cue: dict[str, Any], card: dict[str, Any]) -> bool:
        stored = card["stored"]
        cue_type = cue["observation_type"]
        if cue_type == "folder":
            values = stored.get("folder_names", [])
        elif cue_type == "uploader":
            values = [stored.get("uploader", "")]
        elif cue_type == "source_availability":
            values = [card.get("evidence_level", "")]
        elif cue_type == "limitation":
            values = [stored.get("description", ""), *stored.get("key_points", [])]
        elif cue_type == "series":
            values = [
                stored.get("title", ""),
                *stored.get("folder_names", []),
                *stored.get("projects_tools_models", []),
            ]
        elif cue_type == "topic":
            values = [
                stored.get("title", ""),
                stored.get("one_line_summary", ""),
                *stored.get("key_points", []),
                *stored.get("projects_tools_models", []),
            ]
        else:
            values = [
                stored.get("title", ""),
                stored.get("uploader", ""),
                stored.get("description", ""),
                stored.get("one_line_summary", ""),
                *stored.get("key_points", []),
                *stored.get("projects_tools_models", []),
                *stored.get("folder_names", []),
            ]
        return any(_overlaps(cue["value"], value) for value in values)

    @staticmethod
    def _outcome(
        *,
        task_id: str | None,
        enabled: bool,
        status: str,
        reasons: list[str],
        cues: list[dict[str, Any]] | None = None,
        matches: dict[int, tuple[dict[str, Any], ...]] | None = None,
    ) -> ProjectedCorpusSearchContext:
        cue_values = sorted(
            cues or [],
            key=lambda item: (
                item["observation_type"],
                _normalized(item["value"]),
                item["record_revision_id"],
            ),
        )
        identity = {
            "policy_version": CORPUS_SEARCH_POLICY_VERSION,
            "task_id": task_id,
            "enabled": enabled,
            "status": status,
            "applied": False,
            "effect_scope": "product_search_presentation_only",
            "cues": cue_values,
            "reason_codes": list(dict.fromkeys(reasons)),
            "authority": {
                "source": "task_scoped_workspace_corpus_observation",
                "soft_prior_only": True,
                "citation_authority": False,
                "verifier_authority": False,
                "fact_authority": False,
                "hard_filter": False,
                "route_authority": False,
            },
        }
        context = {**identity, "context_hash": _hash(identity)}
        return ProjectedCorpusSearchContext(
            context=context,
            matches_by_video=matches or {},
        )


def compose_corpus_search_results(
    groups: Sequence[Any],
    *,
    result_limit: int,
    projection: ProjectedCorpusSearchContext,
) -> tuple[tuple[Any, ...], dict[str, Any], tuple[dict[str, Any], ...]]:
    baseline = list(groups)
    target = min(result_limit, len(baseline))
    baseline_selected = baseline[:target]
    baseline_rank = {int(group.video_id): index + 1 for index, group in enumerate(baseline)}
    matches = projection.matches_by_video
    context = dict(projection.context)
    selected = list(baseline_selected)
    corpus_ids: set[int] = set()
    counterexample_id: int | None = None

    if target and context["status"] == "eligible" and matches:
        open_required = math.ceil(target / 2)
        corpus_capacity = math.floor(target / 2)
        open_groups = list(baseline[:open_required])
        counterexample = next(
            (group for group in baseline if int(group.video_id) not in matches), None
        )
        if counterexample is not None:
            counterexample_id = int(counterexample.video_id)
            if all(group.video_id != counterexample.video_id for group in open_groups):
                open_groups[-1] = counterexample
                open_groups.sort(key=lambda group: baseline_rank[int(group.video_id)])
        open_ids = {int(group.video_id) for group in open_groups}
        corpus_groups = sorted(
            (
                group
                for group in baseline
                if int(group.video_id) in matches and int(group.video_id) not in open_ids
            ),
            key=lambda group: (
                -len(matches[int(group.video_id)]),
                baseline_rank[int(group.video_id)],
            ),
        )[:corpus_capacity]
        corpus_ids = {int(group.video_id) for group in corpus_groups}

        merged: list[Any] = []
        open_index = 0
        corpus_index = 0
        while len(merged) < target and (
            open_index < len(open_groups) or corpus_index < len(corpus_groups)
        ):
            if open_index < len(open_groups):
                merged.append(open_groups[open_index])
                open_index += 1
            if len(merged) < target and corpus_index < len(corpus_groups):
                merged.append(corpus_groups[corpus_index])
                corpus_index += 1
        used = {int(group.video_id) for group in merged}
        for group in baseline:
            if len(merged) >= target:
                break
            if int(group.video_id) not in used:
                merged.append(group)
                used.add(int(group.video_id))
        selected = merged

    selected_ids = [int(group.video_id) for group in selected]
    baseline_ids = [int(group.video_id) for group in baseline_selected]
    applied = selected_ids != baseline_ids
    if context["status"] == "eligible":
        context["applied"] = applied
        context["status"] = "applied" if applied else "baseline"
        context["reason_codes"] = [
            "bounded_corpus_composition_applied"
            if applied
            else "no_reorderable_soft_prior_match"
        ]

    contributions = []
    for displayed_rank, group in enumerate(selected, 1):
        video_id = int(group.video_id)
        if video_id in corpus_ids:
            lane = "corpus_soft_prior"
        elif video_id == counterexample_id:
            lane = "open_counterexample"
        else:
            lane = "open_baseline"
        contributions.append(
            {
                "video_id": video_id,
                "displayed_rank": displayed_rank,
                "baseline_rank": baseline_rank[video_id],
                "lane": lane,
                "soft_prior_matches": list(matches.get(video_id, ())),
                "citation_authority": False,
                "verifier_authority": False,
                "fact_authority": False,
                "hard_filter": False,
                "route_authority": False,
            }
        )
    context["open_lane"] = {
        "independent": True,
        "baseline_candidate_pool_unchanged": True,
        "reserved_slots_min": math.ceil(target / 2),
    }
    context["counterexample"] = {
        "required_when_available": True,
        "video_id": counterexample_id,
        "preserved": counterexample_id is None or counterexample_id in selected_ids,
    }
    context["baseline_candidate_pool_hash"] = _hash(
        [
            {
                "video_id": int(group.video_id),
                "baseline_rank": baseline_rank[int(group.video_id)],
            }
            for group in baseline
        ]
    )
    context["result_hash"] = _hash(
        {
            "context_hash": context["context_hash"],
            "selected_video_ids": selected_ids,
            "contributions": contributions,
        }
    )
    return tuple(selected), context, tuple(contributions)
