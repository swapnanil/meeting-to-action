from __future__ import annotations

import json
import logging
import os

import anthropic
from pydantic import ValidationError

from agent.models import CommitmentTrackerResult, MeetingOutput
from agent.prompts import COMMITMENT_SYSTEM_PROMPT, get_commitment_prompt

logger = logging.getLogger(__name__)


def track_commitments(sessions: list[MeetingOutput]) -> CommitmentTrackerResult:
    if len(sessions) < 2:
        return CommitmentTrackerResult(
            missed_commitments=[],
            commitment_completion_rate=1.0,
            highest_risk_owner=None,
            summary="Need at least 2 meeting sessions to track commitments across time.",
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    model = os.environ.get("MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    # Collect all action items from all but the last meeting as "past commitments"
    past_items: list[dict] = []
    for session in sessions[:-1]:
        for item in session.action_items:
            past_items.append({
                "task": item.task,
                "owner": item.owner,
                "deadline": item.deadline,
                "priority": item.priority,
                "committed_in_meeting": session.meeting_title or "Unknown meeting",
                "committed_on_date": session.date,
            })

    if not past_items:
        return CommitmentTrackerResult(
            missed_commitments=[],
            commitment_completion_rate=1.0,
            highest_risk_owner=None,
            summary="No action items found in earlier sessions to track.",
        )

    # Subsequent transcripts — use summary + formatted_follow_up as a proxy for the transcript text
    subsequent_texts = [
        f"Meeting: {s.meeting_title or 'Unknown'}\nDate: {s.date or 'Unknown'}\n"
        f"Decisions: {', '.join(s.decisions)}\n"
        f"Action items: {', '.join(a.task for a in s.action_items)}\n"
        f"Summary: {s.summary}"
        for s in sessions[1:]
    ]

    prompt = get_commitment_prompt(past_items, subsequent_texts)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=COMMITMENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        data = json.loads(raw)
        return CommitmentTrackerResult(**data)
    except (json.JSONDecodeError, ValidationError, Exception) as e:
        logger.error("Commitment tracking failed: %s", e)
        raise ValueError(f"Commitment tracker returned invalid output: {e}") from e
