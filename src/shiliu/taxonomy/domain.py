from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"

    @property
    def discovery_eligible(self) -> bool:
        return self is not EvidenceLevel.D


class FolderMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int
    account_id: int | None = None
    account_name: str = ""
    folder_id: int
    folder_name: str
    favorite_time: int | None = None
    source_position: int
    first_observed_at: str


class StoredClassificationCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_key: str
    video_id: int | None = None
    title: str
    uploader: str = ""
    description: str = ""
    one_line_summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    projects_tools_models: list[str] = Field(default_factory=list)
    source_ids: list[int] = Field(default_factory=list)
    folder_names: list[str] = Field(default_factory=list)
    memberships: list[FolderMembership] = Field(default_factory=list)
    evidence_level: EvidenceLevel


class DiscoveryCardView(BaseModel):
    """The only card projection permitted in open discovery by default."""

    model_config = ConfigDict(extra="forbid")

    content_id: str
    title: str
    uploader: str = ""
    description: str = ""
    one_line_summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    projects_tools_models: list[str] = Field(default_factory=list)
    evidence_level: EvidenceLevel


class CardPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_key: str
    video_id: int | None = None
    evidence_level: EvidenceLevel
    discovery_eligible: bool
    selected_revision: str | None = None
    stored_card: StoredClassificationCard
    discovery_view: DiscoveryCardView
    card_hash: str
    discovery_view_hash: str


class CorpusPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_source_ids: list[int]
    membership_count: int
    total_cards: int
    duplicate_memberships_merged: int
    discovery_eligible_count: int
    trial_assignment_only_count: int
    evidence_counts: dict[str, int]
    cards: list[CardPreview]


class FrozenSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: int
    snapshot_hash: str
    reused: bool
    selected_source_ids: list[int]
    membership_count: int
    total_cards: int
    duplicate_memberships_merged: int
    discovery_eligible_count: int
    trial_assignment_only_count: int
    evidence_counts: dict[str, int]
    created_at: str


def build_discovery_view(card: StoredClassificationCard) -> DiscoveryCardView:
    return DiscoveryCardView(
        content_id=card.content_key,
        title=card.title,
        uploader=card.uploader,
        description=card.description,
        one_line_summary=card.one_line_summary,
        key_points=list(card.key_points),
        projects_tools_models=list(card.projects_tools_models),
        evidence_level=card.evidence_level,
    )
