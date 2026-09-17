# N30b progress

Issue: #53  
Branch: `feat/n30b-walls-openings`

## Current state

N30b implementation is complete through the automated/compile gate. A09 Windows real-mouse acceptance is the remaining merge gate.

Completed:
- stable `WallSegment` identity and endpoint references;
- wall-local `WallOpening` model;
- wall-bound `WallConstraintBinding` for N30b clearance-reference continuity;
- one-to-one RoomPrism boundary edge topology validation;
- opening wall-length / room-height validation;
- wall move preserving wall/opening/constraint IDs;
- split with source-wall lineage and deterministic opening/clearance migration;
- split rejection when an opening crosses the split point;
- merge restricted to ordered collinear same-direction walls with matching thickness;
- merge opening offsets and clearance references migrated atomically;
- conservative wall deletion with rejection while affected opening/clearance references remain;
- SceneDocument schema v3 persistence while preserving canonical hashes when `wall_topology` is absent;
- one CommandHistory transaction for room + topology changes;
- revision repository round-trip coverage;
- native wall/opening editor with Japanese-first toolbar, inspector, status messages and room/object labels;
- GUI actions for wall move, split, merge, delete, door opening and clearance binding;
- wall thickness edits preserving openings and clearance bindings;
- normal native launcher switched to `htdt.wall_editor`;
- `scripts/validate_n30b_windows.py` A09 harness using real Windows mouse input for wall select/drag and validating reference continuity, delete rejection/success, and Undo/Redo;
- GitHub Actions forced to UTF-8 so Japanese native CLI help is portable on Windows runners.

## Remaining gate

1. latest PR-head GitHub Actions must be green;
2. run A09 once on the owned Windows machine from a clean checkout of the PR head;
3. record A09 evidence, update implementation status/PR body, then merge PR #54 and close Issue #53.
