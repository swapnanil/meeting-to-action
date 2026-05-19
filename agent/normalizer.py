from __future__ import annotations

import re

from agent.models import NormalizedTranscript

_ZOOM_TIMESTAMP = re.compile(r"\[\d{2}:\d{2}:\d{2}\]\s*")
_TEAMS_TIMESTAMP = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\s*")
_MEET_TIMESTAMP = re.compile(r"\(\d{2}:\d{2}\)\s*")
_PLAIN_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s*[-–]\s*", re.MULTILINE)
_FILLER_LINES = re.compile(
    r"^\s*(\[Transcription by .*?\]|<<<.*?>>>|--- (End|Start) of .*?---)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_SPEAKER_EMAIL = re.compile(r"\b([a-z]+)\.([a-z]+)@[^\s:]+:\s*", re.IGNORECASE)
_SPEAKER_ALLCAPS = re.compile(r"\b([A-Z][A-Z_]+(?:_EXT|_INT)?)\s*:\s*")
_BLANK_RUNS = re.compile(r"\n{3,}")
_FIRST_TIMESTAMP = re.compile(r"\[?(\d{2}:\d{2}:\d{2})\]?")
_LAST_TIMESTAMP = re.compile(r"\[?(\d{2}:\d{2}:\d{2})\]?")


def _to_title(name: str) -> str:
    return " ".join(word.capitalize() for word in name.replace("_", " ").split())


def _detect_format(text: str) -> str:
    if re.search(r"\[\d{2}:\d{2}:\d{2}\]", text):
        return "zoom"
    if re.search(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", text):
        return "teams"
    if re.search(r"\(\d{2}:\d{2}\)", text):
        return "meet"
    return "unknown"


def _estimate_duration(text: str) -> float | None:
    timestamps = _FIRST_TIMESTAMP.findall(text)
    if len(timestamps) < 2:
        return None
    def _to_seconds(ts: str) -> int:
        parts = ts.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    try:
        return (_to_seconds(timestamps[-1]) - _to_seconds(timestamps[0])) / 60
    except (ValueError, IndexError):
        return None


def _count_speakers(text: str) -> int:
    speakers: set[str] = set()
    for m in re.finditer(r"^([A-Za-z][A-Za-z .'-]+):\s", text, re.MULTILINE):
        speakers.add(m.group(1).strip())
    return max(len(speakers), 1)


def normalize(transcript: str, skip: bool = False) -> NormalizedTranscript:
    if skip:
        return NormalizedTranscript(
            text=transcript,
            source_format="unknown",
            speaker_count=_count_speakers(transcript),
            estimated_duration_minutes=None,
            was_normalized=False,
        )

    source_format = _detect_format(transcript)
    estimated_duration = _estimate_duration(transcript)
    original = transcript

    text = _ZOOM_TIMESTAMP.sub("", transcript)
    text = _TEAMS_TIMESTAMP.sub("", text)
    text = _MEET_TIMESTAMP.sub("", text)
    text = _PLAIN_TIMESTAMP.sub("", text)
    text = _FILLER_LINES.sub("", text)

    def _fix_email_speaker(m: re.Match) -> str:
        first = _to_title(m.group(1))
        last = _to_title(m.group(2))
        return f"{first} {last}: "

    text = _SPEAKER_EMAIL.sub(_fix_email_speaker, text)

    def _fix_allcaps_speaker(m: re.Match) -> str:
        raw = m.group(1).rstrip("_EXT").rstrip("_INT")
        return _to_title(raw) + ": "

    text = _SPEAKER_ALLCAPS.sub(_fix_allcaps_speaker, text)
    text = _BLANK_RUNS.sub("\n\n", text)
    text = text.strip()

    return NormalizedTranscript(
        text=text,
        source_format=source_format,
        speaker_count=_count_speakers(text),
        estimated_duration_minutes=estimated_duration,
        was_normalized=(text != original),
    )
