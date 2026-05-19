from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel


MeetingType = Literal[
    "standup",
    "sprint_planning",
    "retrospective",
    "exec_review",
    "1-on-1",
    "all_hands",
    "design_review",
    "incident_review",
    "unknown",
]


class ActionItem(BaseModel):
    task: str
    owner: str | None
    deadline: str | None
    priority: Literal["high", "medium", "low"]


class RiskFlag(BaseModel):
    description: str
    severity: Literal["critical", "moderate", "low"]


class MeetingOutput(BaseModel):
    meeting_title: str | None
    date: str | None
    participants: list[str]
    meeting_type: MeetingType = "unknown"
    meeting_type_confidence: float = 0.0
    decisions: list[str]
    action_items: list[ActionItem]
    open_questions: list[str]
    risk_flags: list[RiskFlag]
    formatted_follow_up: str
    summary: str

    @property
    def follow_up_email(self) -> str:
        return self.formatted_follow_up


# ── Feature 1: Normalizer ──────────────────────────────────────────────────

class NormalizedTranscript(BaseModel):
    text: str
    source_format: str
    speaker_count: int
    estimated_duration_minutes: float | None
    was_normalized: bool


# ── Feature 3: Batch Processing ────────────────────────────────────────────

class BatchFileResult(BaseModel):
    filename: str
    status: Literal["success", "failed"]
    output: MeetingOutput | None
    error: str | None
    duration_seconds: float


class BatchResult(BaseModel):
    total_files: int
    succeeded: int
    failed: int
    results: list[BatchFileResult]
    digest: Any | None = None  # WeeklyDigest | None — avoid circular ref


# ── Feature 4: Commitment Tracker ─────────────────────────────────────────

class MissedCommitment(BaseModel):
    original_task: str
    original_owner: str | None
    original_deadline: str | None
    committed_in_meeting: str
    committed_on_date: str | None
    meetings_elapsed: int
    severity: Literal["critical", "moderate", "low"]


class CommitmentTrackerResult(BaseModel):
    missed_commitments: list[MissedCommitment]
    commitment_completion_rate: float
    highest_risk_owner: str | None
    summary: str


# ── Feature 5: Weekly Digest ───────────────────────────────────────────────

class WeeklyDigest(BaseModel):
    week_label: str
    total_meetings: int
    total_action_items: int
    total_decisions: int
    top_decisions: list[str]
    open_items_by_owner: dict[str, list[str]]
    escalated_risks: list[str]
    carry_forward_items: list[str]
    digest_email: str
