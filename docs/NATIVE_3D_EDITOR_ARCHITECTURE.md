# Native 3D Spatial Editor architecture

> Status: adopted direction, implementation in progress on `feat/native-3d-cad-ui`
> Updated: 2026-09-16

## Decision

HTDT will no longer treat the form-oriented browser UI as the primary long-term interaction model.
The primary GUI will become a Windows-native 3D spatial editor built with:

- Python 3.12
- PySide6
- PyVista
- VTK
- PyVistaQt

The existing FastAPI/React UI remains available as a compatibility and diagnostics surface while the native editor reaches feature parity. It is not the design target for future room/setup editing.

The application should feel closer to a compact CAD/DCC editor than to a settings form: the room, loudspeakers, listening/measurement positions, constraints, search candidates, acoustic overlays, and future prediction fields are objects in one spatial scene.

## Why this stack

HTDT needs more than mechanical CAD geometry. The same viewport must eventually show polygonal room geometry, loudspeaker enclosures and orientation, measurement points, constraint regions, search clouds, reflection paths, frequency-dependent spatial fields, and prediction/measurement overlays.

PyVista/VTK fits that mix better than using an OpenCascade-only CAD viewer as the primary renderer. It natively supports meshes, point clouds, scalar fields, volumes, picking, widgets, clipping/slicing, and scientific visualization, while remaining directly callable from the existing Python analysis layer.

PySide6 supplies a mature desktop application shell, dockable panes, actions, keyboard shortcuts, native Windows input handling, accessibility hooks, and packaging options without introducing a second application runtime.

PyVistaQt embeds the VTK/PyVista renderer in the Qt window. PyVista 0.49's `AffineWidget3D` provides CAD-style axis translation and rotation handles whose transformation matrix can be captured and converted back into HTDT domain coordinates.

## OSS/codebase research used

The following projects were inspected for architecture and interaction patterns. HTDT may reuse APIs and general architectural ideas where licenses permit; substantial source copying is not the plan.

### PyVista

Repository: `pyvista/pyvista`

Useful patterns:

- `AffineWidget3D` for direct translation/rotation handles.
- actor/mesh picking with left-click interaction.
- point/cell/mesh picking for scene selection.
- widgets suitable for room vertices and future planes/slices.
- scalar/volume rendering suitable for later acoustic result overlays.

HTDT should wrap these interactions behind its own scene/domain adapter rather than expose PyVista objects as persisted domain state.

### PyVistaQt

Repository: `pyvista/pyvistaqt`

Use as the Qt/VTK integration layer. Rendering state remains ephemeral; persisted state stays in HTDT Context/Constraint/Search/Prediction records.

### CQ-editor

Repository: `CadQuery/CQ-editor`

The useful reference is its desktop layout rather than its CadQuery scripting model:

- `QMainWindow`
- central 3D viewer
- dockable object tree and inspector/tool panes
- bidirectional selection synchronization between tree and viewport
- CAD camera presets and grid handling

This pattern maps well to HTDT's Scene / Viewport / Inspector arrangement.

### FreeCAD

Repository: `FreeCAD/FreeCAD`

Useful concepts:

- scene/object tree separate from geometry display
- transform draggers/manipulators
- explicit document transactions and undo/redo
- workbench-like separation of editing modes

HTDT will not embed FreeCAD or adopt its full document model. The HTDT domain model remains purpose-built and immutable at saved revision boundaries.

### pyvista-cad

Repository: `pyvista/pyvista-cad`

Optional future interoperability layer for STEP, IGES, BREP, DXF, IFC, FCStd, glTF, and CAD-style topological-edge rendering. It is not required for the first native editor milestone.

### Godot and web 3D alternatives

Godot's editor/plugin ecosystem and 3D gizmo APIs are strong, but using it would add a second runtime and a custom bridge to the Python measurement/analysis stack. Three.js/WebGL can provide good 3D interaction but would retain the browser-centric architecture the redesign is intended to remove. Neither is selected as the primary HTDT editor runtime.

## Domain boundary

The editor must never make renderer state authoritative.

Saved truth remains the existing immutable HTDT records:

- Project
- Context revision
- ConstraintSet
- SearchSpec
- Measurement/Dataset
- later PredictionRun

The native editor operates on an in-memory `ContextDraft` copied from one immutable Context revision. Mouse interaction mutates only that draft. Saving validates the whole draft through the existing Pydantic/Shapely domain contract and creates a new Context revision whose `parent_context_id` is the source revision.

No drag operation mutates an existing saved Context.

## Unknown-value preservation

The existing provenance rule remains mandatory: unknown is not zero/off/false.

Examples:

- Moving a loudspeaker does not invent an `aim_xyz` if aim was previously unknown.
- A speaker's orientation becomes known only after an explicit rotation/orientation edit.
- Renderer defaults are never silently written into the domain model.
- Visual approximations are not promoted to measured or exact acoustic facts.

## Main window

The target desktop layout is:

- **Center:** large 3D viewport.
- **Left dock:** Scene tree.
- **Right dock:** Inspector / properties / precise numeric editing.
- **Top:** compact mode/transform/view toolbar.
- **Bottom/status:** selection, snap, validation, current Context revision, coordinate feedback.

The viewport is the primary editing surface. Numeric forms are secondary precision controls.

## Scene model

Initial scene node classes:

- Room
  - floor/ceiling shell
  - wall edges
  - polygon vertices
- Speakers
  - one node per speaker
