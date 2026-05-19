#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

from agent.extractor import extract_meeting_output
from agent.models import MeetingOutput

app = typer.Typer(
    name="meeting-to-action",
    help="Meeting-to-Action v2 — by Swapnanil Saha",
    no_args_is_help=True,
)
console = Console()


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
    lines.append(f"**Meeting type:** {output.meeting_type} (confidence: {output.meeting_type_confidence:.0%})")
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
    lines.append("## Follow-up")
    lines.append("---")
    lines.append(output.formatted_follow_up)
    lines.append("---")
    return "\n".join(lines)


def _format_output(output: MeetingOutput, fmt: str) -> str:
    if fmt == "json":
        return output.model_dump_json(indent=2)
    if fmt == "email-only":
        return output.formatted_follow_up
    return _format_as_markdown(output)


@app.command()
def run(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Path to transcript file."),
    stdin: bool = typer.Option(False, "--stdin", help="Read transcript from stdin."),
    format: str = typer.Option("markdown", "--format", help="Output format: json | markdown | email-only"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save output to this file path."),
    raw: bool = typer.Option(False, "--raw", help="Skip transcript normalization (Zoom/Teams cleanup)."),
    push_notion: bool = typer.Option(False, "--push-notion", help="Push action items to Notion after extraction."),
) -> None:
    """Extract decisions, action items, and follow-up from a meeting transcript."""
    _setup_logging()

    if file:
        if not file.exists():
            typer.echo(f"Error: File not found: {file}", err=True)
            raise typer.Exit(1)
        transcript = file.read_text(encoding="utf-8")
    elif stdin:
        transcript = sys.stdin.read()
    else:
        typer.echo("Error: Provide a transcript via --file <path> or --stdin (pipe).", err=True)
        raise typer.Exit(1)

    if format not in ("json", "markdown", "email-only"):
        typer.echo("Error: --format must be one of: json, markdown, email-only", err=True)
        raise typer.Exit(1)

    try:
        result = extract_meeting_output(transcript, skip_normalize=raw)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except EnvironmentError as e:
        typer.echo(f"Configuration error:\n{e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)

    if push_notion:
        from agent.notion import push_to_notion
        try:
            notion_result = push_to_notion(result)
            console.print(f"[green]Pushed {notion_result['notion_pages_created']} action items to Notion.[/green]")
        except Exception as e:
            console.print(f"[red]Notion push failed: {e}[/red]")

    formatted = _format_output(result, format)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(formatted, encoding="utf-8")
        typer.echo(f"Output saved to {output}")
    else:
        typer.echo(formatted)


@app.command()
def batch(
    dir: Path = typer.Option(..., "--dir", "-d", help="Directory containing transcript files."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Directory to write output files."),
    format: str = typer.Option("json", "--format", help="Output format: json | markdown"),
    generate_digest: bool = typer.Option(False, "--generate-digest", help="Generate a weekly digest from all meetings."),
    raw: bool = typer.Option(False, "--raw", help="Skip transcript normalization."),
) -> None:
    """Process a directory of transcript files."""
    _setup_logging()
    from agent.batch import process_directory

    if not dir.is_dir():
        typer.echo(f"Error: {dir} is not a directory.", err=True)
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Processing transcripts in {dir}...[/bold cyan]\n")

    try:
        result = process_directory(dir, generate_digest=generate_digest, skip_normalize=raw)
    except Exception as e:
        typer.echo(f"Batch processing failed: {e}", err=True)
        raise typer.Exit(1)

    table = Table(title=f"Batch Results — {result.succeeded}/{result.total_files} succeeded")
    table.add_column("File")
    table.add_column("Status")
    table.add_column("Meeting Type")
    table.add_column("Action Items", justify="right")
    table.add_column("Duration (s)", justify="right")

    for r in result.results:
        status_color = "green" if r.status == "success" else "red"
        meeting_type = r.output.meeting_type if r.output else "—"
        item_count = str(len(r.output.action_items)) if r.output else "—"
        table.add_row(
            r.filename,
            f"[{status_color}]{r.status}[/{status_color}]",
            meeting_type,
            item_count,
            str(r.duration_seconds),
        )

    console.print(table)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        for r in result.results:
            if r.output:
                out_path = output_dir / f"{Path(r.filename).stem}.json"
                out_path.write_text(r.output.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"\n[green]Outputs written to {output_dir}[/green]")

    if result.digest and output_dir:
        digest_path = output_dir / "digest.json"
        digest_path.write_text(result.digest.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Digest written to {digest_path}[/green]")
    elif result.digest:
        console.print(Panel(result.digest.digest_email, title="Weekly Digest", border_style="cyan"))


@app.command()
def digest(
    dir: Path = typer.Option(..., "--dir", "-d", help="Directory containing JSON meeting output files."),
    week: str = typer.Option("", "--week", help="Week label e.g. 'Week of 2026-05-19'"),
    format: str = typer.Option("markdown", "--format", help="Output format: json | markdown"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save digest to file."),
) -> None:
    """Generate a weekly digest from a directory of meeting JSON outputs."""
    _setup_logging()
    from agent.digest import build_digest

    json_files = sorted(dir.glob("*.json"))
    if not json_files:
        typer.echo(f"No JSON files found in {dir}.", err=True)
        raise typer.Exit(1)

    sessions: list[MeetingOutput] = []
    for f in json_files:
        try:
            sessions.append(MeetingOutput(**json.loads(f.read_text())))
        except Exception as e:
            console.print(f"[yellow]Skipping {f.name}: {e}[/yellow]")

    if not sessions:
        typer.echo("No valid meeting outputs found.", err=True)
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Generating digest from {len(sessions)} meetings...[/bold cyan]\n")

    try:
        result = build_digest(sessions, week_label=week)
    except Exception as e:
        typer.echo(f"Digest failed: {e}", err=True)
        raise typer.Exit(1)

    if format == "json":
        content = result.model_dump_json(indent=2)
    else:
        lines = [
            f"# Weekly Digest — {result.week_label}",
            "",
            f"**Meetings:** {result.total_meetings}  |  **Action items:** {result.total_action_items}  |  **Decisions:** {result.total_decisions}",
            "",
            "## Key Decisions",
            *[f"- {d}" for d in result.top_decisions],
            "",
            "## Open Items by Owner",
        ]
        for owner, items in result.open_items_by_owner.items():
            lines.append(f"**{owner}:**")
            lines.extend(f"  - {i}" for i in items)
        if result.escalated_risks:
            lines += ["", "## Escalated Risks", *[f"- ⚠ {r}" for r in result.escalated_risks]]
        lines += ["", "## Digest Email", "---", result.digest_email, "---"]
        content = "\n".join(lines)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Digest saved to {output}[/green]")
    else:
        typer.echo(content)


@app.command("track-commitments")
def track_commitments_cmd(
    dir: Path = typer.Option(..., "--dir", "-d", help="Directory containing JSON meeting output files (chronological)."),
    format: str = typer.Option("markdown", "--format", help="Output format: json | markdown"),
) -> None:
    """Detect commitments from past meetings that weren't followed up on."""
    _setup_logging()
    from agent.commitment_tracker import track_commitments

    json_files = sorted(dir.glob("*.json"))
    sessions: list[MeetingOutput] = []
    for f in json_files:
        try:
            sessions.append(MeetingOutput(**json.loads(f.read_text())))
        except Exception as e:
            console.print(f"[yellow]Skipping {f.name}: {e}[/yellow]")

    if len(sessions) < 2:
        typer.echo("Need at least 2 meeting JSON outputs to track commitments.", err=True)
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Tracking commitments across {len(sessions)} meetings...[/bold cyan]\n")

    try:
        result = track_commitments(sessions)
    except Exception as e:
        typer.echo(f"Tracking failed: {e}", err=True)
        raise typer.Exit(1)

    if format == "json":
        typer.echo(result.model_dump_json(indent=2))
        return

    console.print(Panel(
        f"[bold]Completion rate:[/bold] {result.commitment_completion_rate:.0%}\n"
        f"[bold]Highest risk owner:[/bold] {result.highest_risk_owner or 'N/A'}\n"
        f"[bold]Summary:[/bold] {result.summary}",
        title=f"Commitment Tracker — {len(result.missed_commitments)} missed",
        border_style="red" if result.missed_commitments else "green",
    ))

    if result.missed_commitments:
        table = Table(title="Missed Commitments", border_style="red")
        table.add_column("Task", max_width=50)
        table.add_column("Owner")
        table.add_column("Deadline")
        table.add_column("Meetings elapsed", justify="right")
        table.add_column("Severity")

        for mc in result.missed_commitments:
            sev_color = {"critical": "bold red", "moderate": "yellow", "low": "dim"}.get(mc.severity, "white")
            table.add_row(
                mc.original_task[:50],
                mc.original_owner or "—",
                mc.original_deadline or "—",
                str(mc.meetings_elapsed),
                f"[{sev_color}]{mc.severity}[/{sev_color}]",
            )
        console.print(table)


if __name__ == "__main__":
    app()
