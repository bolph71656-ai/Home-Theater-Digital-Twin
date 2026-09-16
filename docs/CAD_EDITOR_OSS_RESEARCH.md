# CAD-like 3D Editor — OSS調査と技術選定

> 調査日: 2026-09-16  
> 状態: **採用判断済み**  
> 対象: Windows 11 x64 / 個人利用 / HTDTの3D CADライクGUI全面再設計  
> 関連: [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md), [ADR-0001](adr/0001-native-cad-editor-stack.md)

## 1. 結論

HTDTのGUIは、従来のブラウザ中心UIとの互換性を要求せず、**ネイティブデスクトップの3D CADライク・ワークスペース**として再構築する。

主実装は次を採用する。

- **Python 3.12+**: ドメイン、音響解析、データI/O、アプリケーションロジック。
- **PySide6 / Qt 6 Widgets**: ネイティブWindow、Dock、Action、Inspector、Outliner、ショートカット、ファイル操作。
- **PyVista + VTK + PyVistaQt**: 3D viewport、picking、mesh/actor管理、transform widget、scalar/volume/point-cloud可視化。
- **Pydantic + SQLite**: 保存境界と不変Revision。編集途中はWorking Documentとして分離。
- **Shapely**: 2D room footprint、allowed/exclusion region、幾何判定。現在のG00/G10資産を継続利用する。
- **NumPy / SciPy**: 数値計算。
- **glTFを主要な汎用3D交換形式**とし、STEP/IGES/IFC等は必要になった時点でadapterとして追加する。

この選択は「既存Pythonコードを捨てたくないから」ではない。**HTDT固有の将来要件が、機械CADのB-rep編集よりも、部屋・配置の編集と音響場・測定値・候補群・反射経路の科学可視化を同じviewportへ重ねることにある**ためである。VTKはこの後半の要求に非常に強く、PySide6とPython科学計算スタックの境界コストが小さい。

Godot、Open CASCADE、FreeCAD、Blender等は重要な参照元だが、主ランタイムにはしない。設計パターンは積極的に参考にし、ライセンス上問題のあるコードはコピーしない。

## 2. 選定基準

優先順位は次の通り。

1. **マウス中心でCADのように空間を構築・確認できること**
2. 3D viewportをアプリの中心にできること
3. 選択、hover、gizmo、snap、数値入力、orthographic view、undo/redoを一貫した操作モデルにできること
4. 部屋、家具、座席、スクリーン、スピーカー、測定点、AV機器を同じDocumentで扱えること
5. 将来の音圧場、予測結果、候補点群、反射経路、heatmap、slice、volume等を重畳できること
6. Pythonの音響・科学計算エコシステムとの統合が容易であること
7. Windowsで配布・デバッグしやすいこと
8. 特定CADカーネルへDocumentモデルが拘束されないこと
9. GUI実装が長期的に分割・テスト可能であること
10. ライセンスと保守性が明確であること

## 3. 採用スタック

| レイヤ | 採用 | 理由 |
|---|---|---|
| Desktop shell | PySide6 / Qt 6 Widgets | CAD型Dock UI、Action/shortcut、native window、成熟したdesktop widget |
| 3D renderer | VTK via PyVista | picking、large meshes、scientific scalar/volume/point-cloud visualization |
| Qt/VTK bridge | PyVistaQt | Qt native widget内へviewportを埋め込みやすい |
| Domain | Python typed model | 既存音響スタックと同一言語、renderer非依存に保てる |
| Validation | Pydantic | file/API境界のschema validation |
| Persistence | SQLite + immutable revisions | 測定・比較・配置履歴との整合性を維持 |
| 2D geometry | Shapely | polygon room / feasibility engineで実績あり |
| Numeric | NumPy/SciPy | 音響、最適化、補間、統計 |
| Exchange | glTF first | scene asset交換に適し、rendererから独立 |
| Optional CAD adapter | Open CASCADE / CadQuery系を後付け | STEP/IGES/B-repが本当に必要になった場合のみ |

### Windows PoCの確認済み事項

PR #37 の試作で、Windows上の以下を確認済み。

- PySide6 6.11.2
- PyVista 0.49.0
- PyVistaQt 0.13.1
- VTK 9.7.0
- Python 3.12
- 8頂点の凹polygon roomをnative Qt windowへ描画
- FL/C/FRとMLPの描画
- PyVista `AffineWidget3D` を用いたspeaker actorの移動/回転操作
- `ContextDraft` のsnap、undo/redo、位置変更とaim情報の分離

バージョン番号はPoC記録であり、正式依存は実装PRでlockする。

