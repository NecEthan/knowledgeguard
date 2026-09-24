from fastapi import APIRouter

from .document import router as _document_router
from .documents import router as _documents_router
from .versions import router as _versions_router

router = APIRouter()
router.routes.extend(_documents_router.routes)
router.routes.extend(_document_router.routes)
router.routes.extend(_versions_router.routes)
