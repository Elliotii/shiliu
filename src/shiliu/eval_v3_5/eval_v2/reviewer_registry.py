from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .contracts import ANNOTATION_REVIEW_SCHEMA_VERSION
from .reviewer_draft import REVIEWER_DRAFT_SCHEMA_VERSION


@dataclass(frozen=True)
class ReviewerProviderConfig:
    provider_id: Literal["openai", "deepseek"]
    usage: Literal["annotation_primary_review", "annotation_secondary_review"]
    model: str
    api_style: Literal["responses", "chat_completions"]
    reasoning_effort: Literal["high", "max"]
    temperature_policy: Literal["omitted_unless_supported"]
    draft_schema_version: str
    canonical_schema_version: str
    prompt_version: str
    repair_prompt_version: str
    max_repairs: Literal[1]
    key_env_var: str
    thinking: Literal["enabled"] | None = None


PRIMARY_REVIEWER = ReviewerProviderConfig(
    provider_id="openai",
    usage="annotation_primary_review",
    model="gpt-5.6-terra",
    api_style="responses",
    reasoning_effort="high",
    temperature_policy="omitted_unless_supported",
    draft_schema_version=REVIEWER_DRAFT_SCHEMA_VERSION,
    canonical_schema_version=ANNOTATION_REVIEW_SCHEMA_VERSION,
    prompt_version="v3.5-primary-reviewer-draft-prompt-v3-query-grounded",
    repair_prompt_version="v3.5-primary-reviewer-draft-repair-prompt-v2-query-grounded",
    max_repairs=1,
    key_env_var="OPENAI_API_KEY",
)

SECONDARY_REVIEWER = ReviewerProviderConfig(
    provider_id="deepseek",
    usage="annotation_secondary_review",
    model="deepseek-v4-pro",
    api_style="chat_completions",
    reasoning_effort="max",
    temperature_policy="omitted_unless_supported",
    draft_schema_version=REVIEWER_DRAFT_SCHEMA_VERSION,
    canonical_schema_version=ANNOTATION_REVIEW_SCHEMA_VERSION,
    prompt_version="v3.5-secondary-reviewer-draft-prompt-v2-query-grounded",
    repair_prompt_version="v3.5-secondary-reviewer-draft-repair-prompt-v2-query-grounded",
    max_repairs=1,
    key_env_var="DEEPSEEK_API_KEY",
    thinking="enabled",
)


REVIEWER_PROVIDER_REGISTRY = {
    PRIMARY_REVIEWER.usage: PRIMARY_REVIEWER,
    SECONDARY_REVIEWER.usage: SECONDARY_REVIEWER,
}
