from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.models import ActionItem, MeetingOutput, RiskFlag


def _make_output(title: str, owner: str = "Alice", risk_sev: str = "moderate") -> MeetingOutput:
    return MeetingOutput(
        meeting_title=title,
        date="2026-05-19",
        participants=["Alice", "Bob"],
        meeting_type="standup",
        meeting_type_confidence=0.9,
        decisions=[f"Decision from {title}"],
        action_items=[
            ActionItem(task=f"Task from {title}", owner=owner, deadline="Friday", priority="high"),
            ActionItem(task=f"Low priority task from {title}", owner="Bob", deadline=None, priority="low"),
        ],
        open_questions=[],
        risk_flags=[RiskFlag(description=f"Risk from {title}", severity=risk_sev)],
        formatted_follow_up="Follow-up content.",
        summary="Meeting summary.",
    )


def test_open_items_grouped_by_owner():
    sessions = [
        _make_output("Monday Standup", owner="Alice"),
        _make_output("Wednesday Sync", owner="Charlie"),
    ]
    with patch("agent.digest._generate_digest_email", return_value="Digest email."):
        from agent.digest import build_digest
        result = build_digest(sessions, week_label="Week of 2026-05-19")

    assert "Alice" in result.open_items_by_owner
    assert "Charlie" in result.open_items_by_owner
    assert any("Monday Standup" in task for task in result.open_items_by_owner["Alice"])


def test_escalated_risks_deduped():
    sessions = [
        _make_output("Meeting A", risk_sev="critical"),
        _make_output("Meeting B", risk_sev="moderate"),
        _make_output("Meeting C", risk_sev="low"),  # should not appear
    ]
    with patch("agent.digest._generate_digest_email", return_value="Digest email."):
        from agent.digest import build_digest
        result = build_digest(sessions)

    assert len(result.escalated_risks) == 2
    assert all("low" not in r.lower() for r in result.escalated_risks)


def test_escalated_risks_deduped_across_sessions():
    shared_risk = "Deployment pipeline blocked"
    session_a = MeetingOutput(
        meeting_title="A", date="2026-05-19", participants=["Alice"],
        meeting_type="standup", meeting_type_confidence=0.9, decisions=[],
        action_items=[], open_questions=[],
        risk_flags=[RiskFlag(description=shared_risk, severity="critical")],
        formatted_follow_up="", summary="",
    )
    session_b = MeetingOutput(
        meeting_title="B", date="2026-05-20", participants=["Alice"],
        meeting_type="standup", meeting_type_confidence=0.9, decisions=[],
        action_items=[], open_questions=[],
        risk_flags=[RiskFlag(description=shared_risk, severity="critical")],
        formatted_follow_up="", summary="",
    )
    with patch("agent.digest._generate_digest_email", return_value="Email."):
        from agent.digest import build_digest
        result = build_digest([session_a, session_b])

    assert result.escalated_risks.count(shared_risk) == 1


def test_digest_email_is_non_empty_string():
    sessions = [_make_output("Monday")]
    with patch("agent.digest._generate_digest_email", return_value="This is the weekly digest email."):
        from agent.digest import build_digest
        result = build_digest(sessions)

    assert isinstance(result.digest_email, str)
    assert len(result.digest_email.strip()) > 10


def test_week_label_preserved():
    sessions = [_make_output("Test")]
    with patch("agent.digest._generate_digest_email", return_value="Email."):
        from agent.digest import build_digest
        result = build_digest(sessions, week_label="Week of 2026-05-19")

    assert result.week_label == "Week of 2026-05-19"


def test_total_counts_correct():
    sessions = [_make_output("A"), _make_output("B")]
    with patch("agent.digest._generate_digest_email", return_value="Email."):
        from agent.digest import build_digest
        result = build_digest(sessions)

    assert result.total_meetings == 2
    assert result.total_action_items == 4  # 2 per session
    assert result.total_decisions >= 2
