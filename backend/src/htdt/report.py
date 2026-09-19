from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import csv
import io
import json
import math
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_repository import SceneRevision
from .cad_scene import SceneDocument, SceneEntity, quaternion_to_euler_deg, scene_content_hash
from .cad_system_variant import SystemVariant, materialize_system_variant
from .cad_standards import StandardsEvaluation, StandardsProfile
from .cad_video_geometry import ProjectorSpecification, VideoGeometryEvaluation


REPORT_SCHEMA_VERSION = 1
REPORT_RENDERER_VERSION = 'comparison-report-1'


def _finite_numbers(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    result: list[float] = []
    for value in values:
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            result.append(float(value))
    return result


def build_report_payload(project: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    return {
        'report_schema_version': REPORT_SCHEMA_VERSION,
        'renderer_version': REPORT_RENDERER_VERSION,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'project': {
            'id': project['id'],
            'name': project['name'],
        },
        'comparison': comparison,
        'interpretation_notice': (
            'This report preserves a saved comparison snapshot. Geometry matches and measured differences are evidence/candidates, '
            'not automatic proof of acoustic causation or optimality.'
        ),
    }


def _svg_chart(result: dict[str, Any]) -> str:
    frequencies = _finite_numbers(result.get('grid_hz'))
    a_values = _finite_numbers(result.get('a_db'))
    b_values = _finite_numbers(result.get('b_db'))
    count = min(len(frequencies), len(a_values), len(b_values))
    if count < 2:
        return '<p class="muted">No aligned frequency-response points were saved with this comparison.</p>'
    frequencies, a_values, b_values = frequencies[:count], a_values[:count], b_values[:count]
    if frequencies[0] <= 0 or frequencies[-1] <= frequencies[0]:
        return '<p class="muted">Saved frequency grid is not suitable for a logarithmic report chart.</p>'

    width, height = 920.0, 360.0
    left, right, top, bottom = 64.0, 24.0, 24.0, 46.0
    plot_w, plot_h = width - left - right, height - top - bottom
    y_min = min(a_values + b_values)
    y_max = max(a_values + b_values)
    if math.isclose(y_min, y_max):
        y_min -= 1.0
        y_max += 1.0
    else:
        padding = max(1.0, (y_max - y_min) * 0.08)
        y_min -= padding
        y_max += padding
    x0, x1 = math.log2(frequencies[0]), math.log2(frequencies[-1])

    def point(frequency: float, level: float) -> tuple[float, float]:
        x = left + ((math.log2(frequency) - x0) / (x1 - x0)) * plot_w
        y = top + ((y_max - level) / (y_max - y_min)) * plot_h
        return x, y

    def polyline(levels: list[float]) -> str:
        return ' '.join(f'{x:.2f},{y:.2f}' for x, y in (point(f, level) for f, level in zip(frequencies, levels, strict=True)))

    x_ticks = []
    for frequency in (20, 30, 40, 50, 80, 100, 200, 300, 500, 1000, 2000, 5000, 10000, 20000):
        if frequencies[0] <= frequency <= frequencies[-1]:
            x, _ = point(float(frequency), y_min)
            x_ticks.append(f'<line x1="{x:.2f}" y1="{top:.2f}" x2="{x:.2f}" y2="{top + plot_h:.2f}" class="grid"/><text x="{x:.2f}" y="{height - 16:.2f}" text-anchor="middle">{frequency:g}</text>')
    y_ticks = []
    first_tick = math.ceil(y_min / 5.0) * 5.0
    tick = first_tick
    while tick <= y_max + 1e-9:
        _, y = point(frequencies[0], tick)
        y_ticks.append(f'<line x1="{left:.2f}" y1="{y:.2f}" x2="{left + plot_w:.2f}" y2="{y:.2f}" class="grid"/><text x="{left - 10:.2f}" y="{y + 4:.2f}" text-anchor="end">{tick:g}</text>')
        tick += 5.0

    return f'''<svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="Saved A and B frequency responses">
      <style>.grid{{stroke:#d9dde3;stroke-width:1}} .axis{{stroke:#49515b;stroke-width:1.2}} text{{font:12px system-ui;fill:#4a5159}} .a{{fill:none;stroke:#2457c5;stroke-width:2}} .b{{fill:none;stroke:#b53b31;stroke-width:2}}</style>
      {''.join(x_ticks)}{''.join(y_ticks)}
      <line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" class="axis"/>
      <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis"/>
      <polyline class="a" points="{polyline(a_values)}"/>
      <polyline class="b" points="{polyline(b_values)}"/>
      <text x="{left + 8}" y="{top + 16}">A</text><text x="{left + 34}" y="{top + 16}" fill="#b53b31">B</text>
      <text x="{left + plot_w / 2}" y="{height - 2}" text-anchor="middle">Frequency (Hz, log scale)</text>
    </svg>'''


def _metric(value: Any) -> str:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f'{float(value):.3f}'
    return '—'


def _difference_rows(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return '<tr><td colspan="3">None</td></tr>'
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append(
            f'<tr><td><code>{escape(str(item.get("path", "")))}</code></td>'
            f'<td>{escape(json.dumps(item.get("a"), ensure_ascii=False))}</td>'
            f'<td>{escape(json.dumps(item.get("b"), ensure_ascii=False))}</td></tr>'
        )
    return ''.join(rows) or '<tr><td colspan="3">None</td></tr>'


def render_report_html(payload: dict[str, Any]) -> str:
    comparison = payload['comparison']
    spec = comparison.get('spec') or {}
    result = comparison.get('result') or {}
    measurement_a = result.get('measurement_a') or {}
    measurement_b = result.get('measurement_b') or {}
    warnings = result.get('interpretation_warnings') or []
    warning_html = ''.join(f'<li>{escape(str(item))}</li>' for item in warnings) or '<li>None saved</li>'
    embedded_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HTDT comparison {escape(str(comparison['id']))}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f6f8;color:#1e242b}}main{{max-width:1080px;margin:auto;padding:32px}}
section{{background:white;border:1px solid #d9dde3;border-radius:10px;padding:20px;margin:16px 0}}h1,h2{{margin-top:0}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #e4e7eb;padding:8px;text-align:left;vertical-align:top}}code{{font-size:.9em}}.muted{{color:#606a75}}.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.metric{{border:1px solid #e1e4e8;border-radius:8px;padding:12px}}.metric strong{{display:block;font-size:1.25rem}}.warn{{border-left:4px solid #a46a00;padding-left:12px}}svg{{width:100%;height:auto}}@media(max-width:700px){{.metrics{{grid-template-columns:1fr 1fr}}}}
</style></head><body><main>
<h1>Home Theater Digital Twin — Comparison Report</h1>
<p class="muted">Project: {escape(str(payload['project']['name']))} · comparison {escape(str(comparison['id']))} · saved {escape(str(comparison.get('created_at', '—')))}</p>
<section><h2>Interpretation boundary</h2><p>{escape(payload['interpretation_notice'])}</p><ul class="warn">{warning_html}</ul></section>
<section><h2>Saved metrics</h2><div class="metrics">
<div class="metric"><span>Mean A−B</span><strong>{_metric(result.get('mean_difference_db'))} dB</strong></div>
<div class="metric"><span>RMS difference</span><strong>{_metric(result.get('rms_difference_db'))} dB</strong></div>
<div class="metric"><span>Level offset</span><strong>{_metric(result.get('level_offset_db'))} dB</strong></div>
<div class="metric"><span>Shape RMS</span><strong>{_metric(result.get('shape_rms_db'))} dB</strong></div></div>
<p>Algorithm: <code>{escape(str(result.get('algorithm_version', 'unknown')))}</code> · role: <code>{escape(str(result.get('comparison_role', 'unknown')))}</code> · valid points: {escape(str(result.get('valid_points', '—')))} / {escape(str(result.get('total_grid_points', '—')))}</p></section>
<section><h2>Saved A/B curves</h2>{_svg_chart(result)}</section>
<section><h2>Measurements</h2><table><thead><tr><th></th><th>A</th><th>B</th></tr></thead><tbody>
<tr><th>Dataset ID</th><td><code>{escape(str(comparison.get('dataset_a_id', '')))}</code></td><td><code>{escape(str(comparison.get('dataset_b_id', '')))}</code></td></tr>
<tr><th>Measurement ID</th><td><code>{escape(str(measurement_a.get('measurement_id', '—')))}</code></td><td><code>{escape(str(measurement_b.get('measurement_id', '—')))}</code></td></tr>
<tr><th>Context ID</th><td><code>{escape(str(measurement_a.get('context_id', '—')))}</code></td><td><code>{escape(str(measurement_b.get('context_id', '—')))}</code></td></tr>
<tr><th>Channel</th><td>{escape(str(measurement_a.get('channel_role', '—')))}</td><td>{escape(str(measurement_b.get('channel_role', '—')))}</td></tr>
<tr><th>Evidence</th><td>{escape(str(measurement_a.get('evidence_type', '—')))}</td><td>{escape(str(measurement_b.get('evidence_type', '—')))}</td></tr>
<tr><th>Quality</th><td>{escape(str(measurement_a.get('quality_status', '—')))}</td><td>{escape(str(measurement_b.get('quality_status', '—')))}</td></tr>
<tr><th>Repeat group</th><td>{escape(str(measurement_a.get('repeat_group', '—')))}</td><td>{escape(str(measurement_b.get('repeat_group', '—')))}</td></tr>
</tbody></table></section>
<section><h2>Comparison specification</h2><pre>{escape(json.dumps(spec, ensure_ascii=False, indent=2))}</pre></section>
<section><h2>Intended changes</h2><table><thead><tr><th>Path</th><th>A</th><th>B</th></tr></thead><tbody>{_difference_rows(result.get('intended_changes'))}</tbody></table></section>
<section><h2>Confounders</h2><table><thead><tr><th>Path</th><th>A</th><th>B</th></tr></thead><tbody>{_difference_rows(result.get('confounders'))}</tbody></table></section>
<section><h2>Machine-readable snapshot</h2><p class="muted">The complete report payload is embedded below and in the page as application/json.</p><details><summary>Show JSON</summary><pre>{escape(json.dumps(payload, ensure_ascii=False, indent=2))}</pre></details></section>
<script type="application/json" id="htdt-report-data">{embedded_json}</script>
</main></body></html>'''


INSTALLATION_OUTPUT_SCHEMA_VERSION = 2
INSTALLATION_OUTPUT_AUTHORITY_VERSION = 'installation-output-2'
INSTALLATION_REPORT_RENDERER_VERSION = 'installation-report-2'


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def _semantic_digest(value: Any) -> str:
    from hashlib import sha256

    return sha256(_canonical(value).encode('utf-8')).hexdigest()


class InstallationEvidenceRef(BaseModel):
    """Exact immutable evidence identity referenced by an installation output."""

    model_config = ConfigDict(frozen=True)

    authority: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    evidence_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    evidence_type: str | None = Field(default=None, min_length=1)


class InstallationAuthorityBinding(BaseModel):
    """The exact scene/variant authority used to materialize installation geometry."""

    model_config = ConfigDict(frozen=True)

    document_id: str = Field(min_length=1)
    scene_revision_id: str = Field(min_length=1)
    scene_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    effective_scene_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    system_variant_id: str | None = Field(default=None, min_length=1)
    system_variant_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def variant_pair(self) -> 'InstallationAuthorityBinding':
        if (self.system_variant_id is None) != (self.system_variant_sha256 is None):
            raise ValueError('SystemVariant id/hash must be supplied together')
        return self


class InstallationEntityOutput(BaseModel):
    """Installation-facing pose data derived only from Scene authority."""

    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    speaker_role: str | None = None
    x_m: float
    y_m: float
    z_m: float
    body_yaw_deg: float
    body_pitch_deg: float
    body_roll_deg: float
    mounting_height_m: float | None = None
    mounting_height_reference: Literal['scene_entity_origin_z'] | None = None
    aim_xyz: tuple[float, float, float] | None = None


class InstallationDimensionPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    horizontal_m: float
    vertical_m: float


class InstallationDimensionSheet(BaseModel):
    """Canonical data for a dimensioned orthographic view; rendering is downstream."""

    model_config = ConfigDict(frozen=True)

    view: Literal['top', 'front', 'side']
    horizontal_axis: Literal['x', 'y']
    vertical_axis: Literal['y', 'z']
    horizontal_min_m: float
    horizontal_max_m: float
    vertical_min_m: float
    vertical_max_m: float
    points: tuple[InstallationDimensionPoint, ...]


class InstallationSectionStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    section: str = Field(min_length=1)
    status: Literal['AVAILABLE', 'UNKNOWN', 'OMITTED']
    reason: str = Field(min_length=1)


class InstallationSightlineSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    seat_entity_id: str = Field(min_length=1)
    row_id: str = Field(min_length=1)
    status: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE']
    blocking_seat_ids: tuple[str, ...] = ()
    blocking_row_ids: tuple[str, ...] = ()
    blocked_sample_ids: tuple[str, ...] = ()
    minimum_head_ray_clearance_m: float | None = None


class InstallationCollisionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_a: str = Field(min_length=1)
    entity_b: str = Field(min_length=1)
    status: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE']
    intersects_or_violates_clearance: bool


class InstallationProjectorSummary(BaseModel):
    """Read-only installation summary of exact projector/video authority."""

    model_config = ConfigDict(frozen=True)

    status: Literal['AVAILABLE', 'UNKNOWN']
    specification_id: str | None = None
    specification_version: str | None = None
    specification_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    projector_entity_id: str | None = None
    lens_reference_offset_m: tuple[float, float, float] | None = None
    lens_position_m: tuple[float, float, float] | None = None
    optical_axis_local: tuple[float, float, float] | None = None
    throw_ratio_min: float | None = None
    throw_ratio_max: float | None = None
    evaluated_throw_ratio: float | None = None
    zoom_position: float | None = None
    horizontal_lens_shift_range: tuple[float, float] | None = None
    vertical_lens_shift_range: tuple[float, float] | None = None
    required_horizontal_lens_shift_fraction: float | None = None
    required_vertical_lens_shift_fraction: float | None = None
    image_plane_corners_m: tuple[tuple[float, float, float], ...] = ()
    projection_cone_directions: tuple[tuple[float, float, float], ...] = ()
    supported_aspect_ratios: tuple[str, ...] = ()
    image_aspect_ratio: float | None = None
    screen_entity_id: str | None = None
    screen_visible_width_m: float | None = None
    screen_visible_height_m: float | None = None
    screen_frame_clearance_m: float | None = None
    video_geometry_evaluation_id: str | None = None
    video_geometry_evaluation_sha256: str | None = Field(
        default=None,
        pattern=r'^[0-9a-f]{64}$',
    )
    projection_status: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'] | None = None
    geometry_status: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'] | None = None
    sightlines: tuple[InstallationSightlineSummary, ...] = ()
    collisions: tuple[InstallationCollisionSummary, ...] = ()
    screen_acoustic_effect_status: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'] | None = None
    screen_acoustic_effect_reason: str | None = None


class InstallationStandardsCriterionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    criterion_id: str = Field(min_length=1)
    status: Literal['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE']
    observed_value: float | int | bool | str | None = None
    unit: str | None = None
    target_entity_ids: tuple[str, ...] = ()
    reason_code: str = Field(min_length=1)
    source_publisher: str = Field(min_length=1)
    source_document_title: str = Field(min_length=1)
    source_document_version: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    source_uri: str | None = None
    evidence_refs: tuple[tuple[str, str | None, str | None], ...] = ()


class InstallationStandardsSummary(BaseModel):
    """Criterion-level report view of one exact StandardsProfile/Evaluation pair."""

    model_config = ConfigDict(frozen=True)

    status: Literal['AVAILABLE', 'UNKNOWN']
    profile_id: str | None = None
    profile_version: str | None = None
    profile_semantic_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    evaluation_id: str | None = None
    evaluation_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    criteria: tuple[InstallationStandardsCriterionSummary, ...] = ()


class InstallationOutput(BaseModel):
    """Immutable semantic installation snapshot.

    Generation metadata such as exported_at is intentionally absent from this
    model and therefore cannot alter semantic_sha256. Schema v1 remains
    loadable; new generation uses v2 projector/standards authority summaries.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1, 2] = INSTALLATION_OUTPUT_SCHEMA_VERSION
    authority_version: Literal['installation-output-1', 'installation-output-2'] = (
        INSTALLATION_OUTPUT_AUTHORITY_VERSION
    )
    coordinate_system: Literal['htdt-x-right-y-rear-z-up-m'] = 'htdt-x-right-y-rear-z-up-m'
    authority: InstallationAuthorityBinding
    evidence: tuple[InstallationEvidenceRef, ...]
    entities: tuple[InstallationEntityOutput, ...]
    dimensions: tuple[InstallationDimensionSheet, ...]
    sections: tuple[InstallationSectionStatus, ...]
    projector: InstallationProjectorSummary | None = None
    standards: InstallationStandardsSummary | None = None
    semantic_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_semantic_identity(self) -> 'InstallationOutput':
        evidence_keys = [(item.authority, item.evidence_id) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError('installation evidence references must be unique by authority/id')
        if self.schema_version == 1:
            if self.authority_version != 'installation-output-1':
                raise ValueError('InstallationOutput v1 requires installation-output-1 authority')
            if self.projector is not None or self.standards is not None:
                raise ValueError('InstallationOutput v1 cannot contain v2 authority summaries')
        else:
            if self.authority_version != INSTALLATION_OUTPUT_AUTHORITY_VERSION:
                raise ValueError('InstallationOutput v2 authority version mismatch')
            if self.projector is None or self.standards is None:
                raise ValueError('InstallationOutput v2 requires explicit projector/standards summaries')
        if self.semantic_sha256 != _semantic_digest(self.identity_payload()):
            raise ValueError('InstallationOutput semantic hash mismatch')
        return self

    def identity_payload(self) -> dict[str, Any]:
        payload = {
            'schema_version': self.schema_version,
            'authority_version': self.authority_version,
            'coordinate_system': self.coordinate_system,
            'authority': self.authority.model_dump(mode='json'),
            'evidence': [item.model_dump(mode='json') for item in self.evidence],
            'entities': [item.model_dump(mode='json') for item in self.entities],
            'dimensions': [item.model_dump(mode='json') for item in self.dimensions],
            'sections': [item.model_dump(mode='json') for item in self.sections],
        }
        if self.schema_version >= 2:
            payload['projector'] = self.projector.model_dump(mode='json') if self.projector else None
            payload['standards'] = self.standards.model_dump(mode='json') if self.standards else None
        return payload


def _installation_entity(entity: SceneEntity) -> InstallationEntityOutput:
    yaw, pitch, roll = quaternion_to_euler_deg(entity.orientation)
    aim = None
    if entity.aim_xyz is not None:
        aim = (float(entity.aim_xyz.x), float(entity.aim_xyz.y), float(entity.aim_xyz.z))
    is_speaker = str(entity.kind) == 'speaker'
    return InstallationEntityOutput(
        entity_id=entity.entity_id,
        entity_kind=str(entity.kind),
        name=entity.name,
        speaker_role=entity.speaker_role,
        x_m=float(entity.position.x_m),
        y_m=float(entity.position.y_m),
        z_m=float(entity.position.z_m),
        body_yaw_deg=float(yaw),
        body_pitch_deg=float(pitch),
        body_roll_deg=float(roll),
        mounting_height_m=float(entity.position.z_m) if is_speaker else None,
        mounting_height_reference='scene_entity_origin_z' if is_speaker else None,
        aim_xyz=aim,
    )


def _dimension_sheets(
    document: SceneDocument,
    entities: Sequence[InstallationEntityOutput],
) -> tuple[InstallationDimensionSheet, ...]:
    if document.room is None:
        return ()
    min_x, min_y, max_x, max_y = document.room.bounds_m
    height = float(document.room.height_m)

    def points(horizontal: str, vertical: str) -> tuple[InstallationDimensionPoint, ...]:
        rows = []
        for item in entities:
            coordinate = {'x': item.x_m, 'y': item.y_m, 'z': item.z_m}
            rows.append(InstallationDimensionPoint(
                entity_id=item.entity_id,
                entity_kind=item.entity_kind,
                horizontal_m=coordinate[horizontal],
                vertical_m=coordinate[vertical],
            ))
        return tuple(rows)

    return (
        InstallationDimensionSheet(
            view='top',
            horizontal_axis='x',
            vertical_axis='y',
            horizontal_min_m=float(min_x),
            horizontal_max_m=float(max_x),
            vertical_min_m=float(min_y),
            vertical_max_m=float(max_y),
            points=points('x', 'y'),
        ),
        InstallationDimensionSheet(
            view='front',
            horizontal_axis='x',
            vertical_axis='z',
            horizontal_min_m=float(min_x),
            horizontal_max_m=float(max_x),
            vertical_min_m=0.0,
            vertical_max_m=height,
            points=points('x', 'z'),
        ),
        InstallationDimensionSheet(
            view='side',
            horizontal_axis='y',
            vertical_axis='z',
            horizontal_min_m=float(min_y),
            horizontal_max_m=float(max_y),
            vertical_min_m=0.0,
            vertical_max_m=height,
            points=points('y', 'z'),
        ),
    )


def _xyz_position(value: Any) -> tuple[float, float, float]:
    return (float(value.x_m), float(value.y_m), float(value.z_m))


def _xyz_direction(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def _projector_summary(
    *,
    revision: SceneRevision,
    variant: SystemVariant | None,
    document: SceneDocument,
    effective_hash: str,
    specification: ProjectorSpecification | None,
    evaluation: VideoGeometryEvaluation | None,
) -> InstallationProjectorSummary:
    if specification is None and evaluation is None:
        return InstallationProjectorSummary(status='UNKNOWN')
    if specification is None or evaluation is None:
        raise ValueError(
            'ProjectorSpecification and VideoGeometryEvaluation must be supplied together'
        )

    target = evaluation.target
    expected_variant_id = None if variant is None else variant.variant_id
    expected_variant_sha256 = None if variant is None else variant.variant_sha256
    if (
        target.document_id != revision.document_id
        or target.scene_revision_id != revision.revision_id
        or target.scene_content_hash != revision.content_hash
        or target.system_variant_id != expected_variant_id
        or target.system_variant_sha256 != expected_variant_sha256
        or target.evaluated_scene_content_hash != effective_hash
    ):
        raise ValueError('video geometry evaluation authority does not match installation target')
    request = evaluation.request
    if (
        request.projector_specification_id != specification.specification_id
        or request.projector_specification_version != specification.version
        or request.projector_specification_sha256 != specification.specification_sha256
        or evaluation.projector_specification_sha256 != specification.specification_sha256
    ):
        raise ValueError('ProjectorSpecification/VideoGeometryEvaluation binding mismatch')

    projector_entity = document.entity(request.projector_entity_id)
    if projector_entity.kind != 'projector':
        raise ValueError('video geometry projector binding is not a projector entity')
    screen_entity = document.entity(request.screen.entity_id)
    if screen_entity.kind != 'screen':
        raise ValueError('video geometry screen binding is not a screen entity')

    horizontal_range = (
        None
        if specification.horizontal_lens_shift is None
        else (
            float(specification.horizontal_lens_shift.minimum_fraction),
            float(specification.horizontal_lens_shift.maximum_fraction),
        )
    )
    vertical_range = (
        None
        if specification.vertical_lens_shift is None
        else (
            float(specification.vertical_lens_shift.minimum_fraction),
            float(specification.vertical_lens_shift.maximum_fraction),
        )
    )
    return InstallationProjectorSummary(
        status='AVAILABLE',
        specification_id=specification.specification_id,
        specification_version=specification.version,
        specification_sha256=specification.specification_sha256,
        projector_entity_id=request.projector_entity_id,
        lens_reference_offset_m=(
            float(specification.lens_reference_offset_m.x_m),
            float(specification.lens_reference_offset_m.y_m),
            float(specification.lens_reference_offset_m.z_m),
        ),
        lens_position_m=_xyz_position(evaluation.projection.lens_position),
        optical_axis_local=_xyz_direction(specification.optical_axis_local),
        throw_ratio_min=float(specification.throw_ratio_min),
        throw_ratio_max=float(specification.throw_ratio_max),
        evaluated_throw_ratio=float(evaluation.projection.throw_ratio),
        zoom_position=(
            None
            if evaluation.projection.required_zoom_fraction is None
            else float(evaluation.projection.required_zoom_fraction)
        ),
        horizontal_lens_shift_range=horizontal_range,
        vertical_lens_shift_range=vertical_range,
        required_horizontal_lens_shift_fraction=(
            None
            if evaluation.projection.required_horizontal_lens_shift_fraction is None
            else float(evaluation.projection.required_horizontal_lens_shift_fraction)
        ),
        required_vertical_lens_shift_fraction=(
            None
            if evaluation.projection.required_vertical_lens_shift_fraction is None
            else float(evaluation.projection.required_vertical_lens_shift_fraction)
        ),
        image_plane_corners_m=tuple(
            _xyz_position(item) for item in evaluation.projection.image_plane_corners
        ),
        projection_cone_directions=tuple(
            _xyz_direction(item) for item in evaluation.projection.projection_cone_directions
        ),
        supported_aspect_ratios=tuple(
            f'{item.width_units}:{item.height_units}'
            for item in specification.supported_aspect_ratios
        ),
        image_aspect_ratio=float(
            request.screen.visible_width_m / request.screen.visible_height_m
        ),
        screen_entity_id=request.screen.entity_id,
        screen_visible_width_m=float(request.screen.visible_width_m),
        screen_visible_height_m=float(request.screen.visible_height_m),
        screen_frame_clearance_m=float(request.screen.frame_clearance_m),
        video_geometry_evaluation_id=evaluation.evaluation_id,
        video_geometry_evaluation_sha256=evaluation.evaluation_sha256,
        projection_status=evaluation.projection.status,
        geometry_status=evaluation.geometry_status,
        sightlines=tuple(
            InstallationSightlineSummary(
                seat_entity_id=item.seat_entity_id,
                row_id=item.row_id,
                status=item.status,
                blocking_seat_ids=item.blocking_seat_ids,
                blocking_row_ids=item.blocking_row_ids,
                blocked_sample_ids=item.blocked_sample_ids,
                minimum_head_ray_clearance_m=item.minimum_head_ray_clearance_m,
            )
            for item in evaluation.sightlines
        ),
        collisions=tuple(
            InstallationCollisionSummary(
                entity_a=item.entity_a,
                entity_b=item.entity_b,
                status=item.status,
                intersects_or_violates_clearance=item.intersects_or_violates_clearance,
            )
            for item in evaluation.collisions
        ),
        screen_acoustic_effect_status=evaluation.screen_acoustic_effect_status,
        screen_acoustic_effect_reason=evaluation.screen_acoustic_effect_reason,
    )


def _standards_summary(
    *,
    revision: SceneRevision,
    variant: SystemVariant | None,
    document: SceneDocument,
    profile: StandardsProfile | None,
    evaluation: StandardsEvaluation | None,
) -> InstallationStandardsSummary:
    if profile is None and evaluation is None:
        return InstallationStandardsSummary(status='UNKNOWN')
    if profile is None or evaluation is None:
        raise ValueError('StandardsProfile and StandardsEvaluation must be supplied together')
    if (
        evaluation.profile_id != profile.profile_id
        or evaluation.profile_version != profile.version
        or evaluation.profile_semantic_hash != profile.profile_semantic_hash
    ):
        raise ValueError('StandardsProfile/StandardsEvaluation binding mismatch')

    target = evaluation.target
    expected_variant_id = None if variant is None else variant.variant_id
    expected_variant_sha256 = None if variant is None else variant.variant_sha256
    if (
        target.document_id != revision.document_id
        or target.scene_revision_id != revision.revision_id
        or target.scene_content_hash != revision.content_hash
        or target.system_variant_id != expected_variant_id
        or target.system_variant_sha256 != expected_variant_sha256
    ):
        raise ValueError('StandardsEvaluation authority does not match installation target')
    entity_ids = {entity.entity_id for entity in document.entities}
    if not set(target.entity_ids).issubset(entity_ids):
        raise ValueError('StandardsEvaluation target references entities outside installation target')

    criteria_by_id = {item.criterion_id: item for item in profile.criteria}
    result_ids = {item.criterion_id for item in evaluation.results}
    if result_ids != set(criteria_by_id):
        raise ValueError('StandardsEvaluation criterion set does not match StandardsProfile')
    rows = []
    for result in evaluation.results:
        criterion = criteria_by_id[result.criterion_id]
        if result.criterion_sha256 != _semantic_digest(criterion.model_dump(mode='json')):
            raise ValueError('StandardsEvaluation criterion hash does not match StandardsProfile')
        source = criterion.source
        rows.append(InstallationStandardsCriterionSummary(
            criterion_id=result.criterion_id,
            status=result.status,
            observed_value=result.observed_value,
            unit=result.unit,
            target_entity_ids=result.entity_ids,
            reason_code=result.reason_code,
            source_publisher=source.publisher,
            source_document_title=source.document_title,
            source_document_version=source.document_version,
            source_reference=source.reference,
            source_uri=source.source_uri,
            evidence_refs=tuple(
                (item.evidence_id, item.evidence_sha256, item.detail)
                for item in result.evidence_refs
            ),
        ))
    return InstallationStandardsSummary(
        status='AVAILABLE',
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_semantic_hash=profile.profile_semantic_hash,
        evaluation_id=evaluation.evaluation_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        criteria=tuple(rows),
    )


def _installation_sections(
    *,
    projector: InstallationProjectorSummary,
    standards: InstallationStandardsSummary,
) -> tuple[InstallationSectionStatus, ...]:
    return (
        InstallationSectionStatus(
            section='projector_coordinates',
            status=projector.status,
            reason=(
                'exact ProjectorSpecification and VideoGeometryEvaluation are bound'
                if projector.status == 'AVAILABLE'
                else 'no exact projector/video geometry authority is bound'
            ),
        ),
        InstallationSectionStatus(
            section='standards_profile',
            status=standards.status,
            reason=(
                'exact StandardsProfile and StandardsEvaluation are bound'
                if standards.status == 'AVAILABLE'
                else 'no exact StandardsProfile/StandardsEvaluation authority is bound'
            ),
        ),
        InstallationSectionStatus(
            section='calibration_plan',
            status='UNKNOWN',
            reason='CalibrationPlan integration is deferred from this InstallationOutput slice',
        ),
        InstallationSectionStatus(
            section='treatment_plan',
            status='UNKNOWN',
            reason='AcousticTreatment integration is deferred from this InstallationOutput slice',
        ),
    )


def build_installation_output(
    revision: SceneRevision,
    *,
    variant: SystemVariant | None = None,
    evidence: Sequence[InstallationEvidenceRef] = (),
    projector_specification: ProjectorSpecification | None = None,
    video_geometry_evaluation: VideoGeometryEvaluation | None = None,
    standards_profile: StandardsProfile | None = None,
    standards_evaluation: StandardsEvaluation | None = None,
) -> InstallationOutput:
    """Derive one semantic installation snapshot without creating editable truth."""

    if scene_content_hash(revision.document) != revision.content_hash:
        raise ValueError('SceneRevision content hash does not match its document')
    document = revision.document if variant is None else materialize_system_variant(revision, variant)
    effective_hash = scene_content_hash(document)

    projector = _projector_summary(
        revision=revision,
        variant=variant,
        document=document,
        effective_hash=effective_hash,
        specification=projector_specification,
        evaluation=video_geometry_evaluation,
    )
    standards = _standards_summary(
        revision=revision,
        variant=variant,
        document=document,
        profile=standards_profile,
        evaluation=standards_evaluation,
    )

    supported_kinds = {'speaker', 'seat', 'screen', 'projector', 'measurement_point'}
    rows = tuple(
        sorted(
            (
                _installation_entity(entity)
                for entity in document.entities
                if str(entity.kind) in supported_kinds
            ),
            key=lambda item: (item.entity_kind, item.entity_id),
        )
    )

    evidence_items = list(evidence)
    if variant is not None:
        evidence_items.extend(
            InstallationEvidenceRef(
                authority='system_variant.proposal_evidence',
                evidence_id=item.evidence_id,
                evidence_sha256=item.evidence_sha256,
                evidence_type=item.evidence_kind,
            )
            for item in variant.proposal_evidence
        )
    evidence_rows = tuple(sorted(
        evidence_items,
        key=lambda item: (item.authority, item.evidence_id, item.evidence_sha256 or ''),
    ))

    authority = InstallationAuthorityBinding(
        document_id=revision.document_id,
        scene_revision_id=revision.revision_id,
        scene_content_hash=revision.content_hash,
        effective_scene_content_hash=effective_hash,
        system_variant_id=None if variant is None else variant.variant_id,
        system_variant_sha256=None if variant is None else variant.variant_sha256,
    )
    dimensions = _dimension_sheets(document, rows)
    sections = _installation_sections(projector=projector, standards=standards)
    identity = {
        'schema_version': INSTALLATION_OUTPUT_SCHEMA_VERSION,
        'authority_version': INSTALLATION_OUTPUT_AUTHORITY_VERSION,
        'coordinate_system': document.coordinate_system,
        'authority': authority.model_dump(mode='json'),
        'evidence': [item.model_dump(mode='json') for item in evidence_rows],
        'entities': [item.model_dump(mode='json') for item in rows],
        'dimensions': [item.model_dump(mode='json') for item in dimensions],
        'sections': [item.model_dump(mode='json') for item in sections],
        'projector': projector.model_dump(mode='json'),
        'standards': standards.model_dump(mode='json'),
    }
    return InstallationOutput(
        coordinate_system=document.coordinate_system,
        authority=authority,
        evidence=evidence_rows,
        entities=rows,
        dimensions=dimensions,
        sections=sections,
        projector=projector,
        standards=standards,
        semantic_sha256=_semantic_digest(identity),
    )


def _csv_number(value: float | None) -> str:
    return '' if value is None else format(float(value), '.12g')


def render_installation_csv(output: InstallationOutput) -> str:
    """Render deterministic installation coordinates; no generation timestamp is included."""

    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow((
        'entity_id', 'entity_kind', 'name', 'speaker_role',
        'x_m', 'y_m', 'z_m',
        'body_yaw_deg', 'body_pitch_deg', 'body_roll_deg',
        'mounting_height_m', 'mounting_height_reference',
        'aim_x', 'aim_y', 'aim_z',
        'scene_revision_id', 'scene_content_hash',
        'system_variant_id', 'system_variant_sha256',
        'semantic_sha256',
    ))
    for item in output.entities:
        aim = item.aim_xyz or (None, None, None)
        writer.writerow((
            item.entity_id,
            item.entity_kind,
            item.name,
            item.speaker_role or '',
            _csv_number(item.x_m),
            _csv_number(item.y_m),
            _csv_number(item.z_m),
            _csv_number(item.body_yaw_deg),
            _csv_number(item.body_pitch_deg),
            _csv_number(item.body_roll_deg),
            _csv_number(item.mounting_height_m),
            item.mounting_height_reference or '',
            _csv_number(aim[0]),
            _csv_number(aim[1]),
            _csv_number(aim[2]),
            output.authority.scene_revision_id,
            output.authority.scene_content_hash,
            output.authority.system_variant_id or '',
            output.authority.system_variant_sha256 or '',
            output.semantic_sha256,
        ))
    if output.schema_version >= 2:
        writer.writerow(())
        writer.writerow(('authority_record', 'authority', 'payload_json'))
        writer.writerow((
            'authority_record',
            'projector',
            _canonical(
                None if output.projector is None
                else output.projector.model_dump(mode='json')
            ),
        ))
        writer.writerow((
            'authority_record',
            'standards',
            _canonical(
                None if output.standards is None
                else output.standards.model_dump(mode='json')
            ),
        ))
    return stream.getvalue()


def _projector_report_block(summary: InstallationProjectorSummary | None) -> str:
    if summary is None or summary.status == 'UNKNOWN':
        return '<section><h2>Projector / video geometry</h2><p>UNKNOWN — no exact projector/video authority is bound.</p></section>'
    sightlines = ''.join(
        '<tr>'
        f'<td><code>{escape(item.seat_entity_id)}</code></td>'
        f'<td>{escape(item.row_id)}</td><td>{escape(item.status)}</td>'
        f'<td>{escape(", ".join(item.blocking_seat_ids) or "—")}</td>'
        f'<td>{_metric(item.minimum_head_ray_clearance_m)}</td>'
        '</tr>'
        for item in summary.sightlines
    ) or '<tr><td colspan="5">None</td></tr>'
    collisions = ''.join(
        '<tr>'
        f'<td><code>{escape(item.entity_a)}</code></td>'
        f'<td><code>{escape(item.entity_b)}</code></td>'
        f'<td>{escape(item.status)}</td>'
        f'<td>{escape(str(item.intersects_or_violates_clearance))}</td>'
        '</tr>'
        for item in summary.collisions
    ) or '<tr><td colspan="4">None</td></tr>'
    return (
        '<section><h2>Projector / video geometry</h2>'
        f'<p>ProjectorSpecification: <code>{escape(summary.specification_id or "UNKNOWN")}</code> '
        f'v{escape(summary.specification_version or "UNKNOWN")} / '
        f'<code>{escape(summary.specification_sha256 or "UNKNOWN")}</code></p>'
        f'<p>Projector entity: <code>{escape(summary.projector_entity_id or "UNKNOWN")}</code> · '
        f'VideoGeometryEvaluation: <code>{escape(summary.video_geometry_evaluation_id or "UNKNOWN")}</code> / '
        f'<code>{escape(summary.video_geometry_evaluation_sha256 or "UNKNOWN")}</code></p>'
        f'<p>Lens world position: {escape(str(summary.lens_position_m or "UNKNOWN"))} · '
        f'optical axis local: {escape(str(summary.optical_axis_local or "UNKNOWN"))}</p>'
        f'<p>Throw ratio: {_metric(summary.evaluated_throw_ratio)} '
        f'(spec {_metric(summary.throw_ratio_min)}…{_metric(summary.throw_ratio_max)}) · '
        f'zoom position: {_metric(summary.zoom_position)} · '
        f'lens shift H/V: {_metric(summary.required_horizontal_lens_shift_fraction)} / '
        f'{_metric(summary.required_vertical_lens_shift_fraction)}</p>'
        f'<p>Screen: <code>{escape(summary.screen_entity_id or "UNKNOWN")}</code> · '
        f'visible {_metric(summary.screen_visible_width_m)} × {_metric(summary.screen_visible_height_m)} m · '
        f'frame clearance {_metric(summary.screen_frame_clearance_m)} m · '
        f'aspect {_metric(summary.image_aspect_ratio)}</p>'
        f'<p>Projection status: {escape(summary.projection_status or "UNKNOWN")} · '
        f'geometry status: {escape(summary.geometry_status or "UNKNOWN")} · '
        f'acoustic screen effect: {escape(summary.screen_acoustic_effect_status or "UNKNOWN")}</p>'
        '<h3>Sightline / obstruction</h3><table><thead><tr>'
        '<th>Seat</th><th>Row</th><th>Status</th><th>Blocking seats</th><th>Min clearance (m)</th>'
        f'</tr></thead><tbody>{sightlines}</tbody></table>'
        '<h3>Collision / clearance</h3><table><thead><tr>'
        '<th>A</th><th>B</th><th>Status</th><th>Intersects/violates clearance</th>'
        f'</tr></thead><tbody>{collisions}</tbody></table>'
        '<details><summary>Exact projector authority summary</summary><pre>'
        f'{escape(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2))}'
        '</pre></details></section>'
    )


def _standards_report_block(summary: InstallationStandardsSummary | None) -> str:
    if summary is None or summary.status == 'UNKNOWN':
        return '<section><h2>Standards evaluation</h2><p>UNKNOWN — no exact StandardsProfile/StandardsEvaluation authority is bound.</p></section>'
    rows = ''.join(
        '<tr>'
        f'<td><code>{escape(item.criterion_id)}</code></td>'
        f'<td>{escape(item.status)}</td>'
        f'<td>{escape(str(item.observed_value) if item.observed_value is not None else "UNKNOWN")}</td>'
        f'<td>{escape(item.unit or "UNKNOWN")}</td>'
        f'<td>{escape(", ".join(item.target_entity_ids) or "—")}</td>'
        f'<td>{escape(item.source_publisher)} — {escape(item.source_document_title)} '
        f'{escape(item.source_document_version)} § {escape(item.source_reference)}</td>'
        '</tr>'
        for item in summary.criteria
    ) or '<tr><td colspan="6">No criteria</td></tr>'
    return (
        '<section><h2>Standards evaluation</h2>'
        f'<p>StandardsProfile: <code>{escape(summary.profile_id or "UNKNOWN")}</code> '
        f'v{escape(summary.profile_version or "UNKNOWN")} / '
        f'<code>{escape(summary.profile_semantic_hash or "UNKNOWN")}</code></p>'
        f'<p>StandardsEvaluation: <code>{escape(summary.evaluation_id or "UNKNOWN")}</code> / '
        f'<code>{escape(summary.evaluation_sha256 or "UNKNOWN")}</code></p>'
        '<p class="muted">Criterion truth is reported directly; no aggregate compliance score or hard-constraint policy is inferred.</p>'
        '<table><thead><tr><th>Criterion</th><th>Status</th><th>Observed</th><th>Unit</th>'
        f'<th>Target entities</th><th>Source/reference</th></tr></thead><tbody>{rows}</tbody></table>'
        '<details><summary>Exact standards authority summary</summary><pre>'
        f'{escape(json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2))}'
        '</pre></details></section>'
    )


def render_installation_report_html(
    output: InstallationOutput,
    *,
    exported_at_utc: str | None = None,
) -> str:
    """Render a self-contained human report over an immutable InstallationOutput."""

    exported_at = exported_at_utc or datetime.now(timezone.utc).isoformat()
    authority = output.authority
    variant_text = (
        'none'
        if authority.system_variant_id is None
        else f'{authority.system_variant_id} / {authority.system_variant_sha256}'
    )
    entity_rows = ''.join(
        '<tr>'
        f'<td><code>{escape(item.entity_id)}</code></td>'
        f'<td>{escape(item.entity_kind)}</td>'
        f'<td>{escape(item.speaker_role or "—")}</td>'
        f'<td>{_metric(item.x_m)}</td><td>{_metric(item.y_m)}</td><td>{_metric(item.z_m)}</td>'
        f'<td>{_metric(item.body_yaw_deg)}</td><td>{_metric(item.body_pitch_deg)}</td>'
        f'<td>{_metric(item.mounting_height_m)}</td>'
        '</tr>'
        for item in output.entities
    ) or '<tr><td colspan="9">No installation-coordinate entities in this authority.</td></tr>'
    section_rows = ''.join(
        '<tr>'
        f'<td>{escape(item.section)}</td><td>{escape(item.status)}</td><td>{escape(item.reason)}</td>'
        '</tr>'
        for item in output.sections
    )
    dimension_blocks = ''.join(
        '<section>'
        f'<h2>{escape(sheet.view.title())} dimensions</h2>'
        f'<p class="muted">Axes: {escape(sheet.horizontal_axis)} / {escape(sheet.vertical_axis)} · '
        f'bounds {sheet.horizontal_min_m:.3f}…{sheet.horizontal_max_m:.3f} m × '
        f'{sheet.vertical_min_m:.3f}…{sheet.vertical_max_m:.3f} m</p>'
        '<table><thead><tr><th>Entity</th><th>Kind</th><th>Horizontal (m)</th><th>Vertical (m)</th></tr></thead><tbody>'
        + ''.join(
            '<tr>'
            f'<td><code>{escape(point.entity_id)}</code></td>'
            f'<td>{escape(point.entity_kind)}</td>'
            f'<td>{_metric(point.horizontal_m)}</td><td>{_metric(point.vertical_m)}</td>'
            '</tr>'
            for point in sheet.points
        )
        + '</tbody></table></section>'
        for sheet in output.dimensions
    )
    projector_block = _projector_report_block(output.projector)
    standards_block = _standards_report_block(output.standards)
    semantic_json = json.dumps(output.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HTDT installation {escape(authority.scene_revision_id)}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f6f8;color:#1e242b}}main{{max-width:1100px;margin:auto;padding:32px}}
section{{background:white;border:1px solid #d9dde3;border-radius:10px;padding:20px;margin:16px 0}}h1,h2{{margin-top:0}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #e4e7eb;padding:8px;text-align:left;vertical-align:top}}code{{font-size:.9em}}.muted{{color:#606a75}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
</style></head><body><main>
<h1>Home Theater Digital Twin — Installation Report</h1>
<p class="muted">Exported {escape(exported_at)} · generation metadata is not part of semantic identity.</p>
<section><h2>Authority</h2>
<p>Document: <code>{escape(authority.document_id)}</code></p>
<p>SceneRevision: <code>{escape(authority.scene_revision_id)}</code> / <code>{escape(authority.scene_content_hash)}</code></p>
<p>SystemVariant: <code>{escape(variant_text)}</code></p>
<p>Effective scene hash: <code>{escape(authority.effective_scene_content_hash)}</code></p>
<p>Installation semantic hash: <code>{escape(output.semantic_sha256)}</code></p></section>
<section><h2>Installation coordinates</h2><table><thead><tr>
<th>Entity</th><th>Kind</th><th>Role</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th><th>Body yaw (°)</th><th>Body pitch (°)</th><th>Mount height (m)</th>
</tr></thead><tbody>{entity_rows}</tbody></table>
<p class="muted">Speaker mounting height is the exact Scene entity-origin Z coordinate; no separate bracket/mount reference is inferred.</p></section>
{dimension_blocks}
{projector_block}
{standards_block}
<section><h2>Section availability</h2><table><thead><tr><th>Section</th><th>Status</th><th>Reason</th></tr></thead><tbody>{section_rows}</tbody></table></section>
<section><h2>Machine-readable semantic snapshot</h2><p class="muted">This embedded JSON excludes exported_at and other generation metadata.</p><details><summary>Show JSON</summary><pre>{escape(json.dumps(output.model_dump(mode='json'), ensure_ascii=False, indent=2))}</pre></details></section>
<script type="application/json" id="htdt-installation-output">{semantic_json}</script>
</main></body></html>'''
