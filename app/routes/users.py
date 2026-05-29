from fastapi import APIRouter, Query

from app.models.document import DocumentListResponse, DocumentStatus
from app.services import document_service

router = APIRouter(tags=["users"])


@router.get("/users/{user_id}/documents", response_model=DocumentListResponse)
async def list_user_documents(
    user_id: str,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: DocumentStatus | None = Query(default=None, description="Filter by status"),
) -> DocumentListResponse:
    return await document_service.list_documents(user_id, page, page_size, status)
