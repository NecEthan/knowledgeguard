import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    user_id: uuid.UUID | None
    document_id: uuid.UUID | None
    version_id: uuid.UUID | None
    metadata_: dict | None = Field(None, alias="metadata_")
    created_at: datetime
