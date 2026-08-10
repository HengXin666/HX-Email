"""Public route serving the Google site-verification file.

Google fetches ``/google<hash>.html`` without any credentials, so this route
lives outside /api/v1 and is reachable without auth.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse

from hx_email.config import Settings
from hx_email.server.google_verification import resolve_verification_file


def register_google_verification_serve_route(app: FastAPI, settings: Settings) -> None:
    """Serve the uploaded verification file at the site root."""

    @app.get("/{filename}", include_in_schema=False)
    def serve_google_verification_file(filename: str) -> FileResponse:
        file_path = resolve_verification_file(settings, filename)
        if file_path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return FileResponse(file_path, media_type="text/html")
