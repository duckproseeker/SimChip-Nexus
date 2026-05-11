from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.core.config import get_settings

router = APIRouter(tags=["控制台"])


def frontend_index_file() -> str:
    return str(get_settings().project_root / "frontend" / "dist" / "index.html")


def has_frontend_bundle() -> bool:
    return get_settings().project_root.joinpath("frontend", "dist", "index.html").exists()


def render_frontend_index() -> FileResponse:
    return FileResponse(frontend_index_file(), media_type="text/html")


@router.get("/", include_in_schema=False)
def landing_home() -> Response:
    if not has_frontend_bundle():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FRONTEND_BUNDLE_MISSING",
                "message": "frontend/dist 缺失，请先执行前端构建或远端 Git 同步部署。",
            },
        )
    return render_frontend_index()


@router.get("/ui", include_in_schema=False)
@router.get("/ui/{full_path:path}", include_in_schema=False)
def ui_home(full_path: str = "") -> Response:
    if not has_frontend_bundle():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "FRONTEND_BUNDLE_MISSING",
                "message": "frontend/dist 缺失，请先执行前端构建或远端 Git 同步部署。",
            },
        )
    return render_frontend_index()
