from pathlib import Path

from htdt.cad_repository import SceneRepository
from htdt.cad_scene import (
    Offset3,
    Position3,
    SceneEntity,
    Size3,
    make_f1_scene,
    quaternion_from_euler_deg,
)
from htdt.cad_system_variant import (
    ChannelRoleBinding,
    ProposalEvidenceRef,
    ProposedEntitySpec,
    build_system_variant,
)
from htdt.cad_system_variant_repository import CadSystemVariantRepository
from htdt.report import (
    build_installation_output,
    render_installation_csv,
    render_installation_report_html,
)


def _installation_scene():
    base = make_f1_scene()
    additions = (
        SceneEntity(
            entity_id='seat-main',
            kind='seat',
            name='Main seat',
            position=Position3(x_m=3.0, y_m=3.1, z_m=0.45),
            size_m=Size3(x_m=0.7, y_m=0.8, z_m=0.9),
            acoustic_reference_offset_m=Offset3(z_m=0.65),
        ),
        SceneEntity(
            entity_id='screen-main',
            kind='screen',
            name='Main screen',
            position=Position3(x_m=3.0, y_m=0.12, z_m=1.35),
            size_m=Size3(x_m=2.8, y_m=0.08, z_m=1.58),
        ),
    )
    return base.model_copy(update={'entities': base.entities + additions})


def _variant(revision):
    changed = revision.document.entity('speaker-fl').model_copy(update={
        'orientation': quaternion_from_euler_deg(
            yaw_deg=12.0,
            pitch_deg=-4.0,
            roll_deg=0.0,
        ),
    })
    return build_system_variant(
        baseline=revision,
        name='installation candidate',
        role_bindings=(
            ChannelRoleBinding(role_id='FL', display_name='Front Left'),
            ChannelRoleBinding(role_id='C', display_name='Center'),
            ChannelRoleBinding(role_id='FR', display_name='Front Right'),
        ),
        proposed_entities=(
            ProposedEntitySpec(
                spec_id='speaker-fl-pose',
                entity=changed,
                role_binding_id='FL',
            ),
        ),
        proposal_evidence=(
            ProposalEvidenceRef(
                evidence_kind='objective',
                evidence_id='objective-1',
                evidence_sha256='a' * 64,
            ),
        ),
        created_at_utc='2026-09-19T07:00:00+00:00',
    )


def test_installation_output_is_semantic_and_generation_metadata_free(tmp_path: Path) -> None:
    scene_repository = SceneRepository(tmp_path / 'scene.sqlite3')
    saved = scene_repository.save(_installation_scene(), parent_revision_id=None)
    variant = _variant(saved.revision)

    output = build_installation_output(saved.revision, variant=variant)
    speaker = next(item for item in output.entities if item.entity_id == 'speaker-fl')
    assert speaker.body_yaw_deg == 12.0
    assert speaker.body_pitch_deg == -4.0
    assert speaker.mounting_height_m == speaker.z_m
    assert speaker.mounting_height_reference == 'scene_entity_origin_z'
    assert {item.entity_kind for item in output.entities} >= {
        'speaker',
        'seat',
        'screen',
        'measurement_point',
    }
    projector = next(item for item in output.sections if item.section == 'projector_coordinates')
    assert projector.status == 'UNKNOWN'
    assert next(item for item in output.sections if item.section == 'standards_profile').status == 'UNKNOWN'
    assert len(output.dimensions) == 3
    assert {item.view for item in output.dimensions} == {'top', 'front', 'side'}
    assert output.authority.system_variant_id == variant.variant_id
    assert output.authority.system_variant_sha256 == variant.variant_sha256
    assert output.evidence[0].evidence_id == 'objective-1'

    first = render_installation_report_html(
        output,
        exported_at_utc='2026-09-19T07:01:00+00:00',
    )
    second = render_installation_report_html(
        output,
        exported_at_utc='2026-09-19T08:02:00+00:00',
    )
    assert first != second
    assert output.semantic_sha256 in first
    assert output.semantic_sha256 in second
    assert 'generation metadata is not part of semantic identity' in first
    assert '2026-09-19T07:01:00+00:00' not in output.model_dump_json()

    csv_a = render_installation_csv(output)
    csv_b = render_installation_csv(output)
    assert csv_a == csv_b
    assert 'exported_at' not in csv_a
    assert output.semantic_sha256 in csv_a
    assert 'screen-main' in csv_a
    assert 'seat-main' in csv_a


def test_installation_output_regenerates_identically_after_repository_reopen(
    tmp_path: Path,
) -> None:
    database = tmp_path / 'scene.sqlite3'
    scene_repository = SceneRepository(database)
    saved = scene_repository.save(_installation_scene(), parent_revision_id=None)
    variant_repository = CadSystemVariantRepository(scene_repository)
    variant = _variant(saved.revision)
    variant_repository.save_variant(variant)

    before = build_installation_output(saved.revision, variant=variant)

    reopened_scene_repository = SceneRepository(database)
    reopened_variant_repository = CadSystemVariantRepository(reopened_scene_repository)
    reopened_revision = reopened_scene_repository.get(saved.revision.revision_id)
    reopened_variant = reopened_variant_repository.get_variant(variant.variant_id)

    assert reopened_revision is not None
    assert reopened_variant is not None
    after = build_installation_output(reopened_revision, variant=reopened_variant)

    assert after == before
    assert after.semantic_sha256 == before.semantic_sha256
    assert render_installation_csv(after) == render_installation_csv(before)
