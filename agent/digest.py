from __future__ import annotations

import collections
import logging
import os

import anthropic

from agent.models import MeetingOutput, WeeklyDigest
from agent.prompts import DIGEST_SYSTEM_PROMPT, get_digest_prompt

logger = logging.getLogger(__name__)


def build_digest(sessions: list[MeetingOutput], week_label: str = "") -> WeeklyDigest:
    if not week_label:
        dates = [s.date for s in sessions if s.date]
        week_label = f"Week of {min(dates)}" if dates else "this week"

    # Aggregate all decisions, deduplicate by text similarity (simple: unique strings)
    all_decisions: list[str] = []
    seen: set[str] = set()
    for s in sessions:
        for d in s.decisions:
            key = d.lower().strip()
            if key not in seen:
                seen.add(key)
                all_decisions.append(d)
    top_decisions = all_decisions[:5]

    # Group open action items by owner
    open_items_by_owner: dict[str, list[str]] = collections.defaultdict(list)
    carry_forward: list[str] = []
    total_action_items = 0
    for s in sessions:
        for item in s.action_items:
            total_action_items += 1
            owner = item.owner or "Unassigned"
            open_items_by_owner[owner].append(item.task)
            if item.priority == "high" and item.deadline:
                carry_forward.append(f"{item.task} (owner: {owner}, due: {item.deadline})")

    # Escalated risks — critical and moderate, deduplicated
    escalated: list[str] = []
    risk_seen: set[str] = set()
    for s in sessions:
        for flag in s.risk_flags:
            if flag.severity in ("critical", "moderate"):
                key = flag.description.lower().strip()
                if key not in risk_seen:
                    risk_seen.add(key)
                    escalated.append(flag.description)

    aggregated = {
        "week_label": week_label,
        "total_meetings": len(sessions),
        "total_action_items": total_action_items,
        "top_decisions": top_decisions,
        "open_items_by_owner": dict(open_items_by_owner),
        "escalated_risks": escalated,
        "carry_forward_items": carry_forward[:10],
    }

    digest_email = _generate_digest_email(aggregated)

    return WeeklyDigest(
        week_label=week_label,
        total_meetings=len(sessions),
        total_action_items=total_action_items,
        total_decisions=len(all_decisions),
        top_decisions=top_decisions,
        open_items_by_owner=dict(open_items_by_owner),
        escalated_risks=escalated,
        carry_forward_items=carry_forward[:10],
        digest_email=digest_email,
    )


def _generate_digest_email(aggregated: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_digest_email(aggregated)

    model = os.environ.get("MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=DIGEST_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": get_digest_prompt(aggregated)}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("Failed to generate digest email via LLM: %s. Using fallback.", e)
        return _fallback_digest_email(aggregated)


def _fallback_digest_email(aggregated: dict) -> str:
    lines = [
        f"Weekly Brief — {aggregated.get('week_label', 'this week')}",
        "",
        f"Meetings this week: {aggregated.get('total_meetings')}",
        f"Action items tracked: {aggregated.get('total_action_items')}",
        "",
        "Key decisions:",
    ]
    for d in aggregated.get("top_decisions", []):
        lines.append(f"  • {d}")
    if aggregated.get("escalated_risks"):
        lines.append("\nEscalated risks:")
        for r in aggregated["escalated_risks"]:
            lines.append(f"  ⚠ {r}")
    return "\n".join(lines)
