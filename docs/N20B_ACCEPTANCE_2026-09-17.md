# N20b A07 acceptance — 2026-09-17

Status: **functional pass / performance work remains**

Branch: `feat/n20b-multiselect-snap`

## Environment

- Windows 11 x64, owned PC
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- Physical display: 2880×1800
- OS scaling: 200%
- Python 3.12.10 with the repository's pinned N05/N20 dependencies
- Fixture: F1 for functional checks; F4-equivalent load for performance checks

## Functional A07 results

The following were exercised through the actual Qt/VTK renderer and Windows input path:

- vertex, edge, midpoint and alignment snap candidates are all reachable;
- screen-space snap uses 8 DIP acquire / 12 DIP retain hysteresis;
- Ctrl-click creates a two-entity ordered selection with a primary entity;
- group Move uses one common world-axis delta and preserves relative placement;
- a group Move snapped to an FR vertex and committed as one history command;
- group Rotate uses the common selection pivot and commits as one history command;
- 15° angle snap produced a -45° actual mouse rotation in the acceptance path;
- Undo restores the complete group atomically;
- unknown speaker aim remains unknown through group transforms;
- object transforms do not move the camera;
- numeric multi-selection Move uses the same domain validation/command path;
- W/R shortcuts do not fire while a numeric editor owns keyboard focus.

## DPI checks

The screen-distance selector was checked at Qt scale factors corresponding to DPR 1.0, 1.5 and 2.0. A 7 DIP probe acquired the candidate and a 10 DIP probe retained the same candidate at all three scales. This verifies that geometric tolerance is not being confused with physical/device pixels.

## Input conflict found during acceptance

A real rotation-ring press exposed a scene-picking conflict: the underlying already-selected entity could also be picked on the same press, reducing a multi-selection to one entity and rebuilding the gizmo. The intended CAD behavior is that re-picking an entity already in the current selection without Ctrl does not destroy the group merely because the press landed on a transform handle. This remains a required source fix before N20b is closed.

The translation hit target was also marginal under high-DPI cursor rounding in the F4 camera condition. Commit `d96a89b` widens the translation arrow shaft/tip hit geometry without changing transform semantics.

## F4 performance measurements

Test load: F1 plus 50 editable objects and 1,000 analysis markers represented as one point-cloud actor, not 1,000 actors.

Observed during investigation:

- OS input to corresponding selection render: approximately 127–140 ms p95 in the current harness, above the initial 100 ms target;
- direct selection/update path without OS event dispatch: approximately 52 ms p95;
- direct selection plus synchronous ViewState persistence: approximately 63 ms p95.

The acceptance specification explicitly distinguishes render/app timing from strict OS-to-screen latency. The current figures are therefore recorded separately rather than relabeling the target as passed. F4 drag/orbit 30-second frame-time acceptance remains pending after the translation hit-target change.

## Current conclusion

A07 functional semantics are validated, including multi-selection, snap stability, rigid group transforms, numeric editing and DPI behavior. N20b remains open until the scene-pick/transform-handle conflict is fixed in the GitHub source, F4 drag performance is remeasured, backend regression/CI pass, and the final branch is merged.