## 4. OSS調査結果

### 4.1 PyVista / VTK — **主採用**

**用途**: viewport、picking、transform interaction、mesh/scalar/volume/point-cloud表示。

参考対象:

- PyVista: plotting / picking / widgets / actor management
- PyVistaQt: QtInteractor / BackgroundPlotter integration
- VTK: renderer / picker / interaction style / widgets / transforms / volume rendering

HTDTで取り込む考え方:

- rendererのactorをDocumentの正本にしない。
- `entity_id -> RenderProxy/Actor` のregistryを持つ。
- selectionはactorではなくentity IDで保持する。
- transform widget操作中はpreview transform、確定時だけCommandをcommitする。
- acoustic resultはeditable entityとは別のVisualization Layerとして扱う。

### 4.2 Qt / PySide6 — **主採用**

**用途**: application shell、dock、inspector、outliner、actions、menus、shortcuts、native dialogs。

参考パターン:

- `QMainWindow` + central 3D viewport
- left dock: Scene / Add / Layers
- right dock: Inspector / Constraints / Analysis
- top: mode-aware toolbar
- bottom/status: cursor world position、snap mode、selection summary、operation hint
- `QUndoStack`の思想は参考にするが、永続DocumentのCommand historyはHTDT側で明示定義する。

### 4.3 CQ-editor / CadQuery — **UI構成を参考**

CQ-editor系は、Qt desktop shell + object tree + OpenCascade viewer + console/inspectorというCADアプリの典型構造を持つ。

HTDTではOpenCascade viewer自体は主採用しないが、以下を参考にする。

- object treeとviewport selectionの双方向同期
- dockable tool panes
- view presets / fit / shaded-wireframe切替
- editor shellとgeometry backendの分離

### 4.4 FreeCAD — **アーキテクチャを参考。主ランタイムにはしない**

FreeCADはDocument/Application/Gui/Command/Selectionを明示的に分けた成熟CADであり、HTDTの設計参照として非常に重要。

主な参照箇所:

- `src/App/Document.cpp` — Document/transaction/recomputeの考え方
- `src/Gui/Command.cpp` — Command登録とUI actionの分離
- `src/Gui/Selection.cpp` — model selectionとGUI selection
- `src/Mod/Sketcher/App/` — constraint-driven parametric editing
- `src/Mod/Sketcher/App/planegcs/` — geometric constraint solver

HTDTで採用する思想:

- Documentはrendererから独立
- Undo/RedoはDocument transaction/Commandとして扱う
- UI commandとdomain mutationを分ける
- parametric entityとrender meshを分離する

採用しない理由:

- HTDTには汎用機械CAD全体が不要
- 独自UXを作る際にFreeCAD UI/frameworkへ拘束される
- 音響scalar/volume可視化は別系統が必要になる

### 4.5 Blender — **transform / snapping / tool状態機械を参考。コードはコピーしない**

Blenderの`source/blender/editors/transform/`は、CAD/DCC型のtransform systemを設計するうえで重要な参照元。

主な参照箇所:

- `source/blender/editors/transform/transform.hh`
- `source/blender/editors/transform/transform_ops.cc`
- `source/blender/editors/transform/transform_constraints.*`
- `source/blender/editors/space_view3d/`

参考にする設計:

- transform中のmodal state
- axis/plane constraint
- snap source / snap targetの分離
- precision modifier
- operation開始時snapshot、preview、confirm/cancel
- 数値入力とマウスdragを同一transformへ流す

BlenderはGPL-2.0-or-laterのため、**設計思想のみ参照し、実装コードをHTDTへコピーしない**。

### 4.6 Godot Engine — **gizmo / scene editor / undo設計を参考。主ランタイムにはしない**

GodotはMITで、3D editor、node tree、gizmo、inspector、UndoRedo、scene serializationの参照元として優秀。

参考領域:

- 3D editor plugin / gizmo system
- `EditorUndoRedoManager`
- Node/Scene tree
- Inspector plugin system
- Input event routing

良い点:

- editor interactionが標準化されている
- native desktop rendering/UIを一体で作れる
- MITで参照しやすい

主採用しない理由:

- HTDTの科学計算・測定・最適化はPython ecosystem中心
- Godot C#/GDScriptとのruntime boundaryが増える
- acoustic field/volume/point-cloud解析ではVTKがより直接的
- HTDTはgame runtimeよりengineering/scientific desktop toolに近い

ただし、VTKで操作性の受入基準を満たせない場合の**第一fallback候補**とする。

### 4.7 Open CASCADE Technology (OCCT) — **高度CAD adapter候補**

