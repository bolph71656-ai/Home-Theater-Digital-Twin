from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import datetime
import os
from pathlib import Path
import tempfile

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .comparison import ComparisonError, compare_frequency_responses
from .database import Store
from .models import BackupRestoreRequest, ComparisonCreate, ContextCreate, ImportPreviewRequest, MeasurementImportRequest, ProjectCreate
from .rew_parser import RewParseError, parse_rew_frequency_response


class HealthResponse(BaseModel):
    status: str
    version: str
    platform_target: str
    rew_required: bool
    measurement_hardware_required: bool
    schema_version: int


def _default_data_dir() -> Path:
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        return Path(local_app_data) / 'HomeTheaterDigitalTwin'
    return Path.home() / '.home-theater-digital-twin'


def create_app(data_dir: Path | None = None) -> FastAPI:
    store = Store(data_dir or _default_data_dir())
    app = FastAPI(title='Home Theater Digital Twin', version=__version__, docs_url='/api/docs', redoc_url=None, openapi_url='/api/openapi.json')
    app.state.store = store

    @app.get('/api/health', response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status='ok', version=__version__, platform_target='Windows 11 x64', rew_required=False, measurement_hardware_required=False, schema_version=1)

    @app.get('/api/projects')
    def list_projects() -> list[dict]:
        return store.list_projects()

    @app.post('/api/projects', status_code=201)
    def create_project(request: ProjectCreate) -> dict:
        return store.create_project(request.name)

    @app.get('/api/projects/{project_id}')
    def get_project(project_id: str) -> dict:
        project = store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail='Project not found')
        return project

    @app.get('/api/projects/{project_id}/contexts')
    def list_contexts(project_id: str) -> list[dict]:
        return store.list_contexts(project_id)

    @app.post('/api/projects/{project_id}/contexts', status_code=201)
    def create_context(project_id: str, request: ContextCreate) -> dict:
        try:
            return store.create_context(project_id, request.model_dump(mode='json'), request.parent_context_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post('/api/import/preview')
    def preview_import(request: ImportPreviewRequest) -> dict:
        try:
            raw = store.decode_base64(request.raw_base64)
            parsed = parse_rew_frequency_response(raw)
        except (ValueError, RewParseError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {'filename': request.filename, 'sha256': parsed.source_sha256, 'parser_version': parsed.parser_version, 'points': len(parsed.frequency_hz), 'frequency_min_hz': parsed.frequency_hz[0], 'frequency_max_hz': parsed.frequency_hz[-1], 'phase_status': parsed.phase_status, 'level_reference': parsed.level_reference, 'warnings': list(parsed.warnings), 'header_lines': list(parsed.header_lines)}

    @app.get('/api/projects/{project_id}/measurements')
    def list_measurements(project_id: str) -> list[dict]:
        return store.list_measurements(project_id)

    @app.post('/api/projects/{project_id}/measurements', status_code=201)
    def import_measurement(project_id: str, request: MeasurementImportRequest) -> dict:
        try:
            raw = store.decode_base64(request.raw_base64)
            return store.import_measurement(project_id=project_id, context_id=request.context_id, filename=request.filename, raw=raw, channel_role=request.channel_role, evidence_type=request.evidence_type, source_speaker_ids=request.source_speaker_ids, radiation_scope=request.radiation_scope, captured_at=request.captured_at, notes=request.notes)
        except (ValueError, RewParseError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get('/api/projects/{project_id}/comparisons')
    def list_comparisons(project_id: str) -> list[dict]:
        return store.list_comparisons(project_id)

    @app.post('/api/projects/{project_id}/comparisons', status_code=201)
    def create_comparison(project_id: str, request: ComparisonCreate) -> dict:
        try:
            a = store.get_frequency_response(request.dataset_a_id)
            b = store.get_frequency_response(request.dataset_b_id)
            reference_band = None
            if request.reference_low_hz is not None and request.reference_high_hz is not None:
                reference_band = (request.reference_low_hz, request.reference_high_hz)
            excluded = tuple((band.low_hz, band.high_hz) for band in request.excluded_bands)
            result = compare_frequency_responses(a, b, request.low_hz, request.high_hz, reference_band_hz=reference_band, excluded_bands=excluded)
            result_payload = asdict(result)
            return store.save_comparison(project_id, request.dataset_a_id, request.dataset_b_id, request.model_dump(mode='json'), result_payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ComparisonError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get('/api/backup')
    def create_backup() -> FileResponse:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        archive = store.root / 'backups' / f'htdt-backup-{stamp}.zip'
        store.backup_to(archive)
        return FileResponse(archive, filename=archive.name, media_type='application/zip')

    @app.post('/api/restore')
    def restore_backup(request: BackupRestoreRequest) -> dict[str, str]:
        try:
            raw = base64.b64decode(request.archive_base64, validate=True)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail='Invalid base64 payload') from exc
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False, dir=store.root) as temp:
            temp.write(raw)
            archive = Path(temp.name)
        try:
            store.restore_from(archive)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            archive.unlink(missing_ok=True)
        return {'status': 'restored'}

    frontend_dist = Path(__file__).resolve().parents[3] / 'frontend' / 'dist'
    if frontend_dist.is_dir():
        assets_dir = frontend_dist / 'assets'
        if assets_dir.is_dir():
            app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')

        @app.get('/{path:path}', include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            candidate = frontend_dist / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / 'index.html')
    else:
        @app.get('/', include_in_schema=False)
        def root() -> dict[str, str]:
            return {'name': 'Home Theater Digital Twin', 'status': 'backend-ready', 'ui': 'frontend/dist has not been built yet'}

    return app


app = create_app()
