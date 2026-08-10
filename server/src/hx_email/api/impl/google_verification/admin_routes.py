"""Admin routes for managing the Google site-verification file."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, Query, status

from hx_email.api.dependencies import require_admin
from hx_email.config import Settings
from hx_email.server.google_verification import (
    delete_verification_file,
    list_verification_files,
    save_verification_file,
)


def register_google_verification_routes(router: APIRouter, settings: Settings) -> None:
    """Admin endpoints under /api/v1 for managing the uploaded file."""

    @router.get("/admin/google-verification")
    def get_google_verification_files(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        return {
            "files": [
                {"filename": name, "url": f"/{name}"} for name in list_verification_files(settings)
            ]
        }

    @router.post("/admin/google-verification", status_code=status.HTTP_201_CREATED)
    def upload_google_verification_file(
        filename: Annotated[str, Query(...)],
        content: Annotated[bytes, Body(media_type="text/html")],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        require_admin(settings, authorization)
        try:
            save_verification_file(settings, filename, content)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return {"filename": filename, "url": f"/{filename}"}

    @router.delete(
        "/admin/google-verification/{filename}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_google_verification_file(
        filename: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        require_admin(settings, authorization)
        if not delete_verification_file(settings, filename):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="验证文件不存在",
            )
