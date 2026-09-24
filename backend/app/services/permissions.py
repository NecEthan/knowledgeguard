from sqlalchemy import or_, select

from app.models.base import Document, DocumentPermission, User


def build_permitted_doc_ids(user: User):
    """Return a scalar subquery of document IDs the user can access."""
    return (
        select(Document.id)
        .where(
            or_(
                Document.owner_id == user.id,
                Document.id.in_(
                    select(DocumentPermission.document_id).where(
                        DocumentPermission.user_id == user.id
                    )
                ),
            )
        )
        .where(Document.deleted_at.is_(None))
        .scalar_subquery()
    )
