from __future__ import annotations

from array import array
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Iterator
from uuid import uuid4
import zipfile

from .comparison import FrequencyResponse
from .rew_parser import parse_rew_frequency_response


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pack(values: tuple[float, ...] | None) -> bytes | None:
    if values is None:
        return None
    payload = array('d', values)
    if payload.itemsize != 8:
        raise RuntimeError('Unexpected double size')
    if os.sys.byteorder != 'little':
        payload.byteswap()
    return payload.tobytes()


def _unpack(blob: bytes | None) -> tuple[float, ...] | None:
    if blob is None:
        return None
    payload = array('d')
    payload.frombytes(blob)
    if os.sys.byteorder != 'little':
        payload.byteswap()
    return tuple(payload)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_dir = self.root / 'assets'
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'htdt.sqlite3'
        self._initialise()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        try:
            yield connection
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self.connect() as db:
            db.executescript(
                '''
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contexts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    revision_number INTEGER NOT NULL,
                    parent_context_id TEXT REFERENCES contexts(id),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(project_id, revision_number)
                );
                CREATE TABLE IF NOT EXISTS assets (
                    sha256 TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS measurements (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    context_id TEXT NOT NULL REFERENCES contexts(id),
                    channel_role TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    source_speaker_ids_json TEXT NOT NULL,
                    radiation_scope TEXT NOT NULL,
                    captured_at TEXT,
                    imported_at TEXT NOT NULL,
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    measurement_id TEXT NOT NULL REFERENCES measurements(id),
                    asset_sha256 TEXT NOT NULL REFERENCES assets(sha256),
                    kind TEXT NOT NULL,
                    frequency_blob BLOB NOT NULL,
                    level_blob BLOB NOT NULL,
                    phase_blob BLOB,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS comparisons (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    dataset_a_id TEXT NOT NULL REFERENCES datasets(id),
                    dataset_b_id TEXT NOT NULL REFERENCES datasets(id),
                    spec_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                '''
            )
            db.execute('INSERT OR IGNORE INTO metadata(key, value) VALUES (?, ?)', ('schema_version', str(SCHEMA_VERSION)))
            db.commit()

    def create_project(self, name: str) -> dict[str, Any]:
        project = {'id': str(uuid4()), 'name': name.strip(), 'created_at': utc_now()}
        with self.connect() as db:
            db.execute('INSERT INTO projects(id, name, created_at) VALUES (?, ?, ?)', tuple(project.values()))
            db.commit()
        return project

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM projects ORDER BY created_at DESC')]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
            return dict(row) if row else None

    def create_context(self, project_id: str, payload: dict[str, Any], parent_context_id: str | None) -> dict[str, Any]:
        with self.connect() as db:
            project = db.execute('SELECT id FROM projects WHERE id = ?', (project_id,)).fetchone()
            if project is None:
                raise KeyError('project_not_found')
            if parent_context_id is not None:
                parent = db.execute('SELECT id FROM contexts WHERE id = ? AND project_id = ?', (parent_context_id, project_id)).fetchone()
                if parent is None:
                    raise KeyError('parent_context_not_found')
            revision = db.execute('SELECT COALESCE(MAX(revision_number), 0) + 1 FROM contexts WHERE project_id = ?', (project_id,)).fetchone()[0]
            context = {'id': str(uuid4()), 'project_id': project_id, 'revision_number': revision, 'parent_context_id': parent_context_id, 'created_at': utc_now(), 'payload': payload}
            db.execute(
                '''INSERT INTO contexts(id, project_id, revision_number, parent_context_id, created_at, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (context['id'], project_id, revision, parent_context_id, context['created_at'], json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )
            db.commit()
        return context

    def list_contexts(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM contexts WHERE project_id = ? ORDER BY revision_number DESC', (project_id,)).fetchall()
        return [{'id': row['id'], 'project_id': row['project_id'], 'revision_number': row['revision_number'], 'parent_context_id': row['parent_context_id'], 'created_at': row['created_at'], 'payload': json.loads(row['payload_json'])} for row in rows]

    def _store_asset(self, filename: str, raw: bytes) -> tuple[str, Path, bool]:
        digest = hashlib.sha256(raw).hexdigest()
        suffix = Path(filename).suffix.lower()
        safe_suffix = suffix if suffix and len(suffix) <= 12 else '.bin'
        target = self.assets_dir / f'{digest}{safe_suffix}'
        created = False
        if not target.exists():
            temp = target.with_suffix(target.suffix + '.tmp')
            temp.write_bytes(raw)
            os.replace(temp, target)
            created = True
        return digest, target, created

    def import_measurement(self, project_id: str, context_id: str, filename: str, raw: bytes, channel_role: str, evidence_type: str, source_speaker_ids: list[str], radiation_scope: str, captured_at: str | None, notes: str | None) -> dict[str, Any]:
        parsed = parse_rew_frequency_response(raw)
        asset_sha, asset_path, asset_created = self._store_asset(filename, raw)
        measurement_id = str(uuid4())
        dataset_id = str(uuid4())
        imported_at = utc_now()
        metadata = {'parser_version': parsed.parser_version, 'phase_status': parsed.phase_status, 'level_reference': parsed.level_reference, 'warnings': list(parsed.warnings), 'header_lines': list(parsed.header_lines), 'source_sha256': parsed.source_sha256}
        try:
            with self.connect() as db:
                context = db.execute('SELECT id FROM contexts WHERE id = ? AND project_id = ?', (context_id, project_id)).fetchone()
                if context is None:
                    raise KeyError('context_not_found')
                db.execute('''INSERT OR IGNORE INTO assets(sha256, relative_path, original_filename, size_bytes, created_at) VALUES (?, ?, ?, ?, ?)''', (asset_sha, str(asset_path.relative_to(self.root)), filename, len(raw), imported_at))
                db.execute('''INSERT INTO measurements(id, project_id, context_id, channel_role, evidence_type, source_speaker_ids_json, radiation_scope, captured_at, imported_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (measurement_id, project_id, context_id, channel_role, evidence_type, json.dumps(source_speaker_ids), radiation_scope, captured_at, imported_at, notes))
                db.execute('''INSERT INTO datasets(id, measurement_id, asset_sha256, kind, frequency_blob, level_blob, phase_blob, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (dataset_id, measurement_id, asset_sha, 'frequency_response', _pack(parsed.frequency_hz), _pack(parsed.level_db), _pack(parsed.phase_deg), json.dumps(metadata, ensure_ascii=False, sort_keys=True), imported_at))
                db.commit()
        except Exception:
            if asset_created:
                asset_path.unlink(missing_ok=True)
            raise
        return {'measurement_id': measurement_id, 'dataset_id': dataset_id, 'asset_sha256': asset_sha, 'points': len(parsed.frequency_hz), 'frequency_min_hz': parsed.frequency_hz[0], 'frequency_max_hz': parsed.frequency_hz[-1], 'phase_status': parsed.phase_status, 'warnings': list(parsed.warnings)}

    def list_measurements(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute('''SELECT m.*, d.id AS dataset_id, d.frequency_blob, d.metadata_json, d.asset_sha256 FROM measurements m JOIN datasets d ON d.measurement_id = m.id WHERE m.project_id = ? ORDER BY m.imported_at DESC''', (project_id,)).fetchall()
        result = []
        for row in rows:
            frequency = _unpack(row['frequency_blob']) or ()
            result.append({'id': row['id'], 'dataset_id': row['dataset_id'], 'context_id': row['context_id'], 'channel_role': row['channel_role'], 'evidence_type': row['evidence_type'], 'source_speaker_ids': json.loads(row['source_speaker_ids_json']), 'radiation_scope': row['radiation_scope'], 'captured_at': row['captured_at'], 'imported_at': row['imported_at'], 'notes': row['notes'], 'asset_sha256': row['asset_sha256'], 'frequency_min_hz': frequency[0] if frequency else None, 'frequency_max_hz': frequency[-1] if frequency else None, 'points': len(frequency), 'metadata': json.loads(row['metadata_json'])})
        return result

    def get_frequency_response(self, dataset_id: str) -> FrequencyResponse:
        with self.connect() as db:
            row = db.execute('SELECT frequency_blob, level_blob FROM datasets WHERE id = ? AND kind = ?', (dataset_id, 'frequency_response')).fetchone()
            if row is None:
                raise KeyError('dataset_not_found')
        return FrequencyResponse(frequency_hz=_unpack(row['frequency_blob']) or (), level_db=_unpack(row['level_blob']) or ())

    def save_comparison(self, project_id: str, dataset_a_id: str, dataset_b_id: str, spec: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        comparison = {'id': str(uuid4()), 'created_at': utc_now()}
        with self.connect() as db:
            for dataset_id in (dataset_a_id, dataset_b_id):
                row = db.execute('''SELECT m.project_id FROM datasets d JOIN measurements m ON m.id = d.measurement_id WHERE d.id = ?''', (dataset_id,)).fetchone()
                if row is None or row['project_id'] != project_id:
                    raise KeyError('dataset_not_found')
            db.execute('''INSERT INTO comparisons(id, project_id, dataset_a_id, dataset_b_id, spec_json, result_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)''', (comparison['id'], project_id, dataset_a_id, dataset_b_id, json.dumps(spec, ensure_ascii=False, sort_keys=True), json.dumps(result, ensure_ascii=False, sort_keys=True), comparison['created_at']))
            db.commit()
        return {**comparison, 'project_id': project_id, 'dataset_a_id': dataset_a_id, 'dataset_b_id': dataset_b_id, 'spec': spec, 'result': result}

    def list_comparisons(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM comparisons WHERE project_id = ? ORDER BY created_at DESC', (project_id,)).fetchall()
        return [{'id': row['id'], 'project_id': row['project_id'], 'dataset_a_id': row['dataset_a_id'], 'dataset_b_id': row['dataset_b_id'], 'spec': json.loads(row['spec_json']), 'result': json.loads(row['result_json']), 'created_at': row['created_at']} for row in rows]

    def backup_to(self, archive_path: Path) -> Path:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.root) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            snapshot_db = temp_dir / 'htdt.sqlite3'
            destination = sqlite3.connect(snapshot_db)
            try:
                with self.connect() as source:
                    source.backup(destination)
                destination.close()
            finally:
                destination.close()
            manifest = {'schema_version': SCHEMA_VERSION, 'created_at': utc_now()}
            with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot_db, 'htdt.sqlite3')
                archive.writestr('manifest.json', json.dumps(manifest, sort_keys=True))
                for asset in self.assets_dir.iterdir():
                    if asset.is_file():
                        archive.write(asset, f'assets/{asset.name}')
        return archive_path

    def restore_from(self, archive_path: Path) -> None:
        with tempfile.TemporaryDirectory(dir=self.root) as staging_name:
            staging = Path(staging_name)
            with zipfile.ZipFile(archive_path, 'r') as archive:
                names = set(archive.namelist())
                if 'manifest.json' not in names or 'htdt.sqlite3' not in names:
                    raise ValueError('Invalid HTDT backup')
                manifest = json.loads(archive.read('manifest.json'))
                if manifest.get('schema_version') != SCHEMA_VERSION:
                    raise ValueError('Unsupported backup schema version')
                for member in archive.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or '..' in member_path.parts:
                        raise ValueError('Unsafe backup path')
                archive.extractall(staging)
            restored_db = staging / 'htdt.sqlite3'
            validation_db = sqlite3.connect(restored_db)
            try:
                version = validation_db.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
                if version is None or int(version[0]) != SCHEMA_VERSION:
                    raise ValueError('Backup database schema mismatch')
            finally:
                validation_db.close()
            replacement_assets = staging / 'assets'
            old_assets = self.root / 'assets.old'
            if old_assets.exists():
                shutil.rmtree(old_assets)
            if self.assets_dir.exists():
                os.replace(self.assets_dir, old_assets)
            try:
                if replacement_assets.exists():
                    shutil.copytree(replacement_assets, self.assets_dir)
                else:
                    self.assets_dir.mkdir()
                os.replace(restored_db, self.db_path)
                shutil.rmtree(old_assets, ignore_errors=True)
            except Exception:
                shutil.rmtree(self.assets_dir, ignore_errors=True)
                if old_assets.exists():
                    os.replace(old_assets, self.assets_dir)
                raise

    @staticmethod
    def decode_base64(raw_base64: str) -> bytes:
        try:
            return base64.b64decode(raw_base64, validate=True)
        except ValueError as exc:
            raise ValueError('Invalid base64 payload') from exc
