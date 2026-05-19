from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.models import ActionItem, CommitmentTrackerResult, MeetingOutput, MissedCommitment


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def _make_session(
    title: str,
    date: str,
    action_items: list[ActionItem] | None = None,
    decisions: list[str] | None = None,
) -> MeetingOutput:
    return MeetingOutput(
        meeting_title=title,
        date=date,
        participants=["Alice", "Bob"],
        meeting_type="standup",
        meeting_type_confidence=0.9,
        decisions=decisions or [],
        action_items=action_items or [],
        open_questions=[],
        risk_flags=[],
        formatted_follow_up="Follow-up.",
        summary="Summary.",
    )


def _mock_tracker_response(result: CommitmentTrackerResult):
    mock_client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=result.model_dump_json())]
    mock_client.messages.create.return_value = msg
    return mock_client


def test_missed_commitment_detected_when_not_in_followup():
    sessions = [
        _make_session("Week 1 Standup", "2026-05-12", action_items=[
            ActionItem(task="Write the deployment runbook", owner="Bob", deadline="2026-05-14", priority="high"),
        ]),
        _make_session("Week 2 Standup", "2026-05-19", action_items=[
            ActionItem(task="Fix the Redis latency issue", owner="Alice", deadline=None, priority="medium"),
        ]),
    ]

    expected = CommitmentTrackerResult(
        missed_commitments=[
            MissedCommitment(
                original_task="Write the deployment runbook",
                original_owner="Bob",
                original_deadline="2026-05-14",
                committed_in_meeting="Week 1 Standup",
                committed_on_date="2026-05-12",
                meetings_elapsed=1,
                severity="critical",
            )
        ],
        commitment_completion_rate=0.0,
        highest_risk_owner="Bob",
        summary="1 missed commitment from Week 1 Standup — deployment runbook not delivered by deadline.",
    )

    with patch("agent.commitment_tracker.anthropic.Anthropic", return_value=_mock_tracker_response(expected)):
        from agent.commitment_tracker import track_commitments
        result = track_commitments(sessions)

    assert len(result.missed_commitments) == 1
    assert result.missed_commitments[0].original_owner == "Bob"
    assert result.missed_commitments[0].severity == "critical"


def test_resolved_commitment_not_flagged():
    sessions = [
        _make_session("Week 1", "2026-05-12", action_items=[
            ActionItem(task="Update the API docs", owner="Alice", deadline="2026-05-14", priority="medium"),
        ]),
        _make_session("Week 2", "2026-05-19", decisions=["API docs updated and published"]),
    ]

    expected = CommitmentTrackerResult(
        missed_commitments=[],
        commitment_completion_rate=1.0,
        highest_risk_owner=None,
        summary="All commitments from Week 1 were addressed in subsequent meetings.",
    )

    with patch("agent.commitment_tracker.anthropic.Anthropic", return_value=_mock_tracker_response(expected)):
        from agent.commitment_tracker import track_commitments
        result = track_commitments(sessions)

    assert len(result.missed_commitments) == 0
    assert result.commitment_completion_rate == 1.0


def test_completion_rate_calculated():
    sessions = [
        _make_session("W1", "2026-05-12", action_items=[
            ActionItem(task="Task A", owner="Alice", deadline="2026-05-14", priority="high"),
            ActionItem(task="Task B", owner="Bob", deadline="2026-05-14", priority="high"),
        ]),
        _make_session("W2", "2026-05-19"),
    ]

    expected = CommitmentTrackerResult(
        missed_commitments=[
            MissedCommitment(
                original_task="Task A", original_owner="Alice", original_deadline="2026-05-14",
                committed_in_meeting="W1", committed_on_date="2026-05-12",
                meetings_elapsed=1, severity="moderate",
            )
        ],
        commitment_completion_rate=0.5,
        highest_risk_owner="Alice",
        summary="1 of 2 commitments completed.",
    )

    with patch("agent.commitment_tracker.anthropic.Anthropic", return_value=_mock_tracker_response(expected)):
        from agent.commitment_tracker import track_commitments
        result = track_commitments(sessions)

    assert result.commitment_completion_rate == 0.5


def test_highest_risk_owner_identified():
    sessions = [
        _make_session("W1", "2026-05-12", action_items=[
            ActionItem(task="Task 1", owner="Bob", deadline="2026-05-14", priority="high"),
            ActionItem(task="Task 2", owner="Bob", deadline="2026-05-14", priority="high"),
            ActionItem(task="Task 3", owner="Alice", deadline="2026-05-14", priority="medium"),
        ]),
        _make_session("W2", "2026-05-19"),
    ]

    expected = CommitmentTrackerResult(
        missed_commitments=[
            MissedCommitment(original_task="Task 1", original_owner="Bob", original_deadline="2026-05-14",
                committed_in_meeting="W1", committed_on_date="2026-05-12", meetings_elapsed=1, severity="critical"),
            MissedCommitment(original_task="Task 2", original_owner="Bob", original_deadline="2026-05-14",
                committed_in_meeting="W1", committed_on_date="2026-05-12", meetings_elapsed=1, severity="critical"),
        ],
        commitment_completion_rate=0.33,
        highest_risk_owner="Bob",
        summary="Bob has 2 missed commitments — highest risk owner this week.",
    )

    with patch("agent.commitment_tracker.anthropic.Anthropic", return_value=_mock_tracker_response(expected)):
        from agent.commitment_tracker import track_commitments
        result = track_commitments(sessions)

    assert result.highest_risk_owner == "Bob"


def test_single_session_returns_early():
    from agent.commitment_tracker import track_commitments
    sessions = [_make_session("Only meeting", "2026-05-19")]
    result = track_commitments(sessions)
    assert result.commitment_completion_rate == 1.0
    assert len(result.missed_commitments) == 0
