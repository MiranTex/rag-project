from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.api.downloads import download_response
from backend.api.security import require
from backend.auth.permissions import CHAT_USE, AuthenticatedUser
from backend.dependencies import get_export_store
from backend.models import ExportInfo

router = APIRouter(prefix="/exports", tags=["exports"])


# Cada utilizador só vê os seus ficheiros; o de outro utilizador responde 404, como se não existisse.
@router.get("", response_model=list[ExportInfo])
def list_exports(user: AuthenticatedUser = Depends(require(CHAT_USE))) -> list[ExportInfo]:
    return [ExportInfo(**vars(item)) for item in get_export_store().for_owner(user.user_id).list_files()]


@router.get("/{name}")
def download_export(name: str, user: AuthenticatedUser = Depends(require(CHAT_USE))) -> Response:
    store = get_export_store().for_owner(user.user_id)
    content = store.read(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado.")
    return download_response(content, name, store.media_type(name))
