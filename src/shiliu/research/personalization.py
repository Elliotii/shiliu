from __future__ import annotations

import hashlib
import json
from typing import Any


PERSONALIZATION_CONTEXT_POLICY_VERSION = "v5-c-stage1-personalization-context-v1"
ANSWER_PRESENTATION_EFFECT_SCOPE = "research_answer_presentation_only"
LIMITATIONS_POSITION_KEY = "answer.presentation.limitations_position"
LIMITATIONS_POSITIONS = {"before_answer", "after_answer"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized(value: object) -> str:
    return " ".join(str(value).casefold().split())


class PersonalizationContextProjection:
    """Read-only Stage 1 projection over effective WorkspaceRecord revisions."""

    def project(
        self, records: list[dict[str, Any]], *, enabled: bool = True
    ) -> dict[str, Any]:
        reasons: list[str] = []
        preference_candidates: list[tuple[dict[str, Any], str]] = []
        relevant_records = [
            value
            for value in records
            if value.get("semantic_key") == LIMITATIONS_POSITION_KEY
        ]
        for record in relevant_records:
            decoded = self._preference_value(record)
            if decoded is not None:
                preference_candidates.append((record, decoded))
                continue
            status = str(record.get("effective_status") or "")
            if status == "candidate":
                reasons.append("candidate_not_confirmed")
            elif status == "expired":
                reasons.append("record_expired")
            elif status in {"rejected", "tombstoned", "invalidated", "superseded"}:
                reasons.append("terminal_record_not_applied")
            else:
                reasons.append("malformed_or_unauthorized_preference")

        preference: dict[str, Any] | None = None
        values = {value for _, value in preference_candidates}
        if len(values) > 1:
            reasons.append("confirmed_preference_conflict_fail_closed")
        elif preference_candidates:
            selected, selected_value = max(
                preference_candidates,
                key=lambda item: (
                    str(item[0].get("created_at") or ""),
                    int(item[0].get("version") or 0),
                    str(item[0].get("record_revision_id") or ""),
                ),
            )
            preference = self._record_reference(selected, value=selected_value)
            if len(preference_candidates) > 1:
                reasons.append("matching_confirmed_preferences")

        focus = self._current_focus(records, reasons)
        applied = bool(enabled and preference is not None)
        if not enabled:
            reasons.append("personalization_disabled")
        elif applied:
            reasons.append("confirmed_preference_applied")
        elif not reasons:
            reasons.append("no_confirmed_preference")
        elif not any(
            reason
            in {
                "confirmed_preference_conflict_fail_closed",
                "candidate_not_confirmed",
                "record_expired",
                "terminal_record_not_applied",
                "malformed_or_unauthorized_preference",
            }
            for reason in reasons
        ):
            reasons.append("no_confirmed_preference")

        reason_codes = list(dict.fromkeys(reasons))
        identity = {
            "policy_version": PERSONALIZATION_CONTEXT_POLICY_VERSION,
            "enabled": bool(enabled),
            "applied": applied,
            "effect_scope": ANSWER_PRESENTATION_EFFECT_SCOPE,
            "preference": self._identity_reference(preference),
            "current_focus": self._identity_reference(focus),
            "reason_codes": reason_codes,
        }
        return {
            **identity,
            "preference": preference,
            "current_focus": focus,
            "context_hash": _hash(identity),
            "authority": {
                "source": "workspace_record_effective_revision",
                "behavior": "user_authored_or_user_confirmed_only",
                "candidate": "never_applied_before_confirmation",
                "citation_or_verifier": False,
            },
        }

    @staticmethod
    def _preference_value(record: dict[str, Any]) -> str | None:
        if record.get("authority_class") not in {"user_authored", "user_confirmed"}:
            return None
        if record.get("effective_status") not in {"current", "confirmed"}:
            return None
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return None
        kind = record.get("record_kind")
        if kind == "explicit_memory":
            if set(payload) != {"key", "value"}:
                return None
            if _normalized(payload.get("key")) != LIMITATIONS_POSITION_KEY:
                return None
            value = _normalized(payload.get("value"))
        elif kind == "inferred_candidate":
            if set(payload) != {"statement"}:
                return None
            value = _normalized(payload.get("statement"))
        else:
            return None
        return value if value in LIMITATIONS_POSITIONS else None

    @classmethod
    def _current_focus(
        cls, records: list[dict[str, Any]], reasons: list[str]
    ) -> dict[str, Any] | None:
        eligible = []
        for record in records:
            if (
                record.get("record_kind") != "focus_state"
                or record.get("authority_class") not in {"user_authored", "user_confirmed"}
                or record.get("effective_status") not in {"current", "confirmed"}
            ):
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or set(payload) != {"topic", "state"}:
                reasons.append("malformed_focus_omitted")
                continue
            if _normalized(payload.get("topic")) != record.get("semantic_key"):
                reasons.append("malformed_focus_omitted")
                continue
            if not str(payload.get("state") or "").strip():
                reasons.append("malformed_focus_omitted")
                continue
            eligible.append(record)
        if len(eligible) > 1:
            reasons.append("multiple_current_focus_omitted")
            return None
        if not eligible:
            return None
        record = eligible[0]
        payload = record["payload"]
        return cls._record_reference(
            record,
            topic=str(payload["topic"]),
            state=str(payload["state"]),
        )

    @staticmethod
    def _record_reference(record: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {
            "record_id": str(record["record_id"]),
            "record_revision_id": str(record["record_revision_id"]),
            "version": int(record["version"]),
            "content_hash": str(record["content_hash"]),
            "authority_class": str(record["authority_class"]),
            **extra,
        }

    @staticmethod
    def _identity_reference(value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return {
            key: value[key]
            for key in (
                "record_id",
                "record_revision_id",
                "version",
                "content_hash",
                "value",
                "topic",
                "state",
            )
            if key in value
        }
