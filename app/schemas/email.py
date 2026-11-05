from datetime import datetime
from pydantic import BaseModel, Field


class Email(BaseModel):
    id: str
    provider_message_id: str
    thread_id: str | None = None
    sender: str = Field(min_length=1, max_length=320)
    receiver: str = Field(min_length=1, max_length=320)
    subject: str
    body: str
    is_read: bool = False
    received_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
