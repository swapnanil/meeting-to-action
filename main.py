import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

from agent.extractor import extract_meeting_output
from agent.models import MeetingOutput

app = typer.Typer(
    name="meeting-to-action",
    help="Transform raw meeting transcripts into structured, actionable output.",
    no_args_is_help=True,
)


def _setup_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _format_as_markdown(output: MeetingOutput) -> str:
    lines: list[str] = []

    title = output.meeting_title or "Meeting Analysis"
    lines.append(f"# {title}")
    if output.date:
        lines.append(f"**Date:** {output.date}")
    if output.participants:
        lines.append(f"**Participants:** {', '.join(output.participants)}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append(output.summary)
    lines.append("")

    lines.append("## Decisions")
    if output.decisions:
        for d in output.decisions:
            lines.append(f"- {d}")
    else:
        lines.append("_No decisions recorded._")
    lines.append("")

    lines.append("## Action Items")
    if output.action_items:
        lines.append("| Task | Owner | Deadline | Priority |")
        lines.append("|------|-------|----------|----------|")
        for item in output.action_items:
            owner = item.owner or "—"
            deadline = item.deadline or "—"
            lines.append(f"| {item.task} | {owner} | {deadline} | {item.priority.capitalize()} |")
    else:
        lines.append("_No action items recorded._")
    lines.append("")

    lines.append("## Open Questions")
    if output.open_questions:
        for q in output.open_questions:
            lines.append(f"- {q}")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append("## Risk Flags")
    if output.risk_flags:
        for flag in output.risk_flags:
            lines.append(f"**[{flag.severity.upper()}]** {flag.description}")
    else:
        lines.append("_No risks identified._")
    lines.append("")

    lines.append("## Follow-up Email")
    lines.append("---")
    lines.append(output.follow_up_email)
    lines.append("---")

    return "\n".join(lines)


def _format_output(output: MeetingOutput, fmt: str) -> str:
    if fmt == "json":
        return output.model_dump_json(indent=2)
    if fmt == "email-only":
        return output.follow_up_email
    return _format_as_markdown(output)


@app.command()
def run(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Path to transcript file."),
    stdin: bool = typer.Option(False, "--stdin", help="Read transcript from stdin."),
    format: str = typer.Option(
        "markdown", "--format", help="Output format: json | markdown | email-only"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Save output to this file path."
    ),
) -> None:
    """Extract decisions, action items, and follow-up email from a meeting transcript."""
    _setup_logging()

    if file:
        if not file.exists():
            typer.echo(f"Error: File not found: {file}", err=True)
            raise typer.Exit(1)
        transcript = file.read_text(encoding="utf-8")
    elif stdin:
        transcript = sys.stdin.read()
    else:
        typer.echo(
            "Error: Provide a transcript via --file <path> or --stdin (pipe).", err=True
        )
        raise typer.Exit(1)

    if format not in ("json", "markdown", "email-only"):
        typer.echo(
            "Error: --format must be one of: json, markdown, email-only", err=True
        )
        raise typer.Exit(1)

    try:
        result = extract_meeting_output(transcript)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except EnvironmentError as e:
        typer.echo(f"Configuration error:\n{e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)

    formatted = _format_output(result, format)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(formatted, encoding="utf-8")
        typer.echo(f"Output saved to {output}")
    else:
        typer.echo(formatted)


if __name__ == "__main__":
    app()
