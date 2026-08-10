from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.dependencies import verify_admin_session, verify_session
from app.models import Admin, Operator
from app.services.documentation import (
    create_document, delete_document, get_asset, list_documents, read_document,
    rename_document, save_document, save_image,
)


router = APIRouter()


class DocumentSave(BaseModel):
    content: str
    revision: str | None = None


class DocumentCreate(BaseModel):
    path: str = Field(min_length=1, max_length=240)


class DocumentRename(BaseModel):
    old_path: str = Field(min_length=1, max_length=240)
    new_path: str = Field(min_length=1, max_length=240)


@router.get("/admin/docs/{scope}", tags=["Documentation"])
def admin_document_list(scope: str, admin: Admin = Depends(verify_admin_session)):
    return {"documents": list_documents(scope)}


@router.get("/admin/docs/{scope}/content", tags=["Documentation"])
def admin_document_content(scope: str, path: str, admin: Admin = Depends(verify_admin_session)):
    return read_document(scope, path)


@router.put("/admin/docs/{scope}/content", tags=["Documentation"])
def admin_document_save(scope: str, path: str, data: DocumentSave, admin: Admin = Depends(verify_admin_session)):
    return save_document(scope, path, data.content, data.revision)


@router.post("/admin/docs/{scope}/content", tags=["Documentation"])
def admin_document_create(scope: str, data: DocumentCreate, admin: Admin = Depends(verify_admin_session)):
    return create_document(scope, data.path)


@router.patch("/admin/docs/{scope}/content", tags=["Documentation"])
def admin_document_rename(scope: str, data: DocumentRename, admin: Admin = Depends(verify_admin_session)):
    return rename_document(scope, data.old_path, data.new_path)


@router.delete("/admin/docs/{scope}/content", tags=["Documentation"])
def admin_document_delete(scope: str, path: str, admin: Admin = Depends(verify_admin_session)):
    delete_document(scope, path)
    return {"status": "deleted"}


@router.post("/admin/docs/{scope}/images", tags=["Documentation"])
async def admin_document_image(scope: str, file: UploadFile = File(...), admin: Admin = Depends(verify_admin_session)):
    return await save_image(scope, file)


@router.get("/admin/docs/{scope}/asset", tags=["Documentation"])
def admin_document_asset(scope: str, path: str, admin: Admin = Depends(verify_admin_session)):
    file_path, media_type = get_asset(scope, path)
    return FileResponse(file_path, media_type=media_type)


@router.get("/operator/docs", tags=["Documentation"])
def operator_document_list(operator: Operator = Depends(verify_session)):
    return {"documents": list_documents("operator")}


@router.get("/operator/docs/content", tags=["Documentation"])
def operator_document_content(path: str, operator: Operator = Depends(verify_session)):
    return read_document("operator", path)


@router.get("/operator/docs/asset", tags=["Documentation"])
def operator_document_asset(path: str, operator: Operator = Depends(verify_session)):
    file_path, media_type = get_asset("operator", path)
    return FileResponse(file_path, media_type=media_type)
