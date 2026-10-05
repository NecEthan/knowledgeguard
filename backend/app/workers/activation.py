"""Re-export activation logic from the shared service layer."""

from app.services.activation import activate_version, DocumentDeletedError

__all__ = ["activate_version", "DocumentDeletedError"]
