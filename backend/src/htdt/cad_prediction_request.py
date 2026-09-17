from __future__ import annotations

from dataclasses import dataclass

from .cad_prediction_models import canonical_prediction_json, prediction_input_hash
from .cad_predictions import (
    RECTANGULAR_GEOMETRY_MODEL_ID,
    RECTANGULAR_GEOMETRY_MODEL_VERSION,
    _inside_frame,
    _position_payload,
    _surface_identities,
    exact_rectangular_room_frame,
)
from .cad_repository import SceneRevision
from .cad_scene import acoustic_reference_position


@dataclass(frozen=True)
class RectangularGeometryRequestIdentity:
    model_id: str
    model_version: str
    parameters_json: str
    input_snapshot_json: str
    input_hash: str
    geometry_compatibility: str


def rectangular_geometry_request_identity(
    revision: SceneRevision,
    receiver_entity_id: str,
    *,
    max_mode_hz: float = 300.0,
    sound_speed_m_s: float = 343.0,
) -> RectangularGeometryRequestIdentity:
    """Build the exact canonical model identity used by the rectangular adapter."""

    room = revision.document.room
    if room is None:
        raise ValueError('prediction requires a room')
    receiver_entity = revision.document.entity(receiver_entity_id)
    receiver = acoustic_reference_position(receiver_entity)
    if receiver is None:
        raise ValueError('receiver entity has no acoustic reference position')

    parameters_json = canonical_prediction_json(
        {'max_mode_hz': float(max_mode_hz), 'sound_speed_m_s': float(sound_speed_m_s)}
    )
    speaker_inputs: list[dict[str, object]] = []
    for entity in revision.document.entities:
        if entity.kind != 'speaker':
            continue
        reference = acoustic_reference_position(entity)
        speaker_inputs.append(
            {
                'entity_id': entity.entity_id,
                'speaker_role': entity.speaker_role,
                'acoustic_reference_position': _position_payload(reference),
            }
        )

    frame = exact_rectangular_room_frame(room)
    if frame is None:
        input_snapshot_json = canonical_prediction_json(
            {
                'room': room.model_dump(mode='json'),
                'receiver_entity_id': receiver_entity_id,
                'receiver_position': _position_payload(receiver),
                'speakers': speaker_inputs,
                'approximation_rule': None,
            }
        )
        compatibility = 'unsupported'
    else:
        if not _inside_frame(receiver, frame):
            raise ValueError('receiver acoustic reference is outside the rectangular room')
        input_snapshot_json = canonical_prediction_json(
            {
                'room_frame': {
                    'origin_x_m': frame.origin_x_m,
                    'origin_y_m': frame.origin_y_m,
                    'width_m': frame.width_m,
                    'depth_m': frame.depth_m,
                    'height_m': frame.height_m,
                },
                'receiver_entity_id': receiver_entity_id,
                'receiver_position': _position_payload(receiver),
                'speakers': speaker_inputs,
                'surface_identities': _surface_identities(revision, frame),
                'approximation_rule': None,
            }
        )
        compatibility = 'exact_for_model_geometry'

    return RectangularGeometryRequestIdentity(
        model_id=RECTANGULAR_GEOMETRY_MODEL_ID,
        model_version=RECTANGULAR_GEOMETRY_MODEL_VERSION,
        parameters_json=parameters_json,
        input_snapshot_json=input_snapshot_json,
        input_hash=prediction_input_hash(input_snapshot_json),
        geometry_compatibility=compatibility,
    )
