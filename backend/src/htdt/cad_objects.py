from __future__ import annotations

from math import sqrt

from .cad_scene import Direction3, SceneDocument, SceneEntity, acoustic_reference_position


class TheaterObjectError(ValueError):
    pass


def speaker_aim_replacements(
    document: SceneDocument,
    speaker_ids: tuple[str, ...],
    target_id: str,
) -> tuple[SceneEntity, ...]:
    """Return speaker replacements aimed at a seat/measurement acoustic reference.

    Body pose is intentionally untouched. The function only resolves explicit
    acoustic references into world-space normalized ``aim_xyz`` values.
    """

    if not speaker_ids:
        return ()
    if len(speaker_ids) != len(set(speaker_ids)):
        raise TheaterObjectError('speaker ids must be unique')

    target = document.entity(target_id)
    if target.kind not in {'seat', 'measurement_point'}:
        raise TheaterObjectError('aim target must be a seat or measurement point')
    target_position = acoustic_reference_position(target)
    if target_position is None:
        raise TheaterObjectError('aim target has no acoustic reference position')

    replacements: list[SceneEntity] = []
    for speaker_id in speaker_ids:
        speaker = document.entity(speaker_id)
        if speaker.kind != 'speaker':
            raise TheaterObjectError(f'aim source is not a speaker: {speaker_id}')
        source_position = acoustic_reference_position(speaker) or speaker.position
        delta = (
            target_position.x_m - source_position.x_m,
            target_position.y_m - source_position.y_m,
            target_position.z_m - source_position.z_m,
        )
        length = sqrt(sum(value * value for value in delta))
        if length <= 1e-12:
            raise TheaterObjectError(f'speaker acoustic reference overlaps target: {speaker_id}')
        aim = Direction3(
            x=delta[0] / length,
            y=delta[1] / length,
            z=delta[2] / length,
        )
        replacements.append(speaker.model_copy(update={'aim_xyz': aim}))
    return tuple(replacements)
