from __future__ import annotations

from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from .cad_measurement_models import CadFrequencyResponseDataset, CadMeasurementRecord
from .cad_repository import SceneRevision
from .cad_scene import Direction3, acoustic_reference_position
from .database import utc_now
from .rew_api import REW_API_ADAPTER_VERSION, REW_API_SNAPSHOT_FORMAT, RewFrequencyResponseSnapshot
from .rew_parser import parse_rew_frequency_response


class CadMeasurementError(ValueError):
    pass


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def measurement_record_for_revision(
    revision: SceneRevision,
    measurement_entity_id: str,
    *,
    measurement_id: str | None = None,
    measurement_direction: Direction3 | None = None,
    evidence_type: str = 'unknown',
    channel_role: str = 'unknown',
    source_speaker_ids: tuple[str, ...] = (),
    radiation_scope: str = 'unknown',
    routing_evidence: str = 'unknown',
    captured_at: str | None = None,
    imported_at: str | None = None,
    source_kind: str,
    external_source_id: str | None = None,
    quality_status: str = 'unknown',
    quality_reasons: tuple[str, ...] = (),
    quality_source: str = 'unknown',
    provenance: dict[str, Any] | None = None,
) -> CadMeasurementRecord:
    try:
        entity = revision.document.entity(measurement_entity_id)
    except KeyError as exc:
        raise CadMeasurementError(f'unknown measurement entity: {measurement_entity_id}') from exc
    position = acoustic_reference_position(entity)
    if position is None:
        raise CadMeasurementError(
            f'entity {measurement_entity_id} does not expose an acoustic reference position'
        )

    for source_id in source_speaker_ids:
        try:
            source = revision.document.entity(source_id)
        except KeyError as exc:
            raise CadMeasurementError(f'unknown source speaker: {source_id}') from exc
        if source.kind != 'speaker':
            raise CadMeasurementError(f'source entity is not a speaker: {source_id}')

    return CadMeasurementRecord(
        measurement_id=measurement_id or str(uuid4()),
        document_id=revision.document_id,
        scene_revision_id=revision.revision_id,
        scene_content_hash=revision.content_hash,
        measurement_entity_id=measurement_entity_id,
        measurement_position=position,
        measurement_direction=measurement_direction,
        evidence_type=evidence_type,
        channel_role=channel_role,
        source_speaker_ids=source_speaker_ids,
        radiation_scope=radiation_scope,
        routing_evidence=routing_evidence,
        captured_at=captured_at,
        imported_at=imported_at or utc_now(),
        source_kind=source_kind,
        external_source_id=external_source_id,
        quality_status=quality_status,
        quality_reasons=quality_reasons,
        quality_source=quality_source,
        provenance_json=canonical_json(provenance or {}),
    )


def normalize_rew_api_snapshot(
    revision: SceneRevision,
    measurement_entity_id: str,
    snapshot: RewFrequencyResponseSnapshot,
    *,
    evidence_type: str = 'unknown',
    channel_role: str = 'unknown',
    source_speaker_ids: tuple[str, ...] = (),
    radiation_scope: str = 'unknown',
    routing_evidence: str = 'unknown',
    imported_at: str | None = None,
) -> tuple[CadMeasurementRecord, CadFrequencyResponseDataset, str, bytes]:
    decoded = snapshot.decoded
    wrapper = {
        'format': REW_API_SNAPSHOT_FORMAT,
        'measurement_uuid': decoded.measurement_id,
        'query': snapshot.query,
        'measurement_summary': snapshot.measurement_summary,
        'frequency_response': snapshot.raw_frequency_response,
    }
    raw = canonical_json(wrapper).encode('utf-8')
    digest = sha256(raw).hexdigest()
    summary = snapshot.measurement_summary
    captured_at = summary.get('date') if isinstance(summary.get('date'), str) and summary.get('date') else None
    phase_status = 'unknown' if decoded.phase_deg is not None else 'absent'
    warnings = []
    if decoded.phase_deg is not None and all(value == 0 for value in decoded.phase_deg):
        warnings.append('phase_all_zero_unverified')

    record = measurement_record_for_revision(
        revision,
        measurement_entity_id,
        evidence_type=evidence_type,
        channel_role=channel_role,
        source_speaker_ids=source_speaker_ids,
        radiation_scope=radiation_scope,
        routing_evidence=routing_evidence,
        captured_at=captured_at,
        imported_at=imported_at,
        source_kind='rew_api',
        external_source_id=decoded.measurement_id,
        provenance={
            'adapter_version': REW_API_ADAPTER_VERSION,
            'rew_version': summary.get('rewVersion') if isinstance(summary.get('rewVersion'), str) else None,
            'requested': {
                'unit': decoded.requested_unit,
                'ppo': decoded.requested_ppo,
                'smoothing': decoded.requested_smoothing,
            },
            'returned': {
                'unit': decoded.unit,
                'ppo': decoded.points_per_octave,
                'freq_step_hz': decoded.frequency_step_hz,
                'smoothing': decoded.smoothing,
                'start_frequency_hz': decoded.start_frequency_hz,
            },
            'warnings': warnings,
        },
    )
    dataset = CadFrequencyResponseDataset(
        dataset_id=str(uuid4()),
        measurement_id=record.measurement_id,
        frequency_hz=decoded.frequency_hz,
        level_db=decoded.magnitude,
        phase_deg=decoded.phase_deg,
        phase_status=phase_status,
        level_reference='unknown',
        smoothing=decoded.smoothing,
        processing_json=canonical_json({
            'requested_unit': decoded.requested_unit,
            'requested_ppo': decoded.requested_ppo,
            'requested_smoothing': decoded.requested_smoothing,
            'returned_unit': decoded.unit,
            'returned_ppo': decoded.points_per_octave,
            'returned_frequency_step_hz': decoded.frequency_step_hz,
        }),
        source_sha256=digest,
        importer_version=REW_API_ADAPTER_VERSION,
    )
    return record, dataset, f'rew-api-{decoded.measurement_id}.json', raw


def normalize_rew_text(
    revision: SceneRevision,
    measurement_entity_id: str,
    raw: bytes,
    *,
    filename: str,
    evidence_type: str = 'unknown',
    channel_role: str = 'unknown',
    source_speaker_ids: tuple[str, ...] = (),
    radiation_scope: str = 'unknown',
    routing_evidence: str = 'unknown',
    imported_at: str | None = None,
) -> tuple[CadMeasurementRecord, CadFrequencyResponseDataset, str, bytes]:
    parsed = parse_rew_frequency_response(raw)
    record = measurement_record_for_revision(
        revision,
        measurement_entity_id,
        evidence_type=evidence_type,
        channel_role=channel_role,
        source_speaker_ids=source_speaker_ids,
        radiation_scope=radiation_scope,
        routing_evidence=routing_evidence,
        captured_at=None,
        imported_at=imported_at,
        source_kind='rew_text',
        external_source_id=None,
        provenance={
            'filename': filename,
            'header_lines': parsed.header_lines,
            'warnings': parsed.warnings,
        },
    )
    dataset = CadFrequencyResponseDataset(
        dataset_id=str(uuid4()),
        measurement_id=record.measurement_id,
        frequency_hz=parsed.frequency_hz,
        level_db=parsed.level_db,
        phase_deg=parsed.phase_deg,
        phase_status=parsed.phase_status,
        level_reference=parsed.level_reference,
        smoothing=None,
        processing_json=canonical_json({'warnings': parsed.warnings}),
        source_sha256=parsed.source_sha256,
        importer_version=parsed.parser_version,
    )
    return record, dataset, filename, raw
