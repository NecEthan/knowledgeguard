from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.base import AuditEvent, User
from app.schemas.audit import AuditEventResponse

router = APIRouter(tags=["audit"])


@router.get("", response_model=list[AuditEventResponse])
async def list_audit_events(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEventResponse]:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await db.execute(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)
    )
    events = result.scalars().all()
    return [AuditEventResponse.model_validate(e) for e in events]
