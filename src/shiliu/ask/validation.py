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

    normalized_blocks: dict[str, int] = {}
    for block_index, block in enumerate(draft.answer_blocks):
        normalized_text = " ".join(block.text.casefold().split()).rstrip("。.!！?")
        previous_index = normalized_blocks.get(normalized_text)
        if previous_index is not None:
            issues.append(
                ValidationIssue(
                    "duplicate_answer_block",
                    f"answer_blocks.{block_index}.text",
                    (
                        "answer block repeats the normalized text of "
                        f"answer_blocks.{previous_index}"
                    ),
                )
            )
        else:
            normalized_blocks[normalized_text] = block_index
    return tuple(issues)
