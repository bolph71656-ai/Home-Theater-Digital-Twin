from pathlib import Path

from htdt.database import Store


def _context_payload() -> dict:
    return {
        'room': {'width_m': 4.0, 'depth_m': 5.0, 'height_m': 2.4, 'geometry_kind': 'rectangular', 'notes': None},
        'speakers': [],
        'measurement_point': {'point_id': 'mlp', 'label': 'MLP', 'position': {'x_m': 2.0, 'y_m': 3.0, 'z_m': 1.0}, 'aim_xyz': None, 'position_precision_m': None},
        'avr': {'manufacturer': 'Yamaha', 'model': 'RX-A4A', 'firmware': None, 'input_name': None, 'volume_db': None, 'processing_mode': None, 'peq_mode': None, 'extra': {}},
        'notes': None,
        'parent_context_id': None,
    }


def test_store_import_and_backup_restore(tmp_path: Path) -> None:
    store = Store(tmp_path / 'source')
    project = store.create_project('Living room')
    context = store.create_context(project['id'], _context_payload(), None)
    imported = store.import_measurement(project['id'], context['id'], 'fl.txt', b'20 70\n40 71\n80 72\n160 73\n', 'front_left', 'measured', ['fl'], 'single', None, None)
    assert imported['points'] == 4
    assert len(store.list_measurements(project['id'])) == 1

    archive = store.backup_to(tmp_path / 'backup.zip')
    restored = Store(tmp_path / 'restored')
    restored.restore_from(archive)
    projects = restored.list_projects()
    assert projects[0]['name'] == 'Living room'
    assert len(restored.list_measurements(project['id'])) == 1
