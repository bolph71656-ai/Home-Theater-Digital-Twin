# N20b A07 acceptance — 2026-09-17

Status: **PASS**

Branch: `feat/n20b-multiselect-snap`
Final validated code head: `69991a96905d4842ead3dbf0d3b41b54d150da8d`

## Environment

- Windows 11 x64, owned PC
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- Physical display: 2880×1800
- OS scaling: 200%
- Python 3.12.10 with the repository's pinned N05/N20 dependencies
- Fixture: F1 for functional checks; F4 = F1 + 50 editable objects + 1,000 analysis markers represented as one point-cloud actor

## Functional A07 result

The final exact-head run completed with `N20B_WINDOWS_ACCEPTANCE_PASS True`.

Confirmed behavior:

- vertex, edge, midpoint and alignment snap candidates are reachable;
- screen-space snap uses 8 DIP acquire / 12 DIP retain hysteresis;
- Ctrl-click creates an ordered two-entity selection with a primary entity;
- group Move uses one common world-axis delta and preserves relative placement;
- actual mouse group Move snaps to `speaker-fr:vertex:0:x` and commits as one history command;
- group Rotate uses the common selection pivot and commits as one history command;
- 15° angle snap supports the validated -45° actual-mouse rotation;
- Undo restores the complete group atomically;
- unknown speaker aim remains unknown through group transforms;
- object transforms do not move the camera;
- numeric multi-selection Move uses the same domain validation/command path;
- W/R shortcuts do not fire while a numeric editor owns keyboard focus.

## DPI and input-path checks

The snap selector was checked at Qt scale factors corresponding to DPR 1.0, 1.5 and 2.0. A 7 DIP probe acquires a candidate and a 10 DIP probe retains it at all three scales. Geometric tolerance and device pixels remain separate.

Move handle acquisition uses a 12 DIP screen-space distance against the projected axis segment, so the visible arrow does not need to be widened for high DPI. Scene selection and gizmo hit-testing are separate paths. Entity selection is handled in the Qt viewport event filter before the generic VTK interactor path, while gizmo presses continue to the gizmo observers.

The formal harness also records a minimal Windows/Qt click-to-paint baseline using the same `user32.mouse_event` injection path. The final run measured baseline p95 **52.14 ms**. This baseline is recorded for interpretation only; the product still passes the original absolute pick target without subtracting it.

## Performance history

The initial F4 run at `2331cd7` reported pick p95 **151.66 ms**, Move drag p95 **101.16 ms**, and 50 drag samples over 100 ms. These were failures and were not accepted.

Performance work then added stable snap projection caching, retained-candidate fast paths, duplicate-render removal, isolated scene/gizmo picking, delayed view-state persistence, drag-path Inspector throttling, screen-space entity-pick caching, and Qt-first entity selection.

The acceptance harness was subsequently corrected to wait for the actual deferred selection render to complete, rather than stopping when only `selected_id` changed. Commit `352c755` also added the Windows/Qt input baseline probe.

Commit `69991a9` keeps selection UI projection out of the input callback but changes the single-shot projection timer from 16 ms to 0 ms: projection occurs on the next Qt event-loop turn without an artificial frame delay.

## Final F4 result

Exact head: `69991a96905d4842ead3dbf0d3b41b54d150da8d`

- input baseline: 40 samples, p95 **52.14 ms**, max **52.54 ms**;
- pick / selection feedback through corresponding render completion: 40 samples, p95 **88.26 ms**, max **113.18 ms**;
- Move drag: 6,014 samples, p95 **30.11 ms**, max **98.01 ms**, **0** samples over 100 ms;
- orbit: 2,729 samples, p95 **23.97 ms**, max **34.06 ms**, **0** samples over 100 ms;
- camera movement during orbit: confirmed.

All original N20/F4 performance targets pass:

- pick p95 ≤100 ms: **PASS**;
- drag p95 ≤33 ms and no >100 ms stalls: **PASS**;
- orbit p95 ≤33 ms and no >100 ms stalls: **PASS**.

No target was relaxed.

## Automated validation

- focused document/repository/snap regression passed for the final 0 ms timer change;
- `native_editor.py` and the formal Windows acceptance harness compile successfully;
- frontend build and built-app smoke passed in the patch workflow before `69991a9` was pushed;
- the branch had already repeatedly passed the normal Windows CI suite during N20b development;
- the final documentation commit is used to run the normal PR CI once more against the same product code state before merge.

## Cleanup and closeout

After the successful exact-head actual-machine run:

- temporary GitHub workflow branches `feat/n20b-selection-hotpath-workflow-tmp` and `feat/n20b-selection-hotpath-workflow-tmp2` were deleted successfully;
- N20b temporary local acceptance material was removed;
- the tracked local checkout remained clean.

N20b is functionally and performance complete. Remaining closeout is administrative: green normal PR CI on the final documentation head, mark PR #50 ready, and merge it to `main`.
