from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.store import AssistantConflict
from shiliu.db import Database, utc_now


class TaskNoteService:
    """Versioned navigation state for one conversation task segment."""

    def __init__(
        self,
        db: Database,
        memories: MemoryService,
        *,
        principal_id: str = "local_operator",
        source_ref_validator: Callable[[list[str], int], bool] | None = None,
        dependency_ref_validator: Callable[[list[str], int, str, int], bool] | None = None,
    ) -> None:
        self.db = db
        self.memories = memories
        self.principal_id = principal_id
        self.source_ref_validator = source_ref_validator
        self.dependency_ref_validator = dependency_ref_validator

    def get(self, thread_id: str, *, task_segment: int = 1) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT n.* FROM assistant_task_notes n
                JOIN assistant_threads t ON t.id=n.thread_id
                WHERE n.thread_id=? AND n.task_segment=? AND t.principal_id=?
                """,
                (thread_id, task_segment, self.principal_id),
            ).fetchone()
        return self._decode(dict(row)) if row else None

    def valid_for_context(
        self, thread_id: str, *, space_id: int, scope_version: int, task_segment: int = 1
    ) -> dict[str, Any] | None:
        note = self.get(thread_id, task_segment=task_segment)
        if note is None or note["status"] != "active":
            return None
        if int(note["scope_version"]) != scope_version:
            return None
        if note["source_run_ids"]:
            placeholders = ",".join("?" for _ in note["source_run_ids"])
            with self.db.connect() as connection:
                abandoned = connection.execute(
                    f"SELECT 1 FROM assistant_runs WHERE id IN ({placeholders}) AND status='cancelled' LIMIT 1",
                    note["source_run_ids"],
                ).fetchone()
            if abandoned:
                return None
        suppressed_message_ids = self.memories.suppressed_source_message_ids(space_id=space_id)
        if suppressed_message_ids and note["source_run_ids"]:
            placeholders = ",".join("?" for _ in note["source_run_ids"])
            with self.db.connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT id FROM assistant_messages
                    WHERE run_id IN ({placeholders}) AND role='user'
                    """,
                    note["source_run_ids"],
                ).fetchall()
            if any(str(row["id"]) in suppressed_message_ids for row in rows):
                return None
        memory_refs = [
            value for value in note["dependencies"] if str(value).startswith("memory:")
        ]
        if memory_refs and not self.memories.validate_dependency_refs(
            memory_refs, space_id=space_id
        )["valid"]:
            return None
        source_refs = [
            str(value) for value in note["dependencies"]
            if str(value).startswith("video:")
        ]
        if (
            source_refs
            and self.source_ref_validator is not None
            and not self.source_ref_validator(source_refs, space_id)
        ):
            return None
        result_refs = [
            str(value) for value in note["dependencies"]
            if str(value).startswith("run-result:")
        ]
        if (
            result_refs
            and self.dependency_ref_validator is not None
            and not self.dependency_ref_validator(
                result_refs, space_id, thread_id, scope_version
            )
        ):
            return None
        return note

    def build_candidate(
        self,
        run_context: dict[str, Any],
        *,
        messages: list[dict[str, Any]],
        recalled_memories: list[dict[str, Any]],
        covered_until_message_seq: int,
    ) -> dict[str, Any]:
        space = run_context["space"]
        existing = self.get(str(run_context["thread"]["id"]))
        covered = [
            item for item in messages if int(item.get("seq") or 0) <= covered_until_message_seq
        ]
        user_messages = [item for item in covered if item.get("role") == "user"]
        task_messages = self._current_task_messages(user_messages)
        constraints, goal, active_clauses, withdrawn_targets = self._effective_task_state(
            task_messages
        )
        materials: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        # Recall alone is not use. Keep dependencies only where a user source,
        # answer, result, or inherited finding actually used that memory.
        dependencies: list[str] = []
        dependencies.extend(self.memories.dependency_refs_for_source_messages(
            [str(item["id"]) for item in user_messages], space_id=int(space["id"])
        ))
        source_run_ids: list[str] = []
        calls_by_id: dict[str, dict[str, Any]] = {}
        for item in covered:
            if item.get("run_id"):
                source_run_ids.append(str(item["run_id"]))
            payload = self._payload(item)
            if item.get("role") == "assistant" and payload.get("tool_calls"):
                for call in payload["tool_calls"]:
                    try:
                        calls_by_id[str(call["id"])] = json.loads(
                            call["function"].get("arguments") or "{}"
                        )
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
            if item.get("role") == "assistant" and item.get("content") and not payload.get("tool_calls"):
                refs = [str(value) for value in payload.get("dependency_refs") or []]
                dependencies.extend(refs)
                summary = " ".join(str(item["content"]).split())[:600]
                if any(target in summary for target in withdrawn_targets):
                    continue
                findings.append({
                    "kind": "model_summary",
                    "message_id": str(item["id"]),
                    "text": summary,
                    "dependencies": refs,
                })
            if item.get("role") != "tool":
                continue
            try:
                result = json.loads(str(item.get("content") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            refs = [str(value) for value in result.get("source_refs") or []]
            dependency_refs = [str(value) for value in result.get("dependency_refs") or []]
            result_ref = str(result.get("result_ref") or "")
            dependencies.extend(refs + dependency_refs + ([result_ref] if result_ref else []))
            tool_name = str(payload.get("name") or "")
            call_args = calls_by_id.get(str(payload.get("tool_call_id") or ""), {})
            if tool_name == "run_read_result":
                # This is a pointer traversal, not a new material observation.
                # The original durable result remains represented by its source entry.
                continue
            view = ""
            coverage: Any = result.get("coverage") or {}
            for value in result.get("items") or []:
                if not isinstance(value, dict):
                    continue
                view = str(value.get("view") or value.get("material_kind") or view)
            first_item = next((value for value in result.get("items") or []
                               if isinstance(value, dict)), {})
            title = str((first_item.get("video") or {}).get("title") or
                        first_item.get("title") or "")[:160]
            materials.append({
                "tool": tool_name,
                "source_refs": refs,
                "view": view or "metadata_or_result",
                "coverage": coverage,
                "summary": str(result.get("summary") or "")[:400],
                "result_ref": str(result.get("result_ref") or ""),
                "next_cursor": result.get("next_cursor"),
                "message_seq": int(item.get("seq") or 0),
                "title": title,
                "query": str(call_args.get("query") or "")[:200] if tool_name == "collection_search" else "",
                "require_transcript": bool(call_args.get("require_transcript")) if tool_name == "collection_search" else None,
                "candidates": [{"source_ref": value.get("source_ref"),
                                "title": str(value.get("title") or "")[:120],
                                "available_views": value.get("available_views") or []}
                               for value in (result.get("items") or [])[:10]
                               if isinstance(value, dict)] if tool_name == "collection_search" else [],
            })
            findings.append({
                "kind": "source_result",
                "text": str(result.get("summary") or "")[:500],
                "dependencies": refs + dependency_refs,
                "message_seq": int(item.get("seq") or 0),
            })
        answered_user_ids, pending_users = self._observable_progress(messages, task_messages)
        if answered_user_ids:
            findings.append({
                "kind": "task_progress",
                "text": f"已有最终回答覆盖 {len(answered_user_ids)} 条用户要求",
                "dependencies": [],
            })
        materials = self._dedupe_keep_last(
            materials,
            key=lambda item: json.dumps({
                "tool": item["tool"], "source_refs": item["source_refs"],
                "view": item["view"], "coverage": item["coverage"],
                "summary": item["summary"],
            }, ensure_ascii=False, sort_keys=True),
        )
        findings = self._dedupe_keep_last(
            findings,
            key=lambda item: json.dumps({
                "kind": item["kind"], "text": item["text"],
                "dependencies": item["dependencies"],
            }, ensure_ascii=False, sort_keys=True),
        )
        # A previous note can be invalidated by a cancelled run, forgotten memory,
        # or a changed source. Reattach each summary only to its still-visible
        # observation, then validate its own dependencies before inheriting it.
        observations = {}
        for item in covered:
            if item.get("role") != "tool":
                continue
            try:
                result = json.loads(str(item.get("content") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            observations[int(item.get("seq") or 0)] = (item, result)
        if existing:
            for value in existing["findings"]:
                if value.get("kind") != "semantic_summary":
                    continue
                seq = int(value.get("message_seq") or 0)
                if seq > covered_until_message_seq or seq not in observations:
                    continue
                observation, result = observations[seq]
                source_ref = str(value.get("source_ref") or next(
                    (ref for ref in value.get("dependencies") or []
                     if str(ref).startswith("video:")), ""))
                if not source_ref or source_ref not in (result.get("source_refs") or []):
                    continue
                refs = list(dict.fromkeys([
                    *[str(ref) for ref in value.get("dependencies") or []],
                    *[str(ref) for ref in result.get("dependency_refs") or []],
                    str(result.get("result_ref") or ""), source_ref,
                ]))
                refs = [ref for ref in refs if ref]
                if not self._summary_dependencies_valid(
                    refs, space_id=int(space["id"]),
                    thread_id=str(run_context["thread"]["id"]),
                    scope_version=int(space["scope_version"]),
                ):
                    continue
                inherited = {**value, "dependencies": refs,
                             "source_ref": source_ref,
                             "source_run_id": str(observation.get("run_id") or "")}
                findings.append(inherited)
                dependencies.extend(refs)
                if observation.get("run_id"):
                    source_run_ids.append(str(observation["run_id"]))
        return {
            "expected_version": int(existing["note_version"]) if existing else 0,
            "covered_until_message_seq": covered_until_message_seq,
            "source_run_ids": list(dict.fromkeys(source_run_ids)),
            "goal": goal[:2000],
            "explicit_constraints": constraints,
            "searched_scope_and_material_refs": materials[-30:],
            "findings": findings[-36:],
            "open_questions": [
                {
                    "message_id": str(item["id"]),
                    "message_seq": int(item["seq"]),
                    "quote": "；".join(active_clauses.get(str(item["id"]), []))[:1000],
                    "status": "unknown_pending",
                }
                for item in pending_users
                if active_clauses.get(str(item["id"]))
            ],
            "next_actions": (
                ["继续处理未获得最终回答的要求；按 message_id 回读原文"]
                if any(active_clauses.get(str(item["id"])) for item in pending_users) else []
            ),
            "dependencies": list(dict.fromkeys(dependencies)),
            "scope_version": int(space["scope_version"]),
            "memory_generation": int(run_context["run"].get("observed_memory_epoch", 0)),
        }

    def commit(
        self, thread_id: str, candidate: dict[str, Any], *, task_segment: int = 1,
        run_id: str | None = None, run_epoch: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        expected_version = int(candidate["expected_version"])
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if run_id is not None:
                active = connection.execute(
                    "SELECT 1 FROM assistant_runs WHERE id=? AND thread_id=? "
                    "AND status='running' AND run_epoch=? AND cancel_requested=0",
                    (run_id, thread_id, run_epoch),
                ).fetchone()
                if active is None:
                    raise AssistantConflict("semantic_run_terminated")
            thread = connection.execute(
                "SELECT space_id FROM assistant_threads WHERE id=? AND principal_id=?",
                (thread_id, self.principal_id),
            ).fetchone()
            if thread is None:
                raise KeyError(thread_id)
            space = connection.execute(
                "SELECT scope_version FROM assistant_spaces WHERE id=? AND principal_id=?",
                (thread["space_id"], self.principal_id),
            ).fetchone()
            if space is None or int(space["scope_version"]) != int(candidate["scope_version"]):
                raise AssistantConflict("task_note_scope_changed")
            current_epoch = self._memory_epoch(connection)
            if current_epoch != int(candidate["memory_generation"]):
                raise AssistantConflict("task_note_memory_changed")
            if not self._memory_refs_valid(
                connection,
                [value for value in candidate["dependencies"] if str(value).startswith("memory:")],
                space_id=int(thread["space_id"]),
            ):
                raise AssistantConflict("task_note_dependency_changed")
            if self.dependency_ref_validator is not None:
                refs = [str(value) for value in candidate["dependencies"]]
                if not self.dependency_ref_validator(
                    refs, int(thread["space_id"]), thread_id,
                    int(candidate["scope_version"]),
                ):
                    raise AssistantConflict("task_note_dependency_changed")
            existing = connection.execute(
                "SELECT * FROM assistant_task_notes WHERE thread_id=? AND task_segment=?",
                (thread_id, task_segment),
            ).fetchone()
            actual_version = int(existing["note_version"]) if existing else 0
            if actual_version != expected_version:
                raise AssistantConflict("task_note_version_conflict")
            note_id = str(existing["id"]) if existing else f"atn_{uuid.uuid4().hex}"
            next_version = actual_version + 1
            values = (
                int(candidate["covered_until_message_seq"]),
                json.dumps(candidate["source_run_ids"], ensure_ascii=False),
                str(candidate["goal"]),
                json.dumps(candidate["explicit_constraints"], ensure_ascii=False),
                json.dumps(candidate["searched_scope_and_material_refs"], ensure_ascii=False),
                json.dumps(candidate["findings"], ensure_ascii=False),
                json.dumps(candidate["open_questions"], ensure_ascii=False),
                json.dumps(candidate["next_actions"], ensure_ascii=False),
                json.dumps(candidate["dependencies"], ensure_ascii=False),
                int(candidate["scope_version"]), int(candidate["memory_generation"]), now,
            )
            if existing:
                connection.execute(
                    """
                    UPDATE assistant_task_notes SET note_version=?, covered_until_message_seq=?,
                        source_run_ids_json=?, goal=?, explicit_constraints_json=?,
                        searched_scope_and_material_refs_json=?, findings_json=?,
                        open_questions_json=?, next_actions_json=?, dependencies_json=?,
                        scope_version=?, memory_generation=?, status='active', updated_at=?
                    WHERE id=? AND note_version=?
                    """,
                    (next_version, *values, note_id, expected_version),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO assistant_task_notes(
                        id,thread_id,task_segment,note_version,covered_until_message_seq,
                        source_run_ids_json,goal,explicit_constraints_json,
                        searched_scope_and_material_refs_json,findings_json,open_questions_json,
                        next_actions_json,dependencies_json,scope_version,memory_generation,status,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?)
                    """,
                    (note_id, thread_id, task_segment, next_version, *values[:-1], now, now),
                )
        note = self.get(thread_id, task_segment=task_segment)
        if note is None:
            raise RuntimeError("task_note_commit_missing")
        return note

    def commit_semantic_findings(
        self, thread_id: str, note: dict[str, Any],
        findings: list[dict[str, Any]], *, run_id: str, run_epoch: int,
    ) -> dict[str, Any]:
        candidate = {
            "expected_version": int(note["note_version"]),
            "covered_until_message_seq": int(note["covered_until_message_seq"]),
            "source_run_ids": note["source_run_ids"],
            "goal": note["goal"],
            "explicit_constraints": note["explicit_constraints"],
            "searched_scope_and_material_refs": note["searched_scope_and_material_refs"],
            "findings": [*note["findings"], *findings][-36:],
            "open_questions": note["open_questions"],
            "next_actions": note["next_actions"],
            "dependencies": list(dict.fromkeys([
                *note["dependencies"],
                *(ref for finding in findings for ref in finding.get("dependencies") or []),
            ])),
            "scope_version": note["scope_version"],
            "memory_generation": note["memory_generation"],
        }
        return self.commit(thread_id, candidate, run_id=run_id, run_epoch=run_epoch)

    def _summary_dependencies_valid(self, refs: list[str], *, space_id: int,
                                    thread_id: str, scope_version: int) -> bool:
        memory_refs = [ref for ref in refs if ref.startswith("memory:")]
        source_refs = [ref for ref in refs if ref.startswith("video:")]
        return (
            (not memory_refs or self.memories.validate_dependency_refs(
                memory_refs, space_id=space_id)["valid"])
            and (not source_refs or self.source_ref_validator is None
                 or self.source_ref_validator(source_refs, space_id))
            and (self.dependency_ref_validator is None
                 or self.dependency_ref_validator(refs, space_id, thread_id, scope_version))
        )

    @staticmethod
    def render(note: dict[str, Any], *, delivered_spans: list[dict[str, Any]] | None = None,
               source_titles: dict[str, str] | None = None,
               search_evidence: list[dict[str, Any]] | None = None,
               compact: bool = False) -> str:
        if compact:
            return json.dumps({
                "目标": note["goal"],
                "明确限制原话": note["explicit_constraints"],
                "已查范围与阅读程度": [{
                    key: value for key, value in item.items()
                    if key in {"tool", "source_refs", "view", "coverage", "result_ref", "next_cursor"}
                } for item in note["searched_scope_and_material_refs"][-12:]],
                "阶段结果": [{"semantic": TaskNoteService._render_semantic(item),
                              "dependencies": item.get("dependencies", []),
                              "source_position": item.get("position")}
                             for item in note["findings"]
                             if item.get("kind") == "semantic_summary"][-8:],
                "未解决问题": note["open_questions"],
                "后续步骤": note["next_actions"],
            }, ensure_ascii=False)
        materials = []
        delivered_spans = delivered_spans or []
        source_titles = source_titles or {}
        semantic_spans = [
            {"source_ref": next(iter(value.get("dependencies") or []), None),
             "view": value.get("view"), **(value.get("position") or {})}
            for value in note["findings"] if value.get("kind") == "semantic_summary"
            and isinstance(value.get("position"), dict)
        ]
        for item in note["searched_scope_and_material_refs"]:
            coverage = item.get("coverage")
            if isinstance(coverage, dict):
                coverage = {
                    key: coverage[key]
                    for key in (
                        "mode", "exhaustive", "matched_count", "candidate_limit",
                        "body_available_count", "body_indexed_count",
                        "read_position", "read_complete", "selection",
                    )
                    if key in coverage
                }
            material = {
                "tool": item.get("tool"),
                "source_refs": item.get("source_refs", []),
                "view": item.get("view"),
                "coverage": coverage,
                "summary": str(item.get("summary") or "")[:240],
                "result_ref": item.get("result_ref"),
                "next_cursor": item.get("next_cursor"),
                "title": item.get("title") or source_titles.get(
                    str(next(iter(item.get("source_refs") or []), "")).split(":", 2)[1]
                    if item.get("source_refs") and str(item["source_refs"][0]).startswith("video:") else "", ""
                ),
                "query": item.get("query"),
                "require_transcript": item.get("require_transcript"),
                "candidates": item.get("candidates") or [],
                "model_read": TaskNoteService._delivered_coverage(
                    item, delivered_spans, semantic_spans
                ),
            }
            materials.append({key: value for key, value in material.items()
                              if value not in (None, "", [], {})})
        payload = {
            "目标": note["goal"],
            "明确限制原话": note["explicit_constraints"],
            "已查范围与阅读程度": materials,
            "整体阅读覆盖": TaskNoteService._overall_read_coverage(materials),
            "阶段结果": [
                {
                    "kind": item.get("kind"),
                    **({"semantic": TaskNoteService._render_semantic(item)}
                       if item.get("kind") == "semantic_summary" else
                       {"text": str(item.get("text") or "")[:300]}),
                    "dependencies": item.get("dependencies", []),
                    **({"source_position": item.get("position")}
                       if item.get("kind") == "semantic_summary" else {}),
                }
                for item in note["findings"]
                if item.get("kind") != "source_result" or not any(
                    value.get("kind") == "semantic_summary"
                    and int(value.get("covered_until_message_seq") or 0) >= int(item.get("message_seq") or 0)
                    for value in note["findings"]
                )
            ],
            "未解决问题": note["open_questions"],
            "后续步骤": note["next_actions"],
        }
        if search_evidence:
            payload["已验证搜索动作"] = search_evidence[-3:]
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _overall_read_coverage(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_source: dict[tuple[str, str], dict[str, Any]] = {}
        for material in materials:
            progress = material.get("model_read") or {}
            if not progress:
                continue
            source_ref = str(next(iter(material.get("source_refs") or []), ""))
            view = str(material.get("view") or "")
            key = (source_ref, view)
            entry = by_source.setdefault(key, {
                "source_ref": source_ref, "view": view,
                "total": progress.get("total"),
                "complete_available_view_processed": False,
            })
            entry["complete_available_view_processed"] = bool(
                entry["complete_available_view_processed"]
                or progress.get("complete_available_view_processed"))
        return list(by_source.values())[-12:]

    @staticmethod
    def _render_semantic(item: dict[str, Any]) -> dict[str, Any]:
        value = item.get("semantic")
        if not isinstance(value, dict):
            try:
                value = json.loads(str(item.get("text") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                value = {"findings": [str(item.get("text") or "")]}
        return TaskNoteService.bound_semantic(value)

    @staticmethod
    def bound_semantic(value: Any) -> dict[str, list[str]]:
        """Bound each category independently, keeping its beginning and tail."""
        if not isinstance(value, dict):
            value = {"findings": [str(value)]}
        expanded: dict[str, list[Any]] = {
            key: [] for key in ("findings", "conditions", "disagreements", "open_questions")
        }
        for key in expanded:
            raw = value.get(key) or []
            for entry in raw if isinstance(raw, list) else [raw]:
                if not isinstance(entry, dict):
                    expanded[key].append(entry)
                    continue
                topic = str(entry.get("topic") or entry.get("claim") or "")
                evidence = entry.get("evidence") or []
                if isinstance(evidence, dict):
                    evidence = [evidence]
                if isinstance(evidence, list) and evidence:
                    for proof in evidence:
                        if isinstance(proof, dict):
                            expanded[key].append("；".join(part for part in (
                                topic, str(proof.get("position") or ""),
                                str(proof.get("text") or proof.get("quote") or ""),
                            ) if part))
                        else:
                            expanded[key].append("；".join(part for part in (topic, str(proof)) if part))
                else:
                    expanded[key].append("；".join(part for part in (
                        topic, str(entry.get("text") or entry.get("summary") or ""),
                    ) if part))
                for nested in ("conditions", "disagreements", "open_questions"):
                    nested_values = entry.get(nested) or []
                    expanded[nested].extend(nested_values if isinstance(nested_values, list)
                                            else [nested_values])
        result: dict[str, list[str]] = {}
        for key, limit in (("findings", 10), ("conditions", 7),
                           ("disagreements", 5), ("open_questions", 5)):
            values = [" ".join(str(entry).split())[:260]
                      for entry in expanded[key] if str(entry).strip()]
            values = [entry for entry in values if not re.search(
                r"(?:本段|本分段|本片段|当前片段|当前分段|此段|这一段)"
                r".{0,12}(?:未见|未涉及|未详述|未给出|未覆盖|未交代|无法就)", entry)]
            if key == "open_questions":
                # These are only observations about this segment. The source may
                # already have been fully read by the time the answer is made.
                values = [entry for entry in values if not any(marker in entry for marker in (
                    "后续片段", "后续内容未", "本段结束", "本分段结束",
                ))]
            if len(values) > limit:
                values = [*values[:limit - 2], *values[-2:]]
            result[key] = list(dict.fromkeys(values))
        if not any(result.values()) and value.get("summary"):
            result["findings"] = [str(value["summary"])[:600]]
        return result

    @staticmethod
    def _delivered_coverage(item: dict[str, Any], spans: list[dict[str, Any]],
                            semantic_spans: list[dict[str, Any]]) -> dict[str, Any] | None:
        coverage = item.get("coverage") or {}
        if not isinstance(coverage, dict) or coverage.get("requested_view") is None:
            return None
        position = coverage.get("read_position") or {}
        source_ref = next(iter(item.get("source_refs") or []), None)
        matched = [span for span in spans
                   if span.get("source_ref") == source_ref
                   and span.get("view") == coverage.get("requested_view")]
        summarized = [span for span in semantic_spans
                      if span.get("source_ref") == source_ref
                      and span.get("view") == coverage.get("requested_view")]
        start = int(position.get("start") or 0)
        end = int(position.get("end") or 0)
        received = any(int(span.get("start") or 0) <= start
                       and int(span.get("end") or 0) >= end for span in matched)
        cursor = 0
        for span in sorted([*matched, *summarized], key=lambda value: int(value.get("start") or 0)):
            if int(span.get("start") or 0) > cursor:
                break
            cursor = max(cursor, int(span.get("end") or 0))
        return {"range": [start, end], "total": int(position.get("total") or 0),
                "received_by_answer_model": received,
                "compressed_for_answer": any(int(span.get("start") or 0) <= start and
                                               int(span.get("end") or 0) >= end for span in summarized),
                "complete_available_view_processed": bool((matched or summarized) and
                                                          cursor >= int(position.get("total") or 0))}

    @staticmethod
    def _current_task_messages(user_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the current explicit task; a clear task reset starts a new segment."""
        start = 0
        reset_markers = (
            "开始新任务", "开始一个新任务", "换一个任务", "换个任务",
            "忽略之前所有要求", "撤回之前所有要求", "重新开始这个任务",
        )
        for index, item in enumerate(user_messages):
            text = " ".join(str(item.get("content") or "").split())
            if any(marker in text for marker in reset_markers):
                start = index
        return user_messages[start:]

    @classmethod
    def _effective_task_state(
        cls, user_messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], str, dict[str, list[str]], list[str]]:
        markers = (
            "必须", "不要", "只", "需要", "限制", "优先", "继续", "补充",
            "改成", "改为", "不能", "不得", "保持", "停止", "不再",
        )
        clauses: list[dict[str, Any]] = []
        withdrawn_targets: list[str] = []
        first_id = str(user_messages[0]["id"]) if user_messages else ""
        for item in user_messages:
            text = " ".join(str(item.get("content") or "").split())
            if not text:
                continue
            message_id = str(item["id"])
            message_seq = int(item["seq"])
            replacement = re.search(
                r"把([^；;。]{1,160}?)(?:改成|改为)([^；;。]{1,300})", text
            )
            if replacement:
                old = replacement.group(1).strip(" ：:，,。")
                raw_new = replacement.group(2)
                extra = re.search(r"[，,](?=\s*(?:同时|但是|但))", raw_new)
                if old:
                    removed = [value for value in clauses if old in str(value["quote"])]
                    clauses = [value for value in clauses if old not in str(value["quote"])]
                    withdrawn_targets.append(old)
                    new = raw_new[:extra.start()] if extra else raw_new
                    new = new.strip(" ：:，,。；;")
                    if new:
                        clauses.append({
                            "message_id": message_id,
                            "message_seq": message_seq,
                            "quote": new[:1000],
                            "constraint": True,
                            "goal_clause": any(value["goal_clause"] for value in removed),
                        })
                tail = raw_new[extra.start():] if extra else ""
                text = (tail + text[replacement.end():]).lstrip(" ：:，,。；;")
                text = re.sub(r"^(?:同时|但是|但)", "", text).strip()
                if not text:
                    continue
            withdrawal = re.search(
                r"(?:取消|撤回|不再需要)(?:之前)?(?:关于)?(.{1,160}?)(?:的要求|这一要求|这个要求|[。；;]|$)",
                text,
            )
            if withdrawal:
                target = withdrawal.group(1).strip(" ：:，,")
                if target:
                    clauses = [
                        value for value in clauses if target not in str(value["quote"])
                    ]
                    withdrawn_targets.append(target)
                text = text[withdrawal.end():].lstrip(" ：:，,。；;")
                text = re.sub(r"^(?:同时|但是|但)", "", text).strip()
                if not text:
                    continue
            for clause in re.split(
                r"[；;。\n]+|[，,](?=\s*(?:必须|只|不要|不得|不能|需要|优先|保持))",
                text,
            ):
                clause = clause.strip(" ，,：:")
                if clause:
                    clauses.append({
                        "message_id": message_id,
                        "message_seq": message_seq,
                        "quote": clause[:1000],
                        "constraint": any(marker in clause for marker in markers)
                        or len(user_messages) <= 3,
                        "goal_clause": message_id == first_id,
                    })
        constraints = [
            {key: value[key] for key in ("message_id", "message_seq", "quote")}
            for value in clauses if value["constraint"]
        ]
        goal_clauses = [str(value["quote"]) for value in clauses if value["goal_clause"]]
        goal = "；".join(goal_clauses) or (
            str(clauses[0]["quote"]) if clauses else "当前任务的原要求已撤回"
        )
        active_by_message: dict[str, list[str]] = {}
        for value in clauses:
            active_by_message.setdefault(str(value["message_id"]), []).append(
                str(value["quote"])
            )
        return constraints, goal, active_by_message, withdrawn_targets

    @staticmethod
    def _observable_progress(
        covered: list[dict[str, Any]], task_messages: list[dict[str, Any]]
    ) -> tuple[set[str], list[dict[str, Any]]]:
        """A user request is complete only after a later non-tool final answer."""
        task_ids = {str(item["id"]) for item in task_messages}
        answered: set[str] = set()
        pending: list[dict[str, Any]] = []
        for user in task_messages:
            user_seq = int(user.get("seq") or 0)
            has_final = any(
                int(item.get("seq") or 0) > user_seq
                and item.get("role") == "assistant"
                and bool(str(item.get("content") or "").strip())
                and not TaskNoteService._payload(item).get("tool_calls")
                for item in covered
            )
            if has_final:
                answered.add(str(user["id"]))
            else:
                pending.append(user)
        return answered.intersection(task_ids), pending

    @staticmethod
    def _dedupe_keep_last(
        values: list[dict[str, Any]], *, key: Any
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in reversed(values):
            marker = str(key(item))
            if marker in seen:
                continue
            seen.add(marker)
            result.append(item)
        return list(reversed(result))

    @staticmethod
    def _payload(message: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(message.get("provider_payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _memory_epoch(connection: Any) -> int:
        row = connection.execute(
            "SELECT value FROM assistant_runtime_state WHERE key='memory_epoch'"
        ).fetchone()
        return int(row["value"] if row else 0)

    def _memory_refs_valid(
        self, connection: Any, refs: list[str], *, space_id: int
    ) -> bool:
        now = utc_now()
        for ref in refs:
            parts = str(ref).split(":")
            if len(parts) != 3 or parts[0] != "memory" or not parts[2].isdigit():
                return False
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
                (parts[1], self.principal_id),
            ).fetchone()
            if row is None:
                return False
            if str(row["status"]) != "active" or int(row["version"]) != int(parts[2]):
                return False
            if str(row["scope_kind"]) == "space" and str(row["scope_id"]) != str(space_id):
                return False
            if row["valid_from"] and str(row["valid_from"]) > now:
                return False
            if row["expires_at"] and str(row["expires_at"]) <= now:
                return False
        return True

    @staticmethod
    def _decode(value: dict[str, Any]) -> dict[str, Any]:
        for field in (
            "source_run_ids", "explicit_constraints", "searched_scope_and_material_refs",
            "findings", "open_questions", "next_actions", "dependencies",
        ):
            value[field] = json.loads(value.pop(f"{field}_json"))
        return value
