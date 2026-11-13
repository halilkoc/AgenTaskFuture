"""Dosya/kanıt indirme (ADR 0016). Sahip kontrollü; imzalı bağlantı yok, içerik bu uçtan akıtılır."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Header, HTTPException, Path, Request, Response

from agentask.domain.artifacts import ARTIFACT_ID_PATTERN
from agentask.presentation.dependencies import ContainerDep, PrincipalDep

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.post("/uploads", status_code=201)
async def upload(
    request: Request,
    p: PrincipalDep,
    c: ContainerDep,
    content_type: Annotated[str, Header()],
    x_file_name: Annotated[str, Header(min_length=1, max_length=400)],
) -> dict[str, object]:
    """İşlemde kullanılacak dosya. Gövde ham içeriktir; sınır okunurken uygulanır, ad yalnız üstveridir."""
    limit = c.settings.artifact_max_bytes
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise HTTPException(status_code=413, detail="Dosya izin verilen boyutu aşıyor.")
    ref = await c.artifacts.store_upload(p.user_id, content_type, bytes(data), unquote(x_file_name))
    return {"artifact_id": ref.artifact_id, "size_bytes": ref.size_bytes, "content_type": ref.content_type}


@router.get("/{artifact_id}")
async def download(
    artifact_id: Annotated[str, Path(pattern=ARTIFACT_ID_PATTERN)], p: PrincipalDep, c: ContainerDep
) -> Response:
    ref, data = await c.artifacts.fetch(p.user_id, artifact_id)
    return Response(
        content=data,
        media_type=ref.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ref.artifact_id}"',
            "Cache-Control": "no-store",
        },
    )
