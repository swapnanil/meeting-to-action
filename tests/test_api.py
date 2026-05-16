import io
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent.models import MeetingOutput
from api import app

client = TestClient(app)

VALID_OUTPUT = {
    "meeting_title": "Client Strategy Meeting",
    "date": "2026-05-15",
    "participants": ["Swapnanil Saha", "Marcus Webb", "Diane Torres", "James Okonkwo"],
    "decisions": [
        "Phase one pivots to meeting summarisation using Teams data",
        "Budget for phase one remains at $120K",
    ],
    "action_items": [
        {
            "task": "Send updated proposal with revised scope and timeline",
            "owner": "Swapnanil Saha",
            "deadline": "End of next week",
            "priority": "high",
        },
        {
            "task": "Provide API specification and required OAuth scopes",
            "owner": "Swapnanil Saha",
            "deadline": "Friday",
            "priority": "high",
        },
        {
            "task": "Provision Teams integration after receiving API spec",
            "owner": "James Okonkwo",
            "deadline": "One week after spec received",
            "priority": "medium",
        },
    ],
    "open_questions": [
        "Will the Teams data usage require additional legal sign-off beyond existing O365 DPA?"
    ],
    "risk_flags": [
        {
            "description": "Data access permissions for document store blocked by GDPR / DPA review — 4 to 6 weeks minimum delay. Phase two cannot start until resolved.",
            "severity": "critical",
        }
    ],
    "follow_up_email": (
        "Team,\n\nThank you for a productive session today. Here is a summary of decisions and next steps.\n\n"
        "Decisions:\n- Phase one pivots to meeting summarisation on Teams data\n"
        "- Phase one budget confirmed at $120K\n\n"
        "Action items:\n- Swapnanil: Updated scope proposal by end of next week\n"
        "- Swapnanil: API spec to James by Friday\n"
        "- James: Integration provisioning within one week of spec receipt\n"
        "- Diane: Legal call re phase two DPA, week of the 25th\n\n"
        "Best regards,\nSwapnanil Saha"
    ),
    "summary": (
        "The pilot scope was pivoted to meeting summarisation on Teams data due to a GDPR blocker "
        "on the original document classification use case. Budget stays at $120K for phase one, "
        "with document classification deferred to phase two pending DPA resolution."
    ),
}

SAMPLE_TRANSCRIPT = (
    "Marcus: We have exec buy-in and a $120K budget for the AI pilot but need measurable ROI by Q3.\n"
    "Diane: We have a data access blocker — legal hasn't signed the DPA for the document store yet, "
    "4-6 weeks minimum.\n"
    "Swapnanil: That's a significant blocker. We could pivot phase one to meeting summarisation using "
    "Teams data instead.\n"
    "Marcus: Let's do that. Teams data is already compliant. James, is that feasible?\n"
    "James: Yes, we have the Teams API integration ready to go.\n"
    "Marcus: Decision made — phase one is meeting summarisation on Teams, budget stays at $120K.\n"
    "Swapnanil: I'll send the API spec to James by Friday and an updated proposal by end of next week.\n"
    "James: I'll provision the integration within a week of receiving your spec. I'll send the tenant "
    "ID today.\n"
    "Marcus: Diane, please set up a legal call about the document DPA for the week of the 25th.\n"
    "Diane: Will do."
)


class TestHealthEndpoint:
    def test_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_returns_model_name(self):
        response = client.get("/health")
        assert "model" in response.json()
        assert response.json()["model"] == os.environ.get("MODEL", "claude-sonnet-4-6")


class TestExtractEndpoint:
    def test_happy_path(self):
        with patch("api.extract_meeting_output", return_value=MeetingOutput(**VALID_OUTPUT)):
            response = client.post("/extract", json={"transcript": SAMPLE_TRANSCRIPT})

        assert response.status_code == 200
        data = response.json()
        assert data["meeting_title"] == "Client Strategy Meeting"
        assert len(data["action_items"]) == 3
        assert len(data["risk_flags"]) == 1

    def test_empty_transcript_returns_422(self):
        with patch("api.extract_meeting_output", side_effect=ValueError("Transcript is too short")):
            response = client.post("/extract", json={"transcript": ""})
        assert response.status_code == 422

    def test_short_transcript_returns_422(self):
        with patch("api.extract_meeting_output", side_effect=ValueError("Transcript is too short")):
            response = client.post("/extract", json={"transcript": "Too short"})
        assert response.status_code == 422
        assert "too short" in response.json()["detail"].lower()

    def test_missing_api_key_returns_500(self):
        with patch(
            "api.extract_meeting_output",
            side_effect=EnvironmentError("ANTHROPIC_API_KEY is not set"),
        ):
            response = client.post("/extract", json={"transcript": SAMPLE_TRANSCRIPT})
        assert response.status_code == 500
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]

    def test_invalid_transcript_field_type(self):
        response = client.post("/extract", json={"transcript": 12345})
        assert response.status_code == 422

    def test_missing_transcript_field(self):
        response = client.post("/extract", json={})
        assert response.status_code == 422

    def test_response_schema_complete(self):
        with patch("api.extract_meeting_output", return_value=MeetingOutput(**VALID_OUTPUT)):
            response = client.post("/extract", json={"transcript": SAMPLE_TRANSCRIPT})
        data = response.json()
        required_keys = {
            "meeting_title", "date", "participants", "decisions",
            "action_items", "open_questions", "risk_flags",
            "follow_up_email", "summary",
        }
        assert required_keys.issubset(data.keys())


class TestExtractFileEndpoint:
    def test_happy_path_with_file(self):
        with patch("api.extract_meeting_output", return_value=MeetingOutput(**VALID_OUTPUT)):
            response = client.post(
                "/extract/file",
                files={"file": ("transcript.txt", io.BytesIO(SAMPLE_TRANSCRIPT.encode()), "text/plain")},
            )
        assert response.status_code == 200
        assert response.json()["meeting_title"] == "Client Strategy Meeting"

    def test_empty_file_returns_422(self):
        with patch("api.extract_meeting_output", side_effect=ValueError("Transcript is too short")):
            response = client.post(
                "/extract/file",
                files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
            )
        assert response.status_code == 422

    def test_non_utf8_file_returns_422(self):
        response = client.post(
            "/extract/file",
            files={"file": ("bad.txt", io.BytesIO(b"\xff\xfe garbage"), "text/plain")},
        )
        assert response.status_code == 422

    def test_missing_file_returns_422(self):
        response = client.post("/extract/file")
        assert response.status_code == 422
