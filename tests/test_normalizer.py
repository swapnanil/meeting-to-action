from __future__ import annotations

import pytest
from agent.normalizer import normalize


def test_strips_zoom_timestamps():
    text = "[00:02:14] Alice: We need to fix this.\n[00:03:01] Bob: Agreed."
    result = normalize(text)
    assert "[00:" not in result.text
    assert "Alice: We need to fix this." in result.text
    assert "Bob: Agreed." in result.text
    assert result.was_normalized is True


def test_strips_teams_format():
    text = "00:02:14.000 --> 00:02:18.000\nAlice: The deployment failed.\n00:02:20.000 --> 00:02:25.000\nBob: I'll investigate."
    result = normalize(text)
    assert "-->" not in result.text
    assert "Alice:" in result.text
    assert result.was_normalized is True


def test_strips_meet_format():
    text = "(00:02) Alice: Ready for the review?\n(00:05) Bob: Yes, let's go."
    result = normalize(text)
    assert "(00:" not in result.text
    assert "Alice:" in result.text
    assert result.was_normalized is True


def test_normalizes_speaker_email_to_name():
    text = "bob.patel@company.com: We need to ship this by Friday.\nalice.chen@acme.io: Agreed."
    result = normalize(text)
    assert "Bob Patel:" in result.text
    assert "Alice Chen:" in result.text
    assert "@company.com" not in result.text


def test_normalizes_allcaps_speaker():
    text = "BOB_PATEL_EXT: The Redis latency is spiking.\nALICE_CHEN: That needs to be fixed by Wednesday."
    result = normalize(text)
    assert "BOB_PATEL_EXT:" not in result.text
    assert "ALICE_CHEN:" not in result.text
    assert result.was_normalized is True


def test_detects_zoom_format():
    text = "[00:01:00] Alice: Hello.\n[00:01:05] Bob: Hi."
    result = normalize(text)
    assert result.source_format == "zoom"


def test_detects_teams_format():
    text = "00:01:00.000 --> 00:01:05.000\nAlice: Hello."
    result = normalize(text)
    assert result.source_format == "teams"


def test_detects_unknown_format_for_clean_text():
    text = "Alice: Hello everyone.\nBob: Good morning.\nAlice: Let's get started."
    result = normalize(text)
    assert result.source_format == "unknown"
    assert result.was_normalized is False


def test_speaker_count_detected():
    text = "Alice: Point one.\nBob: Point two.\nCharlie: Point three.\nAlice: Agreed."
    result = normalize(text)
    assert result.speaker_count >= 3


def test_raw_flag_skips_normalization():
    text = "[00:01:00] BOB_EXT: This should not be cleaned."
    result = normalize(text, skip=True)
    assert "[00:01:00]" in result.text
    assert result.was_normalized is False


def test_cleans_filler_lines():
    text = "[Transcription by Zoom]\nAlice: Let's start.\n\n\n\nBob: Ready."
    result = normalize(text)
    assert "[Transcription by Zoom]" not in result.text
    assert "\n\n\n" not in result.text


def test_preserves_clean_transcript_content():
    text = "Alice: The Redis issue is resolved. Bob, can you update the runbook by Thursday?\nBob: Yes, I'll have it done."
    result = normalize(text)
    assert "Redis issue is resolved" in result.text
    assert "update the runbook by Thursday" in result.text
