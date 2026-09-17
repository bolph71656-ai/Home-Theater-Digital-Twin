# N20b A07 acceptance — 2026-09-17

Status: **functional pass / F4 pick final gate pending**

Branch: `feat/n20b-multiselect-snap`

## Environment

- Windows 11 x64, owned PC
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- Physical display: 2880×1800
- OS scaling: 200%
- Python 3.12.10 with the repository's pinned N05/N20 dependencies
- Fixture: F1 for functional checks; F4-equivalent load for performance checks

## Functional A07 result

Actual Qt/VTK renderer and Windows input runs have repeatedly passed the A07 functional gate through the current performance work.

Confirmed behavior:

- vertex, edge, midpoint and alignment snap candidates are all reachable;
- screen-space snap uses 8 DIP acquire / 12 DIP retain hysteresis;
- Ctrl-click creates a two-entity ordered selection with a primary entity;
- group Move uses one common world-axis delta and preserves relative placement;
- actual mouse group Move snaps to `speaker-fr:vertex:0:x` and commits as one history command;
- group Rotate uses the common selection pivot and commits as one history command;
- 15° angle snap supports the validated -45° actual-mouse rotation;
- Undo restores the complete group atomically;
- unknown speaker aim remains unknown through group transforms;
- object transforms do not move the camera;
- numeric multi-selection Move uses the same domain validation/command path;
- W/R shortcuts do not fire while a numeric editor owns keyboard focus.

## DPI checks

The screen-distance selector was checked at Qt scale factors corresponding to DPR 1.0, 1.5 and 2.0. A 7 DIP probe acquired the candidate and a 10 DIP probe retained the same candidate at all three scales. Geometric tolerance and device pixels remain separate.

Commit `2331cd7` changed Move handle acquisition to a 12 DIP screen-space distance against the projected axis segment while leaving the visible arrow geometry unchanged. This removed the 200% DPI cursor-rounding weakness of direct world-geometry handle picking.

## Input conflict correction

A real rotation-ring press previously exposed a conflict between generic PyVista scene mesh picking and gizmo picking: the same press could select an entity behind the handle and rebuild the group selection.

The corrected design separates the input paths and preserves the existing multi-selection when a selected entity is re-picked without Ctrl. The successful actual-mouse A07 runs use this separated scene/gizmo path.

## F4 performance measurements

Load: F1 plus 50 editable objects and 1,000 analysis markers represented as one point-cloud actor, not 1,000 actors.

The initial F4 run at `2331cd7` reported:

- pick / selection feedback p95 **151.66 ms**;
- Move drag p95 **101.16 ms**;
- 50 drag samples exceeded 100 ms.

Subsequent semantics-preserving performance work included stable snap projection caching, retained-candidate fast paths, removal of duplicate renders, a dedicated scene picker path, delayed view-state persistence, release recovery, and removal of Inspector work from the drag hot path.

At `76dbb608`, the formal Windows harness reported:

- pick: p95 **122.32 ms**, max 128.44 ms;
- Move drag: p95 **29.52 ms**, max 97.72 ms, **0** samples over 100 ms;
- orbit: p95 **24.77 ms**, max 45.29 ms, **0** samples over 100 ms.

At `b78b889`, selection rendering was consolidated with the delayed gizmo rebuild. The formal harness reported:

- pick: p95 **119.41 ms**;
- Move drag: p95 **33.86 ms**, max 96.47 ms, **0** samples over 100 ms;
- orbit: p95 **25.39 ms**, **0** samples over 100 ms.

At `fe650fb`, scene selection switched to a camera/viewport-keyed screen-space entity bounds/depth cache rather than running VTK geometry picking on every click. The formal harness reported:

- A07 functional: **pass**;
- pick: p95 **112.36 ms**, max 149.15 ms;
- Move drag: p95 **30.38 ms**, max 92.57 ms, **0** samples over 100 ms;
- orbit: p95 **24.67 ms**, max 55.64 ms, **0** samples over 100 ms;
- camera movement during orbit: confirmed.

Therefore drag and orbit satisfy the initial F4 target. The only remaining performance miss is pick p95 versus the **100 ms** target.

Commit `529f21f` moves tree selection projection, edge highlighting, Inspector/action refresh, old-gizmo removal, new-gizmo creation and render to the existing 16 ms deferred selection UI pass. The ordered selection model and `selected_id` are still committed synchronously in the click callback. Focused document/repository/snap regression and `py_compile` passed in GitHub Actions before the commit was pushed. A final actual-machine measurement is still required for this candidate.

## Automated validation

- focused document/repository/snap tests passed during implementation;
- the branch has repeatedly passed the normal Windows CI suite, including backend tests, launcher/script checks, frontend build and built-app smoke;
- CI run #119 passed for `fe650fb`;
- the patch workflow that produced `529f21f` passed its focused regression before pushing the canonical branch;
- the current documentation commit is intended to trigger the normal PR CI against the same code state.

## Remaining gate

Before N20b is closed:

1. obtain green normal CI for the final branch head;
2. run one combined Windows actual-machine check against that exact GitHub head: A07 functional plus F4 pick/drag/orbit timing;
3. require pick p95 ≤100 ms, drag/orbit p95 ≤33 ms, and no >100 ms drag/orbit stalls;
4. record the final measurements here and in PR #50;
5. remove temporary workflow branches/files used only to apply the GitHub-cloud patch, clean N20b local acceptance residue, mark PR #50 ready, and merge.