OCCTはB-rep/NURBS/boolean/STEP/IGES/interactive CAD表示に強い。

参考対象:

- `AIS_InteractiveContext`
- `AIS_Manipulator`
- `TopoDS_*`
- `BRepBuilderAPI_*`
- `BRepAlgoAPI_*`

HTDTで主採用しない理由:

- room/speaker/seat配置の大半は2D polygon + extrusion + transformで表現可能
- B-rep kernelをDocument中心にすると実装量と依存が急増する
- acoustic scalar field/volume表示には別rendererが必要

STEP/IGES等の正確なCAD importが必要になった時点で、独立adapter/serviceとして採用を検討する。

### 4.8 SolveSpace — **constraint solverの設計参照**

SolveSpaceは軽量なparametric CADとして、2D/3D幾何constraintの設計参照に有用。

参考対象:

- `src/constraint.cpp`
- `src/entity.cpp`
- `src/modify.cpp`
- `src/graphicswin.cpp`

GPLv3のため、solverコードを直接取り込む場合はライセンス影響が大きい。HTDTではまず必要なconstraintを限定実装し、一般constraint solverが必要と判明してから再検討する。

### 4.9 Sweet Home 3D — **room/furniture UXを参考**

住宅の平面図・家具配置・3D確認というドメインがHTDTに近い。

参考領域:

- `model`
- `viewcontroller`
- `j3d`
- `PlanController`
- `HomePieceOfFurniture3D`
- `Wall3D`
- `DimensionLine3D`

参考にする点:

- catalogからsceneへ配置する操作
- wall/furnitureのdomain model
- 2D planと3D viewの同期
- dimension表示

主採用しない理由:

- Java/Java3D中心
- UI/rendererをそのまま流用するより設計参照価値が高い
- GPL系のためコードコピーは避ける

### 4.10 Three.js / React Three Fiber / Babylon.js — **Web版の参照・fallback**

Web 3Dとしては成熟している。

参考箇所:

- Three.js `examples/jsm/controls/TransformControls.js`
- Three.js `Raycaster`
- Babylon.js `GizmoManager`
- Babylon.js pointer drag behavior
- R3F / drei transform controls and declarative scene composition

主採用しない理由:

- HTDTの主対象がWindows desktopであり、WebView/browser lifecycleを持ち込む価値が小さい
- native filesystem / window / multi-panel desktop UXはQtが直接的
- Python scientific stackとの境界を設ける必要がある

ただし、将来viewer-onlyの共有版を作る場合には有力。

### 4.11 OpenSCAD / BRL-CAD / SALOME — **モデリング設計の参照**

- OpenSCAD: declarative CSG / parametric regenerationの参照
- BRL-CAD: CSG tree / geometry databaseの参照
- SALOME: CAD/mesh/solver workflowの参照

HTDTは汎用solid modellerではないため、これらをapplication shellやcore kernelとして採用しない。

### 4.12 IfcOpenShell / BIM系 — **将来import adapter**

建築BIM/IFCを読み込む必要が出た場合に使用候補。初期DocumentをIFC中心にしない。

理由:

- HTDTの編集対象はホームシアター設置と音響でありBIM全体ではない
- IFC schemaを内部モデルにすると操作と履歴が過剰に複雑になる

### 4.13 Clipper2 — **必要時のpolygon offset/boolean候補**

Clipper2はBoost Software License 1.0で、整数座標ベースのrobustなpolygon clipping/offsetに有用。

現在はShapelyでG00/G10を実装済みのため直ちに置換しない。offset robustnessやWindows配布上の問題が明確になった場合のみ比較PoCする。

## 5. CADライク操作へ取り込む設計パターン

### 5.1 Command + transaction

全ての永続変更はCommandとして表現する。

例:

- `MoveEntityCommand`
- `RotateEntityCommand`
- `ResizeEntityCommand`
- `MoveRoomVertexCommand`
- `InsertRoomVertexCommand`
- `DeleteRoomVertexCommand`
- `SetPropertyCommand`
- `CreateEntityCommand`
- `DeleteEntityCommand`
- `GroupEntitiesCommand`

pointer moveのたびに履歴を増やさない。drag開始時にbefore stateを取り、drag中はpreview、mouse-upで1 Commandへcoalesceする。

### 5.2 Tool state machine

viewportは巨大なmouse event handlerにしない。

最低限のTool:

- Select
- Move
- Rotate
- Room Sketch
- Room Vertex Edit
- Place Speaker
- Place Seat / Listening Point
- Place Screen
- Place Furniture
- Measure
- Orbit/Pan temporary navigation

