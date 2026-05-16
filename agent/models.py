from typing import Literal
from pydantic import BaseModel


class ActionItem(BaseModel):
    task: str
    owner: str | None
    deadline: str | None
    priority: Literal["high", "medium", "low"]


class RiskFlag(BaseModel):
    description: str
    severity: Literal["critical", "moderate", "low"]


class MeetingOutput(BaseModel):
    meeting_title: str | None
    date: str | None
    participants: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    open_questions: list[str]
    risk_flags: list[RiskFlag]
    follow_up_email: str
    summary: str
