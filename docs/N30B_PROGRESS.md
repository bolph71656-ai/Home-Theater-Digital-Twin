# N30b progress

Issue: #53  
Branch: `feat/n30b-walls-openings`

## Current slice

Implemented the standalone wall/opening topology domain and focused invariant tests.

Completed:
- stable `WallSegment` identity and endpoint references;
- wall-local `WallOpening` model;
- one-to-one boundary edge topology validation;
- opening wall-length / room-height validation;
- wall move preserving wall/opening IDs;
- split with source wall lineage and deterministic opening migration;
- split rejection when an opening crosses the split point;
- merge restricted to ordered collinear same-direction walls with matching thickness;
- merge opening offset migration;
- domain design record in `N30B_DESIGN.md`.

Next:
- GitHub Actions validation;
- SceneDocument persistence and canonical compatibility;
- atomic room+topology CommandHistory integration;
- native wall/opening UI and A09 harness.
