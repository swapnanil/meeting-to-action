import json
import os
from unittest.mock import MagicMock, patch

import pytest

from agent.extractor import extract_meeting_output
from agent.models import MeetingOutput

VALID_OUTPUT = {
    "meeting_title": "Engineering Standup",
    "date": "2026-05-17",
    "participants": ["Alice Chen", "Bob Patel", "Charlie Nwosu"],
    "decisions": ["Deploy to staging after approval"],
    "action_items": [
        {
            "task": "Fix Redis latency issue on auth service",
            "owner": "Bob Patel",
            "deadline": "Wednesday EOD",
            "priority": "high",
        }
    ],
    "open_questions": ["Who will sign off on the deployment?"],
    "risk_flags": [
        {
            "description": "Deployment blocked by missing infrastructure approval",
            "severity": "moderate",
        }
    ],
    "follow_up_email": (
        "Team,\n\nPlease see the action items from today's standup.\n\nBest regards,\nAlice"
    ),
    "summary": "The team aligned on Redis fix ownership and unblocking the deployment. Two risks flagged.",
}

SAMPLE_TRANSCRIPT = (
    "Alice: Good morning everyone. We have three things to cover — Redis, the deployment, "
    "and sprint planning.\n"
    "Bob: The Redis latency is at 450ms on auth. I think it's connection pool exhaustion.\n"
    "Alice: Bob, can you own this by Wednesday? And get the rollback doc to Charlie today?\n"
    "Bob: Sure, I'll make it my main focus.\n"
    "Charlie: I'll escalate the deployment approval to Priya this morning.\n"
    "Alice: Perfect. Sprint planning moves to Thursday 2:30 PM — I'm on leave from Friday.\n"
    "Bob: Thursday works.\nCharlie: Same."
)


def _make_mock_client(responses: list[str]) -> MagicMock:
    """Build a mock Anthropic client that returns responses in sequence."""
    mock_client = MagicMock()
    side_effects = []
    for text in responses:
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=text)]
        side_effects.append(mock_resp)
    mock_client.messages.create.side_effect = side_effects
    return mock_client


class TestHappyPath:
    def test_returns_meeting_output(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = _make_mock_client([json.dumps(VALID_OUTPUT)])
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                result = extract_meeting_output(SAMPLE_TRANSCRIPT)

        assert isinstance(result, MeetingOutput)
        assert result.meeting_title == "Engineering Standup"
        assert result.date == "2026-05-17"
        assert len(result.participants) == 3
        assert len(result.action_items) == 1
        assert result.action_items[0].owner == "Bob Patel"
        assert result.action_items[0].priority == "high"

    def test_api_called_once_on_valid_json(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = _make_mock_client([json.dumps(VALID_OUTPUT)])
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                extract_meeting_output(SAMPLE_TRANSCRIPT)

        mock_client.messages.create.assert_called_once()


class TestInputValidation:
    def test_empty_transcript_raises_value_error(self):
        with pytest.raises(ValueError, match="too short"):
            extract_meeting_output("")

    def test_whitespace_only_raises_value_error(self):
        with pytest.raises(ValueError, match="too short"):
            extract_meeting_output("   \n\t  ")

    def test_short_transcript_raises_value_error(self):
        with pytest.raises(ValueError, match="too short"):
            extract_meeting_output("This is short")

    def test_exactly_49_chars_raises(self):
        with pytest.raises(ValueError):
            extract_meeting_output("a" * 49)

    def test_exactly_50_chars_proceeds(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = _make_mock_client([json.dumps(VALID_OUTPUT)])
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                result = extract_meeting_output("a" * 50)
        assert isinstance(result, MeetingOutput)


class TestMissingApiKey:
    def test_raises_environment_error(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                extract_meeting_output(SAMPLE_TRANSCRIPT)

    def test_error_message_includes_setup_instructions(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(EnvironmentError) as exc_info:
                extract_meeting_output(SAMPLE_TRANSCRIPT)
        assert ".env" in str(exc_info.value)


class TestJsonRetry:
    def test_invalid_json_triggers_one_retry(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = _make_mock_client(["not valid json {{{{", json.dumps(VALID_OUTPUT)])
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                result = extract_meeting_output(SAMPLE_TRANSCRIPT)

        assert isinstance(result, MeetingOutput)
        assert mock_client.messages.create.call_count == 2

    def test_invalid_json_twice_raises_value_error(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = _make_mock_client(["not json", "still not json"])
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                with pytest.raises(ValueError, match="invalid JSON"):
                    extract_meeting_output(SAMPLE_TRANSCRIPT)

    def test_malformed_schema_triggers_retry(self):
        """Claude returns valid JSON but wrong schema → should retry."""
        bad_response = json.dumps({"wrong_key": "wrong_value"})
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = _make_mock_client([bad_response, json.dumps(VALID_OUTPUT)])
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                result = extract_meeting_output(SAMPLE_TRANSCRIPT)

        assert isinstance(result, MeetingOutput)
        assert mock_client.messages.create.call_count == 2


class TestRateLimitRetry:
    def test_rate_limit_retries_with_backoff(self):
        import anthropic as anthropic_module

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            mock_client = MagicMock()
            good_resp = MagicMock()
            good_resp.content = [MagicMock(text=json.dumps(VALID_OUTPUT))]
            mock_client.messages.create.side_effect = [
                anthropic_module.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429, headers={}),
                    body={},
                ),
                good_resp,
            ]
            with patch("agent.extractor.anthropic.Anthropic", return_value=mock_client):
                with patch("agent.extractor.time.sleep") as mock_sleep:
                    result = extract_meeting_output(SAMPLE_TRANSCRIPT)

        assert isinstance(result, MeetingOutput)
        mock_sleep.assert_called_once_with(1)
