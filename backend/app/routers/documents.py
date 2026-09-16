from fastapi import APIRouter

router = APIRouter(tags=["documents"])

# Endpoints:
#   POST   /documents
#   GET    /documents
#   GET    /documents/:id
#   PATCH  /documents/:id
#   DELETE /documents/:id
#   POST   /documents/:id/versions
#   GET    /documents/:id/versions
#   GET    /documents/:id/versions/:vid
# Not yet implemented.
