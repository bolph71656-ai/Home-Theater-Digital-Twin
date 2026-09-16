# Native 3D Spatial Editor

## Decision

HTDT is moving away from a form-first browser UI as the primary interaction model. The primary editing experience will be a native Windows desktop spatial editor built with PySide6 + PyVista/VTK + PyVistaQt.

The existing browser UI remains available as a fallback during migration. Existing backend APIs, immutable Context revisions, room geometry validation, placement constraints, measurement provenance, and search-space contracts remain authoritative.

## Why this stack

PySide6 provides a native Qt application shell and dockable panes. PyVista/VTK provides the 3D scene, picking, transform widgets, point/mesh/volume rendering, slices and future acoustic-field visualisation. PyVistaQt embeds that scene directly in Qt.

This is a better fit for HTDT than a mechanical-CAD-only kernel because HTDT must render room geometry, speaker cabinets, listening points, placement regions, candidate clouds, reflection paths and future acoustic scalar/volume fields in one scene.

FreeCAD and CQ-editor are reference implementations for CAD navigation, object trees, dockable inspectors and selection synchronisation. They are not runtime dependencies.

## Product interaction model

The central 3D viewport is the primary workspace. A Scene tree on the left lists Room, Speakers, Listening Position, Constraints, Candidates and later Prediction layers. An Inspector on the right exposes exact numeric values and metadata for the selected object.

Spatial objects are manipulated directly with mouse-driven gizmos. Camera orbit, pan, zoom, orthographic views, top/front/side presets and fit-to-scene are first-class controls. Numeric entry remains available for precision but is no longer the main workflow.

Room polygon vertices are edited directly in top view. Speaker and MLP positions are moved in 3D. Grid snapping is configurable. Constraint regions and candidate sets will be visual layers rather than JSON/form-first concepts.

## Data integrity contract

The viewport never mutates a stored Context in place. Opening a Context creates an in-memory draft. Each edit is validated against the existing ContextCreate model and room geometry rules. Save creates a new immutable Context revision with the source Context as parent.

Unknown values stay unknown. In particular, moving a speaker does not invent an aim vector. `aim_xyz` is written only after an explicit user rotation/aim action.

Undo/redo operates on draft state. Invalid geometry or out-of-room placements are rejected before a new draft state is committed.

## Initial milestone

The first native-editor milestone is limited to:

- native Qt main window;
- Scene tree, 3D viewport and Inspector;
- rectangular and polygon-prism room rendering;
- speaker and MLP rendering;
- object selection synchronisation;
- mouse transform gizmo for movable entities;
- direct polygon-vertex editing in top view;
- deterministic metric grid snapping;
- draft undo/redo;
- save-as-new-Context-revision;
- Windows rendering and persistence acceptance tests.

Measurement, comparison and search/prediction workflows remain backed by the existing services until their native visual layers are implemented.

## Technology baseline

Initial validated Windows/Python 3.12 versions:

- PySide6 6.11.2
- PyVista 0.49.0
- PyVistaQt 0.13.1
- VTK 9.7.0

A local prototype on the HTDT Windows machine successfully rendered the existing 8-vertex concave room fixture, FL/C/FR speaker cabinets and MLP in a native Qt window and attached a 3D affine transform gizmo to a selected speaker.

## Migration rule

Do not add new workflow-specific form screens to the browser UI unless needed as a temporary fallback. New placement-oriented functionality should expose scene-layer data and interaction hooks so it can be represented directly in the native 3D workspace.
