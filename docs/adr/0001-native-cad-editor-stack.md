# ADR-0001: HTDTをネイティブ3D CADライク・エディタへ再設計する

- Status: **Accepted**
- Date: 2026-09-16
- Decision owners: HTDT project
- Supersedes: browser-first GUIを前提にした従来のUI方針
- Related: [CAD_EDITOR_OSS_RESEARCH.md](../CAD_EDITOR_OSS_RESEARCH.md), [IMPLEMENTATION_ROADMAP.md](../IMPLEMENTATION_ROADMAP.md)

## Context

HTDTの価値は、測定値や比較表を表示するだけではなく、ユーザーが実際の部屋、スピーカー、座席、スクリーン、家具、測定点、配置制約を空間として構築し、その状態と測定・予測・最適化結果を一体で理解できることにある。

従来のbrowser-first UIは、数値入力と簡易3D表示には適していたが、3D CADのようなmouse-first editingを中心操作へ据えるには構造的な負債が大きい。互換性維持を優先すると今後の編集ツール、snapping、gizmo、selection、undo/redo、analysis overlayの実装効率が低下するため、UI/interaction layerは全面再設計する。

## Decision

### 1. GUIをnative desktop applicationとする

Windows 11 x64を第一対象とし、PySide6/Qtをapplication shellに採用する。Web browserは主UIではない。

### 2. 3D viewportはPyVista/VTKを採用する

理由:

- native Qt embedding
- actor/mesh/point/face picking
- transform widgets
- orthographic/perspective camera
- scalar field、volume、slice、point cloud等の科学可視化
- Pythonの音響解析・最適化スタックとの低コスト統合

### 3. Documentをrendererから独立させる

VTK actor / PyVista mesh / Qt widgetを保存modelの正本にしない。

Canonical hierarchy:

```text
HTDT Document
  Room
  Openings
  Furniture
  Screen
  Speakers
  Listening positions / Seats
  Measurement points
  AV equipment
  Constraints
  Analysis references
  Metadata
```

RendererはDocumentのprojectionである。

### 4. 変更はCommandとして表現する

mouse drag中はpreview state、操作確定時に1つのCommandとしてcommitする。Undo/RedoはCommand historyを正本とする。

保存時はWorking Documentから新しいimmutable Context/Scene revisionを生成する。

### 5. Tool state machineを採用する

Select / Move / Rotate / Room Sketch / Vertex Edit / Place Speaker / Place Seat / Measure等を独立Toolとして実装し、viewportへ巨大なmouse event分岐を書かない。

### 6. SelectionとSnappingを独立serviceとする

Selectionはentity ID集合として保持する。Scene tree、Inspector、Viewport、Status barは同じSelectionStateへ同期する。

Snap engineはgrid、axis、angle、vertex、edge、midpoint、wall projection、alignment、symmetry等のcandidateをrenderer非依存で評価する。

### 7. 汎用CAD kernelをcore requirementにしない

HTDTの中心形状はpolygon/extrusion/transformで表現できる。Open CASCADE等のB-repはSTEP/IGESや高度形状が実要件になった場合にadapterとして追加する。

### 8. 旧browser UIとの互換性は要件としない

既存backend/dataは価値があるものだけ移植・再利用する。既存frontend API契約やscreen layoutを守るために新Document/GUI設計を歪めない。

## Consequences

### Positive

- viewportを中心にしたCAD的UXを最初から設計できる
- mouse manipulation、selection、snap、numeric editを同じ操作体系にできる
- acoustic analysisを3D visualization layerとして自然に追加できる
- Python計算資産と同一process/言語で連携できる
- rendererを交換してもDocument schemaを維持できる

### Negative

- Qt/VTK interactionをHTDT向けに作り込む必要がある
- browser frontendとの二重保守期間を短期間持つ可能性がある
- VTK標準gizmoだけで理想UXへ届かない場合はcustom overlayが必要

## Rejected primary alternatives

- FreeCAD fork/workbench: frameworkが広すぎ、HTDT固有UXを拘束する
- Blender add-on: DCC中心のinteraction/data modelが利用目的と異なる
- Godot: editor能力は高いがPython scientific stackとのruntime/language boundaryが増える
- Open CASCADE-only: B-repには強いがacoustic field visualizationを別途要する
- Three.js/R3F/Babylon.js browser app: desktop-first方針と逆
- Rust/wgpu/Bevy/egui: foundational code量が大きく、価値提供まで遠い

## Validation gates

このADRは無条件に技術へ固執するものではない。以下をN20で確認する。

- select/hover responseが即時である
- speaker/seat/furnitureをgizmoでmove/rotateできる
- grid/axis/angle/wall snapが視覚的に理解できる
- dragをEscで完全cancelできる
- mouse-upで履歴が1 Commandになる
- Inspector数値編集とviewport操作が同じCommand/validation経路を通る
- top/front/side/perspective viewが同一Documentを扱う
- 1000程度のscene entity/analysis markersでも操作感を維持する

満たせない場合は、Godot 4 .NETを第一fallbackとして同じDocument/Command contractでPoCし、renderer/application shellのみ再評価する。
