import json
import logging
import os
import time
from datetime import datetime, timezone

import anthropic
from pydantic import ValidationError

from .models import MeetingOutput
from .prompts import JSON_CORRECTION_PROMPT, SYSTEM_PROMPT, get_user_prompt

logger = logging.getLogger(__name__)


def _call_api(client: anthropic.Anthropic, model: str, max_tokens: int, messages: list) -> str:
    """Call the Anthropic API with exponential backoff on rate limit errors."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                logger.warning(
                    f"Rate limited by Anthropic API. Waiting {wait_time}s before retry "
                    f"(attempt {attempt + 1}/{max_retries})."
                )
                time.sleep(wait_time)
            else:
                logger.error("Rate limit exceeded after %d retries.", max_retries)
                raise


def extract_meeting_output(transcript: str) -> MeetingOutput:
    """Extract structured meeting intelligence from a raw transcript."""
    if not transcript or len(transcript.strip()) < 50:
        raise ValueError(
            f"Transcript is too short ({len(transcript.strip())} chars). "
            "Please provide at least 50 characters of meeting content."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "To fix this:\n"
            "  1. Copy .env.example to .env\n"
            "  2. Set ANTHROPIC_API_KEY=sk-ant-... in your .env file\n"
            "  3. Or export it in your shell: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    model = os.environ.get("MODEL", "claude-sonnet-4-6")
    max_tokens = int(os.environ.get("MAX_TOKENS", "2048"))
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Starting extraction | transcript_length=%d | model=%s | timestamp=%s",
        len(transcript),
        model,
        timestamp,
    )

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": get_user_prompt(transcript)}]

    raw = _call_api(client, model, max_tokens, messages)

    try:
        data = json.loads(raw)
        return MeetingOutput(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(
            "Invalid JSON on first attempt — retrying with correction prompt. "
            "error=%s | transcript_length=%d | model=%s | timestamp=%s",
            e,
            len(transcript),
            model,
            timestamp,
        )
        messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": JSON_CORRECTION_PROMPT},
        ]
        raw = _call_api(client, model, max_tokens, messages)
        try:
            data = json.loads(raw)
            return MeetingOutput(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Extraction failed after JSON correction retry. "
                "error=%s | transcript_length=%d | model=%s | timestamp=%s",
                e,
                len(transcript),
                model,
                timestamp,
            )
            raise ValueError(
                f"Claude returned invalid JSON even after correction retry: {e}"
            ) from e
