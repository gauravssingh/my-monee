"""Backup, recovery, diagnostics, and portability API routes."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from expense_tracker.api.deps import db_session, settings_dep
from expense_tracker.config import Settings
from expense_tracker.services.backup import (
    _backups_dir,
    create_backup_snapshot,
    delete_backup,
    export_full_json_bundle,
    get_db_health,
    list_backups,
    restore_backup,
    vacuum_and_optimize,
)

router = APIRouter(prefix="/api/system", tags=["backup_and_storage"])


class CreateBackupBody(BaseModel):
    note: str | None = None


class RestoreBackupBody(BaseModel):
    filename: str


@router.get("/db-health")
def db_health_route(settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    return get_db_health(settings)


@router.post("/db-vacuum")
def db_vacuum_route(settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    return vacuum_and_optimize(settings)


@router.get("/backups")
def list_backups_route(settings: Settings = Depends(settings_dep)) -> list[dict[str, Any]]:
    return list_backups(settings)


@router.post("/backups/create")
def create_backup_route(
    body: CreateBackupBody,
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    return create_backup_snapshot(settings, note=body.note)


@router.post("/backups/restore")
def restore_backup_route(
    body: RestoreBackupBody,
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    try:
        return restore_backup(body.filename, settings)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/backups/{filename}")
def delete_backup_route(
    filename: str,
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    success = delete_backup(filename, settings)
    if not success:
        raise HTTPException(status_code=404, detail="Backup file not found.")
    return {"success": True, "deleted": filename}


@router.get("/backups/download/{filename}")
def download_backup_route(
    filename: str,
    settings: Settings = Depends(settings_dep),
) -> FileResponse:
    b_dir = _backups_dir(settings)
    target = b_dir / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Backup file not found.")
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=filename,
    )


@router.post("/backups/upload")
async def upload_backup_route(
    file: UploadFile = File(...),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be a .db file.")

    b_dir = _backups_dir(settings)
    dest_path = b_dir / file.filename
    content = await file.read()
    dest_path.write_bytes(content)

    return {
        "success": True,
        "filename": file.filename,
        "size_bytes": len(content),
    }


@router.get("/export-bundle")
def export_bundle_route(session: Session = Depends(db_session)) -> Response:
    bundle = export_full_json_bundle(session)
    json_bytes = json.dumps(bundle, indent=2).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="mymonee_ledger_export.json"'},
    )
