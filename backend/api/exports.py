from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.dependencies import get_export_store
from backend.models import ExportInfo

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("", response_model=list[ExportInfo])
def list_exports() -> list[ExportInfo]:
    return [ExportInfo(**vars(item)) for item in get_export_store().list_files()]


@router.get("/{name}")
def download_export(name: str) -> FileResponse:
    path = get_export_store().resolve(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado.")
    return FileResponse(path, filename=path.name)
