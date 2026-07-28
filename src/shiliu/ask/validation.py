from __future__ import annotations

from dataclasses import dataclass

from shiliu.ask.context import ContextBuildResult
from shiliu.ask.contracts import GroundedAnswerDraft
from shiliu.ask.evidence import TranscriptEvidenceMaterializer


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def validate_grounded_answer(
    draft: GroundedAnswerDraft,
    *,
    context: ContextBuildResult,
    materializer: TranscriptEvidenceMaterializer,
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if draft.status == "insufficient" and draft.answer_blocks:
        issues.append(
            ValidationIssue(
                "insufficient_has_blocks",
                "answer_blocks",
                "insufficient output must not contain answer blocks",
            )
        )
    if draft.status != "insufficient" and not draft.answer_blocks:
        issues.append(
            ValidationIssue(
                "answer_blocks_missing",
                "answer_blocks",
                "complete or partial output requires answer blocks",
            )
        )
    if draft.status == "partial" and not any(
        value.strip() for value in draft.limitations
    ):
        issues.append(
            ValidationIssue(
                "partial_limitations_missing",
                "limitations",
                "partial output must identify the remaining evidence gap",
            )
        )
    if draft.status == "insufficient" and not any(
        value.strip() for value in draft.limitations
    ):
        issues.append(
            ValidationIssue(
                "insufficient_limitations_missing",
                "limitations",
                "insufficient output must explain the evidence limitation",
            )
        )

    allowlist = set(context.citation_allowlist)
    span_by_id = {value.citation_id: value for value in context.spans}
    used: set[str] = set()
    for block_index, block in enumerate(draft.answer_blocks):
        if not block.citation_ids:
            issues.append(
                ValidationIssue(
                    "block_citation_missing",
                    f"answer_blocks.{block_index}.citation_ids",
                    "every answer block requires at least one citation",
                )
            )
            continue
        if len(set(block.citation_ids)) != len(block.citation_ids):
            issues.append(
                ValidationIssue(
                    "duplicate_block_citation",
                    f"answer_blocks.{block_index}.citation_ids",
                    "citation IDs must not repeat within one answer block",
                )
            )
        for citation_index, citation_id in enumerate(block.citation_ids):
            if citation_id not in allowlist:
                issues.append(
                    ValidationIssue(
                        "unknown_citation",
                        (
                            f"answer_blocks.{block_index}."
                            f"citation_ids.{citation_index}"
                        ),
                        "citation ID is not in the current context allowlist",
                    )
                )
                continue
            used.add(citation_id)

    for citation_id in sorted(used):
        try:
            materializer.validate_current(span_by_id[citation_id])
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    getattr(exc, "code", "citation_validation_failed"),
                    f"citations.{citation_id}",
                    str(exc)[:300],
                )
            )
    return tuple(issues)
