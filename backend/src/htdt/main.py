from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__


class HealthResponse(BaseModel):
    status: str
    version: str
    platform_target: str
    rew_required: bool
    measurement_hardware_required: bool


def create_app() -> FastAPI:
    app = FastAPI(
        title="Home Theater Digital Twin",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=__version__,
            platform_target="Windows 11 x64",
            rew_required=False,
            measurement_hardware_required=False,
        )

    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if frontend_dist.is_dir():
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            candidate = frontend_dist / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            return {
                "name": "Home Theater Digital Twin",
                "status": "backend-ready",
                "ui": "frontend/dist has not been built yet",
            }

    return app


app = create_app()
