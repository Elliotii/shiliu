from __future__ import annotations


DEEP_POLICY_VERSION = "v4-deep-policy-v1"

DEEP_POLICY_INSTRUCTIONS = (
    "Choose exactly one bounded search action. Return JSON matching the schema. "
    "Navigation is navigation_only and is never factual evidence. Only "
    "transcript_evidence citation IDs may resolve questions. Start from the user "
    "query and, when there are no observations yet, normally begin with "
    "search_navigation. React to observations, use focused transcript search for "
    "promising videos, read an authoritative window when a hit needs adjacent "
    "context, avoid repeated scoped queries and windows, and finish when the "
    "available transcript evidence can support a useful answer. Do not answer the "
    "question in this action."
)
