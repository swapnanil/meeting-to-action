from __future__ import annotations

import logging
import os

from agent.models import ActionItem, MeetingOutput

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {"high": "High", "medium": "Medium", "low": "Low"}


def _get_notion_client():
    try:
        from notion_client import Client
    except ImportError:
        raise ImportError(
            "notion-client is not installed. Run: pip install notion-client"
        )
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "NOTION_API_KEY is not set. Add it to your .env file."
        )
    return Client(auth=api_key)


def _get_database_id() -> str:
    db_id = os.environ.get("NOTION_DATABASE_ID")
    if not db_id:
        raise EnvironmentError(
            "NOTION_DATABASE_ID is not set. Add the target Notion database ID to your .env file."
        )
    return db_id


def push_to_notion(output: MeetingOutput) -> dict:
    notion = _get_notion_client()
    database_id = _get_database_id()

    created_ids: list[str] = []

    for item in output.action_items:
        page = _build_page(database_id, item, output)
        try:
            result = notion.pages.create(**page)
            created_ids.append(result["id"])
            logger.info("Created Notion page for action item: %s", item.task[:60])
        except Exception as e:
            logger.error("Failed to create Notion page for '%s': %s", item.task[:60], e)
            raise RuntimeError(f"Notion API error: {e}") from e

    return {
        "notion_pages_created": len(created_ids),
        "notion_page_ids": created_ids,
    }


def _build_page(database_id: str, item: ActionItem, output: MeetingOutput) -> dict:
    properties: dict = {
        "Name": {"title": [{"text": {"content": item.task}}]},
        "Priority": {"select": {"name": _PRIORITY_MAP.get(item.priority, "Medium")}},
        "Status": {"select": {"name": "Not started"}},
    }

    if item.owner:
        properties["Owner"] = {"rich_text": [{"text": {"content": item.owner}}]}

    if item.deadline:
        try:
            import re
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", item.deadline)
            if date_match:
                properties["Due Date"] = {"date": {"start": date_match.group()}}
            else:
                properties["Due Date Note"] = {
                    "rich_text": [{"text": {"content": item.deadline}}]
                }
        except Exception:
            pass

    if output.meeting_title:
        properties["Meeting"] = {
            "rich_text": [{"text": {"content": output.meeting_title}}]
        }

    return {"parent": {"database_id": database_id}, "properties": properties}
