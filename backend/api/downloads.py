from urllib.parse import quote

from fastapi.responses import Response


def download_response(content: bytes, filename: str, media_type: str) -> Response:
    """Ficheiro em memória (lido do storage local ou S3) com o mesmo Content-Disposition do FileResponse:
    nomes com acentos vão em filename*=utf-8''…"""
    quoted = quote(filename)
    if quoted != filename:
        disposition = f"attachment; filename*=utf-8''{quoted}"
    else:
        disposition = f'attachment; filename="{filename}"'
    return Response(content, media_type=media_type, headers={"Content-Disposition": disposition})