Toolは`activate -> pointer_down -> pointer_move -> pointer_up -> cancel/deactivate`を持つ。

### 5.3 Selection service

Selectionはviewport actorやQt tree rowに保持しない。

`SelectionState`を正本とし、以下がsubscribeする。

- viewport highlight
- scene tree
- inspector
- status bar
- command enable/disable

### 5.4 Snap engine

Snapをrendererやgizmo内部へ埋め込まない。

候補:

- grid
- axis lock
- angle increment
- vertex
- edge
- edge midpoint
- wall projection
- room boundary
- alignment with other entities
- speaker symmetry axis
- user-defined clearance

各candidateはtype / world point / distance / priority / source entityを返す。UIは現在採用中のsnap targetを視覚表示する。

### 5.5 Render proxy

Document entityからVTK actorを直接参照しない。

```text
Document Entity
  -> SceneProjection
    -> RenderProxy
      -> one or more VTK Actors
```

render actorの再生成・LOD・highlightはDocument identityを壊さない。

## 6. ライセンス方針

- MIT/BSD/Apache/Boost系は、必要なら依存または実装参考にできる。
- LGPL系は動的リンク/依存条件を確認して利用する。
- GPL系（Blender、SolveSpace、Sweet Home 3D等）は**設計参照のみ**を原則にする。
- GPLコードをHTDTへコピーする判断は、プロジェクト全体のライセンス方針を変更するため、個別ADRなしでは行わない。
- 参考にしたOSS、バージョン、ファイル、ライセンスは実装PRの記録へ残す。

## 7. 採用しない主候補と理由

| 候補 | 主採用しない理由 |
|---|---|
| FreeCAD fork / workbench | HTDT UXをFreeCAD frameworkへ拘束しすぎる |
| Blender addon | DCC UI/データモデルがHTDT利用者の中心操作と合わない |
| Godot app | Python scientific stackとのruntime/language境界が増える |
| OCCT-only app | B-repには強いが音響field/volume可視化には追加rendererが必要 |
| Three.js/R3F/Babylon browser app | native Windows desktopを第一対象にする今回方針と逆 |
| Rust + wgpu + egui | 低レベル実装量が多く、HTDT固有価値に到達するまでが長い |
| Bevy | editor application frameworkとしてはHTDTで必要な成熟度/desktop toolingを自前補完する範囲が大きい |
| Unity/Unreal | engine規模、ライセンス、配布サイズ、engineering appとの不一致 |

## 8. リスクとescape hatch

### R1: VTKのgizmoがCAD操作として不足

対策:

- custom overlay handles / Qt overlay / VTK widgetsで補う。
- N20 acceptanceで、selection、move/rotate、snap、numeric input、cancel/confirmを評価する。
- 満たせない場合はGodot 4 .NET PoCを第一fallbackとして比較する。

### R2: scene規模増大でactor管理が重い

対策:

- RenderProxy cache
- static/dynamic layer分離
- glyph/instancing
- dirty-region更新
- analysis layerのdecimation/LOD

### R3: Documentとrendererが密結合する

対策:

- renderer importをDomain packageで禁止
- entity ID / event / projection boundaryで接続
- 保存schemaはVTK class名やactor stateを含めない

### R4: 汎用CAD要求が膨張する

対策:

- HTDTは「ホームシアター空間編集CAD」であり汎用CADにはしない。
- B-rep、fillet、NURBS sketcher等は実要件発生まで作らない。
- importはadapterで解決する。

## 9. 参考情報

調査時点で確認した主要ソース:

- Godot license: https://godotengine.org/license/
- Godot C# docs: https://docs.godotengine.org/en/stable/tutorials/scripting/c_sharp/
- VTK: https://github.com/Kitware/VTK
- PyVista: https://github.com/pyvista/pyvista
- PyVistaQt: https://github.com/pyvista/pyvistaqt
- FreeCAD: https://github.com/FreeCAD/FreeCAD
- Blender: https://github.com/blender/blender
- Open CASCADE: https://github.com/Open-Cascade-SAS/OCCT
- SolveSpace: https://github.com/solvespace/solvespace
- Sweet Home 3D: https://github.com/SweetHome3D/SweetHome3D
- Three.js: https://github.com/mrdoob/three.js
- Babylon.js: https://github.com/BabylonJS/Babylon.js
- IfcOpenShell: https://github.com/IfcOpenShell/IfcOpenShell
- Clipper2: https://github.com/AngusJohnson/Clipper2

この文書は候補比較の記録であり、**実装順と完了条件の正本は `IMPLEMENTATION_ROADMAP.md`** とする。