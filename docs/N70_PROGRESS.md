# N70 implementation progress

Tracking: Issue #63  
Branch: `feat/n70-prediction-visualization`  
Base main: `86354dd58200738b33ae27261a5308e3551bcbac`

## 2026-09-17 — start

- N60 merged as `f1694eb879a250835efa026ac5dacdec18362788`; Issue #61 closed `completed`.
- Post-merge status/acceptance docs were synchronized on main as `86354dd58200738b33ae27261a5308e3551bcbac`.
- Created Issue #63 and branch `feat/n70-prediction-visualization` from that main head.
- Re-read `IMPLEMENTATION_ROADMAP.md`, `CAD_EDITOR_ACCEPTANCE.md`, `PLACEMENT_OPTIMIZATION_ROADMAP.md`, `DATA_AND_ANALYSIS.md` and existing acoustic code before implementation.
- Confirmed A14 requires non-rectangular rooms to distinguish unsupported vs explicit rectangular approximation; no silent solver substitution is allowed.
- Confirmed F5 is 10,000 analysis markers plus a later 64^3 scalar grid, with measured performance budget rather than a guessed target.

## Existing code finding

`backend/src/htdt/acoustics.py` already contains useful pure geometry algorithms:

- rectangular room modes;
- first-order image-source reflection points/path lengths;
- explicit `predicted_geometry_candidate` classification and assumptions.

The implementation deliberately does not model reflection amplitude/phase, absorption, speaker directivity, modal damping/amplitude, or a spatial SPL field. Therefore N70 must not render these outputs as a validated FR/heatmap.

## N70a implementation decision

First build a native immutable prediction authority and geometry visualization layer:

1. bind each prediction run to exact native SceneRevision/content hash plus model ID/version/parameters;
2. use a native adapter to reuse the existing Qt-free room-mode/reflection geometry;
3. reject non-rectangular rooms for the exact rectangular model;
4. keep any future rectangular approximation explicit and persisted;
5. add prediction-specific stale/cancel tokens rather than changing accepted N60 measurement-job semantics;
6. add `PredictionWorkspaceWindow` over N60 with a `予測` tab and non-pickable overlays;
7. enable heatmap/slice/volume only when a real model result contains a scalar field.

Detailed contract: [N70 design](N70_DESIGN.md).

## Planned focused verification

- native SceneRevision/model/input immutable binding;
- result persistence round-trip;
- exact rectangular-room detection and non-rectangular rejection;
- acoustic-reference source/receiver mapping;
- underlying geometry algorithm outputs preserved without semantic promotion;
- prediction stale/cancel/document-switch guard;
- measured vs predicted UI semantics;
- reflection overlay identity and non-pickability;
- A13/A14 Windows harness compile before real-hardware gate;
- F5 benchmark only when the relevant rendering/storage slice exists.

## External model decision boundary

N70a does not require choosing a new external solver. REW Room Simulator / pyroomacoustics adoption is a later N70b decision boundary and requires S01/S03-equivalent evidence. Until then, the product exposes only what the current validated code actually computes: rectangular geometry candidates, not an SPL field.
