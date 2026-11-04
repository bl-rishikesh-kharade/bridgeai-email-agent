from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class Email(BaseModel):
    id: str
    provider_message_id: str
    thread_id: str | None = None
    sender: EmailStr
    receiver: EmailStr
    subject: str
    body: str
    is_read: bool = False
    received_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
