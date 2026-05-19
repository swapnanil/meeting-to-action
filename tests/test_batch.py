from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.models import ActionItem, MeetingOutput, RiskFlag


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def _make_output(title: str = "Test", owner: str = "Alice") -> MeetingOutput:
    return MeetingOutput(
        meeting_title=title,
        date="2026-05-19",
        participants=["Alice", "Bob"],
        meeting_type="standup",
        meeting_type_confidence=0.9,
        decisions=["Ship by Friday"],
        action_items=[ActionItem(task=f"Fix the issue in {title}", owner=owner, deadline="Friday", priority="high")],
        open_questions=[],
        risk_flags=[RiskFlag(description="Deployment blocker", severity="moderate")],
        formatted_follow_up="Team standup summary.",
        summary="Quick standup — action items assigned.",
    )


def _mock_client(output: MeetingOutput):
    mock = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=output.model_dump_json())]
    mock.messages.create.return_value = msg
    return mock


def test_batch_processes_all_files():
    outputs = [_make_output(f"Meeting {i}") for i in range(3)]
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        msg = MagicMock()
        msg.content = [MagicMock(text=outputs[call_count % len(outputs)].model_dump_json())]
        call_count += 1
        return msg

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect

    transcripts = [
        {"filename": f"meeting_{i}.txt", "text": "Alice: Let's get this shipped by Friday — it's the top priority. Bob: Understood, I'll have it done by Thursday EOD."}
        for i in range(3)
    ]

    with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
        from agent.batch import process_batch
        result = process_batch(transcripts, generate_digest=False)

    assert result.total_files == 3
    assert result.succeeded == 3
    assert result.failed == 0


def test_batch_reports_failures_without_stopping():
    good_output = _make_output("Good Meeting")
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Simulated API failure")
        msg = MagicMock()
        msg.content = [MagicMock(text=good_output.model_dump_json())]
        return msg

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect

    transcripts = [
        {"filename": f"t{i}.txt", "text": "Alice: Let's get this shipped by Friday — it's the top priority. Bob: Understood, I'll have it done by Thursday EOD."}
        for i in range(3)
    ]

    with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
        from agent.batch import process_batch
        result = process_batch(transcripts)

    assert result.total_files == 3
    assert result.failed >= 1
    assert result.succeeded >= 1


def test_batch_generates_digest_when_flag_set():
    output = _make_output()
    mock_client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=output.model_dump_json())]
    mock_client.messages.create.return_value = msg

    transcripts = [
        {"filename": f"t{i}.txt", "text": "Alice: Let's ship this by Friday. Bob: I'll handle it."}
        for i in range(2)
    ]

    with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
        with patch("agent.digest._generate_digest_email", return_value="Weekly digest email content."):
            from agent.batch import process_batch
            result = process_batch(transcripts, generate_digest=True)

    assert result.digest is not None
    assert result.digest.total_meetings == 2


def test_batch_writes_output_files():
    output = _make_output()
    mock_client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=output.model_dump_json())]
    mock_client.messages.create.return_value = msg

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "src"
        src.mkdir()
        out = Path(tmpdir) / "out"
        (src / "meeting.txt").write_text("Alice: We need to ship the new dashboard by Friday — it's blocking the client demo. Bob: Understood, I'll prioritize it and have it ready by Thursday EOD.", encoding="utf-8")

        with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
            from agent.batch import process_directory
            result = process_directory(src)

        assert result.total_files == 1
        assert result.succeeded == 1
