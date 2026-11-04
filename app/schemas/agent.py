from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field


ChatFilterId = Literal[
    "important_unread",
]


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    filter_id: ChatFilterId | None = None
    selected_email_id: str | None = Field(default=None, max_length=256)


class ChatEmailOption(BaseModel):
    id: str = Field(max_length=256)
    gmail_url: str | None = None
    subject: str = Field(max_length=1000)
    sender: str = Field(max_length=320)
    received_at: datetime | None = None
    summary: str | None = Field(default=None, max_length=600)
    priority: Literal["Critical", "High", "Medium", "Low"] | None = None
    requires_action: bool | None = None
    requires_attention: bool | None = None
    action_items: list[str] = Field(default_factory=list, max_length=10)


class AgentChatResponse(BaseModel):
    response: str
    current_email_id: str | None = None
    email_options: list[ChatEmailOption] = Field(default_factory=list)
    used_recent_window: bool = False
