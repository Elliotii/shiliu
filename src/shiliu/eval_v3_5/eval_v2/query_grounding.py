from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .contracts import AnnotationPacketV2


GroundingStatus = Literal[
    "valid", "query_grounding_warning", "query_grounding_invalid"
]

QUERY_GROUNDING_VALIDATOR_VERSION = "v3.5-query-grounding-validator-v1"


@dataclass(frozen=True)
class QueryGroundingValidation:
    status: GroundingStatus
    errors: tuple[str, ...] = ()


_RELATION_TERMS = ("相比", "比较", "优势", "优于", "versus", " vs ", "advantage")
_QUERY_TERM_ALIASES = {"cli": ("命令行", "command line"), "mcp": ("mcp",)}


def validate_query_grounding(draft: object, packet: AnnotationPacketV2) -> QueryGroundingValidation:
    """Validate query anchors and evidence association without changing the label."""
    question = getattr(packet, "evidence_question", None)
    if question is None:
        return QueryGroundingValidation("valid")
    if not isinstance(question, str) or not question.strip():
        return QueryGroundingValidation("query_grounding_invalid", ("missing_evidence_question",))

    aspects = getattr(draft, "required_aspects", ())
    required_spans = getattr(draft, "required_spans", ())
    supported = set(getattr(draft, "supported_aspect_indices", ()))
    errors: list[str] = []
    warnings: list[str] = []

    latin_entities = tuple(
        dict.fromkeys(
            token
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9+._-]*\b", question)
            if len(token) >= 2 and token.upper() == token
        )
    )
    relation_terms = tuple(term for term in _RELATION_TERMS if term.casefold() in question.casefold())
    transcript_by_id = {segment.segment_id: segment.text for segment in packet.full_raw_transcript}
    transcript_text = " ".join(transcript_by_id.values()).casefold()

    for index, aspect in enumerate(aspects):
        anchors = tuple(getattr(aspect, "query_anchor_texts", ()))
        text = str(getattr(aspect, "text", ""))
        if not anchors:
            errors.append(f"aspect_missing_query_anchor:{index}")
            continue
        for anchor in anchors:
            if anchor not in question:
                errors.append(f"anchor_not_evidence_question_substring:{index}:{anchor}")
        if not any(_anchor_is_bound(anchor, text) for anchor in anchors):
            errors.append(f"aspect_not_bound_to_anchor:{index}")
        if latin_entities and not any(
            entity.casefold() in " ".join(anchors).casefold() for entity in latin_entities
        ):
            errors.append(f"aspect_missing_core_entity_anchor:{index}")
        if len(latin_entities) >= 2 and relation_terms and not any(
            term.casefold() in " ".join(anchors).casefold() for term in relation_terms
        ):
            errors.append(f"comparison_aspect_missing_relation_anchor:{index}")

    for span_index, span in enumerate(required_spans):
        mapped = tuple(getattr(span, "supported_aspect_indices", ()))
        selected_text = " ".join(
            transcript_by_id.get(segment_id, "")
            for segment_id in getattr(span, "segment_ids", ())
        ).casefold()
        for aspect_index in mapped:
            if not (0 <= aspect_index < len(aspects)):
                continue
            aspect = aspects[aspect_index]
            anchors = tuple(getattr(aspect, "query_anchor_texts", ()))
            aspect_terms = _significant_terms(str(getattr(aspect, "text", "")), anchors)
            expanded_terms = tuple(
                dict.fromkeys(
                    alias
                    for term in aspect_terms
                    for alias in (term, *_QUERY_TERM_ALIASES.get(term, ()))
                )
            )
            if not any(term in selected_text for term in expanded_terms):
                warnings.append(f"weak_span_aspect_lexical_link:{span_index}:{aspect_index}")

    absent_entities = [entity for entity in latin_entities if entity.casefold() not in transcript_text]
    if latin_entities and len(absent_entities) == len(latin_entities) and supported:
        errors.append("core_query_entities_absent_but_aspect_supported")

    if errors:
        return QueryGroundingValidation("query_grounding_invalid", tuple(dict.fromkeys(errors)))
    if warnings:
        return QueryGroundingValidation("query_grounding_warning", tuple(dict.fromkeys(warnings)))
    return QueryGroundingValidation("valid")


def _significant_terms(text: str, anchors: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for value in (*anchors, text):
        values.extend(token.casefold() for token in re.findall(r"[A-Za-z][A-Za-z0-9+._-]*", value))
        values.extend(term.casefold() for term in _RELATION_TERMS if term.casefold() in value.casefold())
    return tuple(dict.fromkeys(term for term in values if len(term) > 1))


def _anchor_is_bound(anchor: str, aspect_text: str) -> bool:
    anchor_folded = anchor.casefold()
    text_folded = aspect_text.casefold()
    if anchor_folded in text_folded:
        return True
    terms = _significant_terms(anchor, ())
    return bool(terms) and all(term in text_folded for term in terms)
