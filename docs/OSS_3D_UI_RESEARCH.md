# OSS research for the HTDT 3D UI

> Research note: 2026-09-16

The native GUI redesign intentionally reuses proven interaction patterns instead of rebuilding a 3D editor from first principles.

## CQ-editor / CadQuery

Useful patterns:
- `QMainWindow` desktop shell;
- central OpenCascade 3D viewer;
- dockable Object Tree / inspector / console panes;
- bidirectional object-tree and graphical-selection synchronization;
- camera presets, fit, shaded/wireframe switching, grid and axes.

HTDT will reuse the application-structure pattern, not the full OpenCascade rendering stack.

## FreeCAD

Useful patterns:
- persistent scene/object tree;
- direct-manipulation draggers/manipulators;
- CAD camera navigation and orthographic views;
- explicit separation of document model, commands, GUI selection, and rendering.

FreeCAD is too broad to embed as HTDT's application shell, but its command/undo and selection concepts are relevant.

## PyVista / VTK

Selected as the main renderer because it combines:
- native desktop embedding through PyVistaQt;
- mesh/actor/point/face picking;
- `AffineWidget3D` for translation and rotation;
- surface, volume, scalar-field, slice and point-cloud visualization;
- Python-native integration with HTDT's analysis and geometry code.

This is materially more suitable than a pure mechanical-CAD renderer for future SPL fields, prediction candidate clouds, reflection paths, and measurement overlays.

## pyvista-cad

Potential future import layer for STEP, IGES, BREP, DXF, IFC, FCStd and glTF. It is not required for N10. CAD import is deliberately kept separate from the core spatial-editor milestone.

## Rejected as primary stack

- Three.js / browser-first: capable 3D rendering, but keeps the current browser application model the user explicitly wants replaced.
- Godot: strong editor/gizmo/UndoRedo patterns, but introduces a second runtime/language boundary around the existing Python acoustic stack.
- OpenCascade-only: excellent B-rep/CAD kernel, but less direct for acoustic scalar fields, volume rendering and dense prediction overlays.

## Result

N10 uses PySide6 + PyVista/VTK + PyVistaQt as the production direction. Existing FastAPI/web UI remains a migration fallback until the native editor passes Windows acceptance.
