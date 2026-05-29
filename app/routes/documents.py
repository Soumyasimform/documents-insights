from fastapi import APIRouter

from app.models.document import DocumentCreateRequest, DocumentResponse
from app.services import document_service

router = APIRouter(tags=["documents"])


@router.post("/documents", status_code=201, response_model=DocumentResponse)
async def submit_document(body: DocumentCreateRequest) -> DocumentResponse:
    return await document_service.create_document(body)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str) -> DocumentResponse:
    return await document_service.get_document(document_id)
