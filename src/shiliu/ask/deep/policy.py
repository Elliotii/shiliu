from __future__ import annotations


DEEP_POLICY_VERSION = "v4-deep-policy-v1"

DEEP_POLICY_INSTRUCTIONS = (
    "Choose exactly one bounded search action. Return JSON matching the schema. "
    "Navigation is navigation_only and is never factual evidence. Only "
    "transcript_evidence may support the final answer. Preserve the user's core "
    "concepts and question type in search queries, including comparison intent; do "
    "not reduce a cross-video comparison to generic topic keywords. Treat "
    "open_questions as important aspects of the final answer that remain genuinely "
    "unanswered. Mark one resolved only when the cited transcript quote directly "
    "answers that question; topical relevance, conceptual similarity, keyword "
    "overlap, or a valid citation ID is not resolution. Start from the original "
    "question and, with no observations, normally begin with search_navigation. "
    "React to observations, use focused transcript search for promising videos, "
    "read an authoritative window when adjacent context is needed, and avoid "
    "repeated scoped queries and windows. Finish when direct transcript evidence "
    "sufficiently covers the core user question. Continue when an important "
    "requested answer gap remains and another bounded search is likely to help; if "
    "the answer is useful but further search has low expected value, finish and let "
    "the final answer report the gap honestly as partial. Do not answer the question "
    "in this action."
)
