from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import datetime
import os
from pathlib import Path
import tempfile

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .acoustics import analyze_rectangular_context
from .comparison import ComparisonError, compare_frequency_responses
from .conditions import classify_differences, context_differences
from .database import SCHEMA_VERSION, Store
from .models import AttachmentCreate, BackupRestoreRequest, ComparisonCreate, ContextCreate, ImportPreviewRequest, MeasurementImportRequest, ProjectCreate
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


def _comparison_warnings(a: dict, b: dict, confounder_count: int) -> list[str]:
    warnings: list[str] = []
    for label, item in (('A', a), ('B', b)):
        status = item['quality_status']
        if status == 'invalid':
            warnings.append(f'{label} is marked invalid; keep only as reference, not evidence of improvement')
        elif status == 'warning':
            warnings.append(f'{label} has measurement quality warnings')
        elif status == 'unknown':
            warnings.append(f'{label} measurement quality is unknown')
        if item['evidence_type'] != 'measured':
            warnings.append(f'{label} evidence_type is {item["evidence_type"]}, not measured')
    if confounder_count:
        warnings.append(f'{confounder_count} unclassified context difference(s) may confound the A/B comparison')
    return warnings


def create_app(data_dir: Path | None = None) -> FastAPI:
    store = Store(data_dir or _default_data_dir())
    app = FastAPI(title='Home Theater Digital Twin', version=__version__, docs_url='/api/docs', redoc_url=None, openapi_url='/api/openapi.json')
    app.state.store = store

    @app.get('/api/health', response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status='ok', version=__version__, platform_target='Windows 11 x64', rew_required=False,
                              measurement_hardware_required=False, schema_version=SCHEMA_VERSION)

    @app.get('/api/integrity')
    def integrity() -> dict:
        problems = store.integrity_problems()
        return {'status': 'ok' if not problems else 'error', 'problems': problems}

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

    @app.get('/api/projects/{project_id}/contexts/{context_id}/acoustics')
    def context_acoustics(project_id: str, context_id: str, max_hz: float = Query(default=300.0, gt=0, le=2000),
                          sound_speed_m_s: float = Query(default=343.0, gt=250, lt=400)) -> dict:
        context = store.get_context(project_id, context_id)
        if context is None:
            raise HTTPException(status_code=404, detail='Context not found')
        try:
            return analyze_rectangular_context(context['payload'], max_hz=max_hz, sound_speed_m_s=sound_speed_m_s)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post('/api/import/preview')
    def preview_import(request: ImportPreviewRequest) -> dict:
        try:
            raw = store.decode_base64(request.raw_base64)
            parsed = parse_rew_frequency_response(raw)
        except (ValueError, RewParseError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {'filename': request.filename, 'sha256': parsed.source_sha256, 'parser_version': parsed.parser_version,
                'points': len(parsed.frequency_hz), 'frequency_min_hz': parsed.frequency_hz[0], 'frequency_max_hz': parsed.frequency_hz[-1],
                'phase_status': parsed.phase_status, 'level_reference': parsed.level_reference, 'warnings': list(parsed.warnings),
                'header_lines': list(parsed.header_lines)}

    @app.get('/api/projects/{project_id}/measurements')
    def list_measurements(project_id: str) -> list[dict]:
        return store.list_measurements(project_id)

    @app.post('/api/projects/{project_id}/measurements', status_code=201)
    def import_measurement(project_id: str, request: MeasurementImportRequest) -> dict:
        try:
            raw = store.decode_base64(request.raw_base64)
            return store.import_measurement(project_id=project_id, context_id=request.context_id, filename=request.filename, raw=raw,
                                            channel_role=request.channel_role, evidence_type=request.evidence_type,
                                            source_speaker_ids=request.source_speaker_ids, radiation_scope=request.radiation_scope,
                                            captured_at=request.captured_at, notes=request.notes, routing_evidence=request.routing_evidence,
                                            quality_status=request.quality_status, quality_reasons=request.quality_reasons,
                                            quality_source=request.quality_source, repeat_group=request.repeat_group)
        except (ValueError, RewParseError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get('/api/projects/{project_id}/attachments')
    def list_attachments(project_id: str) -> list[dict]:
        return store.list_attachments(project_id)

    @app.post('/api/projects/{project_id}/attachments', status_code=201)
    def create_attachment(project_id: str, request: AttachmentCreate) -> dict:
        try:
            raw = store.decode_base64(request.raw_base64)
            return store.attach_asset(project_id, request.filename, raw, request.kind, request.label, request.measurement_id, request.context_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get('/api/projects/{project_id}/comparisons')
    def list_comparisons(project_id: str) -> list[dict]:
        return store.list_comparisons(project_id)

    @app.post('/api/projects/{project_id}/comparisons', status_code=201)
    def create_comparison(project_id: str, request: ComparisonCreate) -> dict:
        try:
            descriptor_a = store.get_dataset_descriptor(request.dataset_a_id)
            descriptor_b = store.get_dataset_descriptor(request.dataset_b_id)
            if descriptor_a['project_id'] != project_id or descriptor_b['project_id'] != project_id:
                raise KeyError('dataset_not_found')
            a = store.get_frequency_response(request.dataset_a_id)
            b = store.get_frequency_response(request.dataset_b_id)
            reference_band = None
            if request.reference_low_hz is not None and request.reference_high_hz is not None:
                reference_band = (request.reference_low_hz, request.reference_high_hz)
            excluded = tuple((band.low_hz, band.high_hz) for band in request.excluded_bands)
            result = compare_frequency_responses(a, b, request.low_hz, request.high_hz,
                                                 reference_band_hz=reference_band, excluded_bands=excluded)
            differences = context_differences(descriptor_a['context_payload'], descriptor_b['context_payload'])
            classified = classify_differences(differences, request.expected_change_paths)
            same_repeat_group = bool(descriptor_a['repeat_group'] and descriptor_a['repeat_group'] == descriptor_b['repeat_group'])
            keys = ('measurement_id', 'context_id', 'channel_role', 'evidence_type', 'quality_status', 'quality_reasons', 'quality_source', 'repeat_group')
            result_payload = {**asdict(result), 'measurement_a': {key: descriptor_a[key] for key in keys},
                              'measurement_b': {key: descriptor_b[key] for key in keys},
                              'comparison_role': 'repeatability' if same_repeat_group else 'configuration_ab',
                              'context_differences': differences, 'intended_changes': classified['intended'],
                              'confounders': classified['confounders'],
                              'interpretation_warnings': _comparison_warnings(descriptor_a, descriptor_b, len(classified['confounders']))}
            return store.save_comparison(project_id, request.dataset_a_id, request.dataset_b_id, request.model_dump(mode='json'), result_payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ComparisonError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get('/api/backup')
    def create_backup() -> FileResponse:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        archive = store.root / 'backups' / f'htdt-backup-{stamp}.zip'
        try:
            store.backup_to(archive)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
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
