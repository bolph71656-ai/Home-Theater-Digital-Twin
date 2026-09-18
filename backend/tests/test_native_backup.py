from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from htdt.cad_document import WorkingDocument
from htdt.cad_measurement_repository import CadMeasurementRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, make_f1_scene
from htdt.native_backup import create_backup, restore_backup, validate_backup


def _seed_data(data_dir: Path):
    repository = SceneRepository(data_dir / 'cad-scenes.sqlite3')
    first = repository.save(make_f1_scene(), parent_revision_id=None).revision
    measurements = CadMeasurementRepository(repository)

    raw = b'owned raw measurement fixture\n'
    digest = sha256(raw).hexdigest()
    relative_path = f'measurement-assets/{digest}'
    asset = data_dir / relative_path
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(raw)
    with sqlite3.connect(repository.path) as connection:
        connection.execute(
            '''INSERT INTO cad_measurement_assets(
                sha256, filename, relative_path, size_bytes
            ) VALUES (?, ?, ?, ?)''',
            (digest, 'fixture.txt', relative_path, len(raw)),
        )
    return repository, first, digest, raw


def _mutate_scene(repository: SceneRepository, source_revision_id: str):
    source = repository.get(source_revision_id)
    assert source is not None
    working = WorkingDocument(
        source.document,
        source_revision_id=source.revision_id,
        saved_content_hash=source.content_hash,
    )
    working.move_entity(
        'speaker-fl',
        Position3(x_m=1.75, y_m=0.75, z_m=1.05),
    )
    return repository.save(
        working.committed_document,
        parent_revision_id=source.revision_id,
    ).revision


def _rewrite_zip(source: Path, destination: Path, replacements: dict[str, bytes]) -> None:
    with ZipFile(source, 'r') as original, ZipFile(
        destination,
        'w',
        compression=ZIP_DEFLATED,
    ) as rewritten:
        for info in original.infolist():
            payload = replacements.get(info.filename, original.read(info.filename))
            rewritten.writestr(info.filename, payload)


def test_native_backup_round_trip_restores_database_and_content_addressed_assets(tmp_path: Path):
    data_dir = tmp_path / 'data'
    repository, first, digest, raw = _seed_data(data_dir)
    backup_path = tmp_path / 'baseline.htdt-backup'

    manifest = create_backup(data_dir, backup_path)
    validated = validate_backup(backup_path)

    assert validated == manifest
    assert {entry.path for entry in manifest.files} == {
        'cad-scenes.sqlite3',
        f'measurement-assets/{digest}',
    }

    second = _mutate_scene(repository, first.revision_id)
    assert second.revision_id != first.revision_id
    assert SceneRepository(repository.path).latest(first.document_id).revision_id == second.revision_id

    restored, pre_restore = restore_backup(data_dir, backup_path)

    assert restored == manifest
    assert pre_restore is not None and pre_restore.is_file()
    validate_backup(pre_restore)
    reopened = SceneRepository(data_dir / 'cad-scenes.sqlite3')
    assert reopened.latest(first.document_id).revision_id == first.revision_id
    assert (data_dir / 'measurement-assets' / digest).read_bytes() == raw


def test_backup_validation_rejects_asset_content_tampering(tmp_path: Path):
    data_dir = tmp_path / 'data'
    _repository, _first, digest, _raw = _seed_data(data_dir)
    valid = tmp_path / 'valid.htdt-backup'
    corrupt = tmp_path / 'corrupt.htdt-backup'
    create_backup(data_dir, valid)

    _rewrite_zip(
        valid,
        corrupt,
        {f'measurement-assets/{digest}': b'tampered payload'},
    )

    with pytest.raises(ValueError, match='size mismatch|SHA-256 mismatch'):
        validate_backup(corrupt)


def test_backup_validation_rejects_path_traversal_member(tmp_path: Path):
    data_dir = tmp_path / 'data'
    _seed_data(data_dir)
    valid = tmp_path / 'valid.htdt-backup'
    malicious = tmp_path / 'malicious.htdt-backup'
    create_backup(data_dir, valid)

    with ZipFile(valid, 'r') as original, ZipFile(
        malicious,
        'w',
        compression=ZIP_DEFLATED,
    ) as rewritten:
        for info in original.infolist():
            rewritten.writestr(info.filename, original.read(info.filename))
        rewritten.writestr('../escape.txt', b'escape')

    with pytest.raises(ValueError, match='unsafe backup archive path'):
        validate_backup(malicious)
    assert not (tmp_path / 'escape.txt').exists()


def test_failed_restore_leaves_current_native_data_unchanged(tmp_path: Path):
    data_dir = tmp_path / 'data'
    repository, first, digest, _raw = _seed_data(data_dir)
    baseline = tmp_path / 'baseline.htdt-backup'
    corrupt = tmp_path / 'corrupt.htdt-backup'
    create_backup(data_dir, baseline)

    second = _mutate_scene(repository, first.revision_id)
    _rewrite_zip(
        baseline,
        corrupt,
        {f'measurement-assets/{digest}': b'corrupt'},
    )

    with pytest.raises(ValueError):
        restore_backup(data_dir, corrupt)

    reopened = SceneRepository(data_dir / 'cad-scenes.sqlite3')
    assert reopened.latest(first.document_id).revision_id == second.revision_id
