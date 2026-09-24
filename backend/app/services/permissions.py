from sqlalchemy import select

from app.models.base import Document, User


def build_permitted_doc_ids(user: User):
    """Return a scalar subquery of document IDs the user can access."""
    query = select(Document.id)
    if user.role != "admin":
        query = query.where(Document.sensitivity == "STANDARD")
    return query.scalar_subquery()
