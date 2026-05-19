from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.models import ActionItem, MeetingOutput, RiskFlag


def _make_output(**kwargs) -> MeetingOutput:
    defaults = dict(
        meeting_title="Test Meeting",
        date="2026-05-19",
        participants=["Alice", "Bob"],
        meeting_type="unknown",
        meeting_type_confidence=0.0,
        decisions=[],
        action_items=[],
        open_questions=[],
        risk_flags=[],
        formatted_follow_up="Test follow-up",
        summary="Test summary.",
    )
    defaults.update(kwargs)
    return MeetingOutput(**defaults)


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def _mock_client(output: MeetingOutput):
    mock = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=output.model_dump_json())]
    mock.messages.create.return_value = msg
    return mock


def test_standup_type_field_valid():
    output = _make_output(meeting_type="standup", meeting_type_confidence=0.92)
    assert output.meeting_type == "standup"
    assert output.meeting_type_confidence == 0.92


def test_retrospective_type_field_valid():
    output = _make_output(meeting_type="retrospective", meeting_type_confidence=0.85)
    assert output.meeting_type == "retrospective"


def test_exec_review_type_field_valid():
    output = _make_output(meeting_type="exec_review", meeting_type_confidence=0.78)
    assert output.meeting_type == "exec_review"


def test_incident_review_type_field_valid():
    output = _make_output(meeting_type="incident_review", meeting_type_confidence=0.90)
    assert output.meeting_type == "incident_review"


def test_unknown_type_is_default():
    output = _make_output()
    assert output.meeting_type == "unknown"
    assert output.meeting_type_confidence == 0.0


def test_standup_detected_from_blockers_language():
    standup_output = _make_output(
        meeting_type="standup",
        meeting_type_confidence=0.95,
        risk_flags=[RiskFlag(description="Redis latency blocking auth service", severity="critical")],
        formatted_follow_up="🔴 Blockers\n- Redis latency spike\n🔄 In Progress\n- Auth service fix\n✅ Done\n- Deploy pipeline",
    )
    with patch("agent.extractor.anthropic.Anthropic", return_value=_mock_client(standup_output)):
        from agent.extractor import extract_meeting_output
        result = extract_meeting_output(
            "Bob: Morning everyone. Still blocked on Redis — 450ms latency spike in auth.\n"
            "Alice: Got it. Bob owns the fix by Wednesday. Charlie you good?\n"
            "Charlie: All clear, shipping the infra changes this afternoon.",
            skip_normalize=True,
        )
    assert result.meeting_type == "standup"
    assert result.meeting_type_confidence > 0.5


def test_retrospective_detected_from_keep_stop_start():
    retro_output = _make_output(
        meeting_type="retrospective",
        meeting_type_confidence=0.88,
        formatted_follow_up="Keep\n- Daily standups\nStop\n- Skipping retros\nStart\n- Code review checklist",
    )
    with patch("agent.extractor.anthropic.Anthropic", return_value=_mock_client(retro_output)):
        from agent.extractor import extract_meeting_output
        result = extract_meeting_output(
            "Alice: Let's run our retro. What should we keep doing?\n"
            "Bob: Keep the daily standups — they're working.\n"
            "Alice: What should we stop?\n"
            "Charlie: Stop skipping retrospectives when we're busy.\n"
            "Alice: And start?\n"
            "Bob: Start using a code review checklist.",
            skip_normalize=True,
        )
    assert result.meeting_type == "retrospective"


def test_exec_review_detected_from_board_language():
    exec_output = _make_output(
        meeting_type="exec_review",
        meeting_type_confidence=0.91,
        formatted_follow_up="Subject: Executive Review Summary — Q2 Board Update\n\nDecisions Taken:\n- Approved Q2 budget increase\n\nRisks Requiring Executive Attention:\n- Pipeline delay may impact Q2 targets",
    )
    with patch("agent.extractor.anthropic.Anthropic", return_value=_mock_client(exec_output)):
        from agent.extractor import extract_meeting_output
        result = extract_meeting_output(
            "CEO: Welcome to the Q2 board review. Let's cover the key decisions from last quarter and risks going into Q3.\n"
            "CFO: The budget has been approved by the board. We're increasing the engineering headcount by 20%.\n"
            "CTO: The main risk is pipeline delay — we may miss Q2 targets by two weeks.",
            skip_normalize=True,
        )
    assert result.meeting_type == "exec_review"


def test_follow_up_format_differs_by_type():
    standup_output = _make_output(
        meeting_type="standup",
        formatted_follow_up="🔴 Blockers\n- Redis\n🔄 In Progress\n- Fix\n✅ Done\n- Deploy",
    )
    exec_output = _make_output(
        meeting_type="exec_review",
        formatted_follow_up="Subject: Board Review Summary\n\nDecisions Taken:\n- Budget approved.\n\nRisks Requiring Executive Attention:\n- Q2 pipeline delay.",
    )
    assert "🔴" in standup_output.formatted_follow_up
    assert "Subject:" in exec_output.formatted_follow_up
    assert standup_output.formatted_follow_up != exec_output.formatted_follow_up


def test_meeting_output_follow_up_email_property():
    output = _make_output(formatted_follow_up="This is the follow-up content.")
    assert output.follow_up_email == "This is the follow-up content."
