from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
import math
from typing import Any


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