- Listening / Measurement Point
- Constraint overlays
- Search candidates
- Acoustic overlays

Only Room, Speakers, and Measurement Point are required for the first implementation milestone.

Scene actors keep stable domain IDs (`vertex_id`, `speaker_id`, `point_id`) so viewport picking and Scene tree selection refer to the same object.

## Camera and navigation

Required modes:

- orbit/pan/zoom perspective view
- top orthographic plan view
- front/right/left views
- fit selection / fit room
- visible metric grid
- coordinate axes

Top view is the primary room-footprint editing mode. Perspective mode is the primary setup inspection mode.

## Speaker and measurement-point editing

Selecting a movable spatial entity attaches a CAD-style transform gizmo.

Initial behavior:

- X/Y/Z translation handles
- configurable translation snap, initially 0.05 m / 0.01 m presets
- Inspector shows exact X/Y/Z continuously
- movement is validated against room reference bounds and exact polygon geometry
- invalid placement is not silently clamped

Speaker rotation is separate from translation. When the user explicitly rotates a speaker, the resulting forward direction is normalized and written to draft `aim_xyz`. Translation alone preserves an unknown aim.

## Room polygon editing

For `polygon_prism` Contexts, the top view exposes one draggable handle per ordered room vertex.

Requirements:

- direct vertex drag
- metric grid snap
- stable `vertex_id`
- edges update continuously
- height edited separately
- no automatic polygon reordering
- no silent self-intersection repair
- invalid draft state must be visually obvious
- save is blocked until the existing room geometry validation succeeds

Later commands may include insert vertex on edge, delete vertex, orthogonal constraint, dimension locks, and wall-length entry. They should be domain commands with undo/redo, not ad-hoc mesh edits.

## Undo / redo

Interactive edits are commands applied to the draft. Undo/redo affects the draft only.

At minimum:

- move entity
- change room vertex
- change room height
- explicit speaker orientation

One mouse drag should normally become one undoable command at release, rather than one command per mouse-move event.

## Constraints and search visualization

G10 and O10 remain valid backend/domain work and become richer scene layers instead of form-first workflows.

Planned native visualization:

- allowed regions as translucent floor overlays
- exclusion regions as hatched/red translucent areas
- wall clearance bands
- cabinet envelopes
- linked/mirrored placement guides
- rejected candidates as muted/red points
- feasible candidates as selectable point clouds
- selected candidate displayed as a full setup ghost/preview

Hard feasibility continues to be computed by G10; the renderer does not duplicate constraint truth.

## Acoustic visualization direction

VTK/PyVista is intentionally selected so future milestones can display:

- reflection paths
- room-mode geometry
- frequency-dependent heatmaps
- SPL scalar fields
- prediction residual fields
- candidate clouds colored by objective-vector components

Measured, predicted, derived, and unknown evidence must remain visually and semantically distinct.

## Launch strategy

During transition:

1. Keep the existing FastAPI API and web frontend working.
2. Add a native editor entry point that uses the same Store/domain code directly on the local machine.
3. Once the native editor covers the core Project/Context workflow and passes Windows acceptance, make it the default `run-local.ps1` experience.
4. Keep an explicit web/diagnostic launch mode rather than deleting the browser UI immediately.

The native GUI should not need HTTP to talk to its own local domain layer. FastAPI remains useful for tests, interoperability, and the fallback web UI.

## First implementation milestone acceptance

The native editor is not accepted merely because it renders a room. The first usable milestone must pass all of the following on the owned Windows 11 machine:

1. Load an existing Project and exact Context revision.
2. Render the 8-vertex concave polygon room as a 3D prism.
3. Render every positioned speaker and the measurement point.
4. Select the same entity from either Scene tree or viewport.
5. Translate a speaker and measurement point with a mouse gizmo and metric snap.
6. Edit room polygon vertices directly in top view.
7. Show exact coordinates in Inspector while editing.
8. Undo and redo edits.
9. Reject invalid/outside-room drafts without silent correction.
10. Save only by creating a new validated immutable Context revision.
11. Reload the new revision and reproduce geometry/positions exactly.
12. Preserve unknown speaker aim unless orientation was explicitly edited.

## Roadmap impact

O20 Batch Prediction is intentionally paused while the primary interaction architecture is replaced. O10/G10 backend contracts remain in place and will be surfaced through the native scene.

Near-term sequence:

- **N00 — architecture/prototype:** stack selection, Windows render/gizmo proof, documented here.
- **N10 — native spatial editor shell:** Scene tree, viewport, Inspector, camera/grid, Project/Context load.
- **N20 — direct editing:** speaker/MLP gizmos, room vertex handles, snap, undo/redo, immutable Context save.
- **N30 — constraint/search scene:** visualize and edit G10/O10 spatially.
- **N40 — native default launch:** packaging/startup/error handling and browser UI fallback.
- Resume O20 after N20/N30 establish the scene representation required to inspect prediction batches effectively.

## Windows prototype evidence

A local prototype on the owned Windows 11 machine successfully launched PySide6 + PyVistaQt/VTK using Python 3.12 and rendered:

- the existing 8-vertex concave room fixture
- FL / C / FR loudspeaker objects
- MLP marker
- 3D grid and axes
- a PyVista `AffineWidget3D` translation/rotation gizmo

This proves the selected rendering/desktop stack can run on the actual target machine. It is not yet the product acceptance test; the product implementation must satisfy the milestone criteria above.
