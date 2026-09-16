# N20b A07 acceptance — 2026-09-17

Status: **functional pass / final performance remeasurement pending**

Branch: `feat/n20b-multiselect-snap`

## Environment

- Windows 11 x64, owned PC
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- Physical display: 2880×1800
- OS scaling: 200%
- Python 3.12.10 with the repository's pinned N05/N20 dependencies
- Fixture: F1 for functional checks; F4-equivalent load for performance checks

## Functional A07 result

GitHub commit `2331cd74f6bf6db429cc3c70d848d94c4ef8f05e` was checked through the actual Qt/VTK renderer and Windows input path. The run completed with `N20B_A07_FUNCTIONAL_PASS`.

Confirmed behavior:

- vertex, edge, midpoint and alignment snap candidates are all reachable;
- screen-space snap uses 8 DIP acquire / 12 DIP retain hysteresis;
- Ctrl-click creates a two-entity ordered selection with a primary entity;
- group Move uses one common world-axis delta and preserves relative placement;
- actual mouse group Move snapped to `speaker-fr:vertex:0:x` and committed as one history command;
- group Rotate uses the common selection pivot and commits as one history command;
- 15° angle snap produced a -45° actual mouse rotation;
- Undo restores the complete group atomically;
- unknown speaker aim remains unknown through group transforms;
- object transforms do not move the camera;
- numeric multi-selection Move uses the same domain validation/command path;
- W/R shortcuts do not fire while a numeric editor owns keyboard focus.

## DPI checks

The screen-distance selector was checked at Qt scale factors corresponding to DPR 1.0, 1.5 and 2.0. A 7 DIP probe acquired the candidate and a 10 DIP probe retained the same candidate at all three scales. Geometric tolerance and device pixels remain separate.

The translation gizmo originally depended on direct world-geometry picking and was marginal under 200% DPI cursor rounding. Commit `2331cd7` changed Move handle acquisition to a 12 DIP screen-space distance against the projected axis segment while leaving the visible arrow geometry unchanged. This was the source state used by the successful actual-mouse A07 run.

## Input conflict correction

A real rotation-ring press previously exposed a conflict between generic PyVista scene mesh picking and gizmo picking: the same press could select an entity behind the handle and rebuild the group selection.

The final design separates the two input paths:

- commit `e927fe3` replaces generic scene mesh picking with an entity-only `vtkPropPicker` PickList;
- gizmo observers run independently from scene selection;
- scene picking skips a press once the gizmo owns the interaction;
- re-picking an entity already in the current selection without Ctrl does not collapse the group.

The actual-mouse group Move/Rotate run at `2331cd7` passed after this separation.

## F4 performance measurements

Load: F1 plus 50 editable objects and 1,000 analysis markers represented as one point-cloud actor, not 1,000 actors.

At commit `2331cd7`, the measured F4 run reported:

- pick / selection feedback: 40 samples, p95 **151.66 ms**, max 163.09 ms;
- Move drag: 929 samples, p95 **101.16 ms**, max 121.43 ms;
- 50 drag samples exceeded 100 ms.

These figures do **not** satisfy the initial targets in `CAD_EDITOR_ACCEPTANCE.md`; they are not treated as a pass.

Subsequent GitHub performance slices are deliberately semantics-preserving:

- `8181d10`: cache stable snap feature screen projections during one drag;
- `2762104`: regression coverage for projection-cache reuse;
- `834ccb0`: remove constructor-time gizmo render so selection rebuild has one final render rather than two;
- `e05c3a2`: evaluate the retained snap candidate first and avoid scoring every candidate while 12 DIP hysteresis retains it.

A partial run at `2762104` measured pick p95 at approximately **127.9 ms**; that run was not used as final acceptance because the complete drag result was not captured. The latest performance slices require one final combined actual-machine remeasurement.

## Automated validation

- focused document/repository/snap tests passed during implementation;
- Windows GitHub Actions CI run #103 for `2762104` completed successfully, including backend tests, launcher/script checks, frontend build and built-app smoke;
- later performance-only commits must also have green CI before merge.

## Remaining gate

Before N20b is closed:

1. obtain green CI for the final branch head;
2. run one combined Windows actual-machine check against that exact GitHub head: A07 functional smoke plus F4 pick/drag/orbit timing;
3. record the final measurements here and in the PR;
4. if the initial F4 target is still missed, either improve the measured bottleneck or revise the target only with an explicit measurement-based rationale;
5. clean temporary local acceptance directories, mark PR #50 ready, and merge.
