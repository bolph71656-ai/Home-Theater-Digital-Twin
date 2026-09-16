# HTDT 実装ロードマップ — CAD-first 正本

> 改訂: 2026-09-16  
> 状態: **今後の実装ロードマップの正本**  
> 対象: Windows 11 x64 / 個人利用  
> 技術決定: [ADR-0001](adr/0001-native-cad-editor-stack.md)  
> OSS調査: [CAD_EDITOR_OSS_RESEARCH.md](CAD_EDITOR_OSS_RESEARCH.md)

## 0. この文書の位置付け

**2026-09-16以降、実装の優先順位・段階・受入条件は本書を正本とする。**

旧ロードマップで進めたREW取込、測定履歴、Room Geometry v2、Placement Constraints、Search Space等は有効な実装資産として保持するが、今後の製品中心は「フォーム/グラフ中心のbrowser tool」ではなく、**3D CADのように部屋とホームシアターを直接構築・編集・確認できるnative spatial editor**へ移す。

互換性維持は要件ではない。既存実装は、新アーキテクチャへ適合し将来の開発効率を上げるものだけ再利用する。

文書の正本関係:

| 文書 | 正本とする内容 |
|---|---|
| **本書** | 実装順、milestone、受入条件、移行方針 |
| [ADR-0001](adr/0001-native-cad-editor-stack.md) | native CAD editorの技術・アーキテクチャ決定 |
| [CAD_EDITOR_OSS_RESEARCH.md](CAD_EDITOR_OSS_RESEARCH.md) | OSS調査、採用/不採用理由、コード参照先 |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | mainへ反映済みの事実 |
| [DATA_AND_ANALYSIS.md](DATA_AND_ANALYSIS.md) | 測定/比較データ契約 |
| [MEASUREMENT_WORKFLOW.md](MEASUREMENT_WORKFLOW.md) | REW/マイク/AVRの測定境界 |
| [PLACEMENT_OPTIMIZATION_ROADMAP.md](PLACEMENT_OPTIMIZATION_ROADMAP.md) | 最適配置アルゴリズムの詳細。実装順は本書に従う |

矛盾する旧文書がある場合は、本書とADR-0001を優先する。

---

## 1. 完成像

HTDTを起動すると、中央に大きな3D viewportがあり、ユーザーはCADと同様にmouseで空間を作る。

### 1.1 基本操作

- 空のsceneからroom footprintをclickして描く。
- wall vertexをdragし、寸法を直接入力して正確に修正する。
- wall thickness / room height / openingsを編集する。
- speaker、seat、screen、furniture、AV equipmentをpaletteからdrag/dropする。
- objectをclickして選択し、gizmoでmove/rotateする。
- grid、axis、angle、wall、vertex、edge、alignmentへsnapする。
- Top / Front / Side / Perspectiveを即時切替する。
- Scene treeから選んでもviewportで選んでも同じselectionになる。
- Inspectorで数値入力するとviewportへ即反映される。
- `Ctrl+Z/Ctrl+Shift+Z`、Esc cancel、duplicate、delete、multi-select等が一貫して動く。
- dimension、distance、angle、clearanceをscene上で確認できる。

### 1.2 HTDT固有の重畳表示

同じsceneへ次をlayerとして重ねる。

- speaker radiation/aim
- MLP / seat / microphone positions
- measurement dataset markers
- room modes / reflection paths
- allowed / exclusion regions
- placement search candidates
- prediction response summaries
- SPL/metric heatmap
- scalar field / slice / volume visualization
- measured-vs-predicted residual

編集対象と解析表示は同一viewportに存在するが、Document上は別レイヤとして分離する。

---

## 2. 確定技術スタック

### 2.1 Production direction

- Python 3.12+
- PySide6 / Qt 6 Widgets
- PyVista / VTK / PyVistaQt
- Pydantic
- SQLite
- Shapely
- NumPy / SciPy

### 2.2 原則

- Qt WidgetやVTK ActorをDocument modelにしない。
- Python domain packageからQt/VTKをimportしない。
- rendererはDocumentのprojectionであり正本ではない。
- viewport操作もInspector操作も同じCommand/validation経路を通す。
- scene全体を巨大なmutable dictとして編集し続けない。
- mouse moveごとにUndo historyを増やさない。
- full CAD kernelは初期要件にしない。
- physics engineで配置制約を代用しない。制約は決定論的geometryとして評価する。

---

## 3. 目標アーキテクチャ

```text
PySide6 Application Shell
├─ Command/Action Registry
├─ Scene Tree / Palette / Layers
├─ 3D Viewport
├─ Inspector / Constraints / Analysis
└─ Status / Navigation
          │
          ▼
Editor Application Layer
├─ ToolController
├─ SelectionService
├─ SnapEngine
├─ CommandHistory
├─ WorkingDocument
├─ Clipboard / Duplicate
└─ ViewState
          │
          ▼
Domain
├─ Document / Revision
├─ Room / Wall / Opening
├─ Speaker / Seat / Screen / Furniture / AV Equipment
├─ MeasurementPoint
├─ ConstraintSet
├─ AnalysisReference
└─ Geometry / Validation
          │
          ├──────────────► Persistence / SQLite / RawAssets
          │
          ├──────────────► REW / Prediction / Optimization adapters
          │
          ▼
SceneProjection
├─ RenderProxyRegistry
├─ EditableEntityLayer
├─ AnalysisLayer
├─ AnnotationLayer
└─ Selection/Highlight Overlay
          │
          ▼
PyVista / VTK
```

---

## 4. Document設計

### 4.1 正本はDocument

Documentには少なくとも以下を持つ。

- `document_id`
- `revision_id`
- units / coordinate system
- room geometry
- openings
- furniture
- screen(s)
- speakers
- seats/listening positions
- measurement points
- AV equipment
- constraints
- layer visibility metadata
- references to measurements / predictions / optimization runs

### 4.2 Entity identity

全entityは安定したIDを持つ。display name、tree row、VTK actor ID、DB row indexをidentityにしない。

### 4.3 Working Documentと保存Revision

- editorを開いた時点のRevisionからWorking Documentを作る。
- editing中のCommandはWorking Documentへ適用する。
- Save時に新しいimmutable Revisionを生成する。
- 過去のmeasurementが参照するRevisionを書き換えない。

### 4.4 Renderer非依存

保存schemaへ以下を入れない。

- VTK actor pointer/ID
- PyVista object
- Qt widget state
- camera内部class
- renderer固有material object

camera/view/layer visibility等はEditor View Stateとして分離保存できる。

---

## 5. Editor interaction設計

### 5.1 Tool state machine

最低限のTool:

1. Select
2. Move
3. Rotate
4. Room Sketch
5. Room Vertex Edit
6. Place Speaker
7. Place Seat / Listening Point
8. Place Screen
9. Place Furniture
10. Place Measurement Point
11. Measure
12. Orbit/Pan temporary navigation

Tool APIの概念:

```text
activate(context)
pointer_down(event)
pointer_move(event)
pointer_up(event)
key_down(event)
cancel()
deactivate()
```

Tool固有の一時状態はDocumentへ直接保存しない。

### 5.2 Transform transaction

1. pointer downで対象とbefore stateを取得
2. drag中はpreview
3. snap engineへcandidate照会
4. visual snap feedbackを表示
5. pointer upで1 Commandをcommit
6. Esc/right cancelでbefore stateへ完全復元

### 5.3 Selection

- single select
- Ctrl/Shift multi-select
- empty click deselect
- scene tree ↔ viewport bidirectional sync
- hidden/locked layer policy
- selection outline / bounding box / gizmo

### 5.4 Snapping

N20で必須:

- metric grid
- axis constraint
- angle increment
- room vertex
- wall edge projection
- edge midpoint
- object center/alignment

後続:

- symmetry axis
- equal spacing
- clearance snap
- speaker toe-in target
- screen centerline
- seat row alignment

Snap candidateにはtype、target、distance、priority、world positionを持たせ、採用中候補をviewportへ表示する。

---

## 6. UI/UX原則

### 6.1 Layout

標準layout:

- **Center**: viewportを最大領域
- **Left upper**: Scene tree
- **Left lower**: Add / asset palette
- **Right upper**: Inspector
- **Right lower**: Constraints / Analysis / Properties
- **Top**: context-sensitive toolbar + view controls
- **Bottom**: world coordinates、snap、selection、operation hint

### 6.2 説明文に依存しない

- object種別はicon+shape+labelで区別
- selectionしたら編集可能handleを直接表示
- snap targetはhover/guideで示す
- invalid placementはscene上で理由を指す
- hidden/locked/analyzed stateをlayer/UIへ一貫表示
- 操作前に長文説明を読ませない

### 6.3 Progressive disclosure

初期画面に全機能を並べない。

- Beginner: Select / Add / Move / Rotate / Measure / Save
- context selectionで必要なInspectorだけ表示
- advanced constraints / analysisはlayer panelから開く

### 6.4 Keyboard

最低限:

- `Ctrl+Z` undo
- `Ctrl+Shift+Z` redo
- `Delete` delete
- `Esc` cancel
- `F` frame selection
- `1/3/7`等のview presetはPoCで評価し、Windows/CAD慣習に合う形で固定
- modifierによるsnap invert / precision move

---

## 7. Milestones

### N00 — Architecture reset / 正本化

**目的**: browser-first互換性を捨て、native CAD editorを正式な開発軸にする。

成果:

- 本ロードマップ
- ADR-0001
- OSS調査
- PR #37をnative editor implementation trackとして継続

完了条件:

- mainから本書へ辿れる
- 旧ロードマップより本書が優先されることが明記される
- GUI実装PRが本書のmilestone IDを使用する

### N10 — Native editor shell

成果:

- PySide6 `QMainWindow`
- central PyVistaQt viewport
- Scene tree
- Inspector
- status bar
- view presets
- open/save working document

完了条件:

- Windowsでnative windowとして起動
- 既存browserを開かず編集workspaceを表示
- sample room + speakers + MLPをsceneへ描画
- Scene treeとviewportの選択が同期

### N20 — CAD transform foundation

成果:

- ToolController
- SelectionService
- CommandHistory
- Move/Rotate tools
- transform gizmo
- numeric transform Inspector
- grid/axis/angle/wall snap
- confirm/cancel

完了条件:

- speakerをmouseで移動し、1操作=1 undoになる
- Esc cancelで完全に元へ戻る
- rotationを明示しない位置変更がunknown aimを発明しない
- viewport/Inspectorが同じvalidation pathを通る
- multiple selectionの基本transformが破綻しない

### N30 — Room CAD

成果:

- room polygon sketch
- insert/move/delete vertex
- room height
- wall visualization
- opening model foundation
- dimension display
- top/front/side/perspective

完了条件:

- 凹polygon roomをmouseのみで作成できる
- vertex dragと数値編集が一致
- self-intersection等のinvalid geometryを保存しない
- dimensionとstored valueが一致
- G00 geometry contractを新Documentへ統合または明示移行

### N40 — Home theater objects

成果:

- speaker
- seat/listening point
- screen
- furniture primitive
- AV equipment marker
- measurement point
- asset palette / drag-drop
- duplicate/group/lock/hide

完了条件:

- 新規部屋を作り、3.0.2等の構成をmouse中心で組める
- speaker role、position、aimをInspectorとviewportから編集できる
- screen/seat/furnitureに寸法とtransformを持てる

### N50 — Constraint visualization

成果:

- existing G10 constraintsをviewport layer化
- allowed/exclusion area
- clearance visualization
- linked placement
- rejected reason overlay
- candidate preview

完了条件:

- placement candidateの可否をscene上で理解できる
- invalid理由をtableではなく対象geometryと紐付けて示す
- constraint editorがscene selectionと同期

### N60 — Measurement integration

成果:

- existing measurement/REW assetsをnative UIへ統合
- measurement point / Context / Datasetの選択同期
- FR chart dock
- measurement overlay
- comparison layer

完了条件:

- sceneでspeaker/measurement pointを選ぶと関連実測を絞り込める
- measurementからscene entityへ逆選択できる
- 過去Revisionの測定位置を現在位置へ書き換えない

### N70 — Prediction / acoustic visualization

成果:

- reflection path
- room mode annotation
- prediction candidate cloud
- heatmap / scalar field
- slice / volume表示基盤
- measured/predicted differentiation

完了条件:

- editable geometryとprediction resultを明確に見分けられる
- prediction layerをoffにしてもDocument編集へ影響しない
- analysis data量が大きくてもinteraction threadを不必要にblockしない

### N80 — Placement optimization workspace

成果:

- SearchSpec visual editing
- candidate batch inspection
- objective vector visualization
- Pareto candidate comparison
- measurement loop navigation

完了条件:

- O10以降の候補を3D scene上で選択・比較できる
- candidate applyはWorking Documentへのpreviewとして扱える
- predicted rankingとmeasured validationを同じworkflowで追跡できる

### N90 — Productization

成果:

- installer/package
- crash-safe save
- layout persistence
- performance profiling
- release build
- documentation/update flow

完了条件:

- 対象Windows PCでinstall / launch / save / reopen / uninstallが成立
- user dataがapp binary更新で失われない
- core workflowにbrowser frontendが不要

---

## 8. 既存実装の扱い

### 8.1 再利用する

- REW read-only integration
- RawAsset provenance
- measurement/comparison logic
- SQLite migration/backupのうち新schemaにも価値がある部分
- G00 polygon room knowledge
- G10 hard placement constraints
- O10 deterministic search concepts
- NumPy/SciPy/Shapely系ロジック

### 8.2 置換対象

- browser中心のnavigation/layout
- minimal 3D renderer
- form-first room/placement editing
- frontend stateを正本とする設計
- 3D操作と別系統の数値編集経路

### 8.3 互換性を要求しない

必要ならDB/schema/APIをbreaking changeする。

ただし破壊的移行を行うPRは、

- 何を捨てるか
- 何をmigrationするか
- 既存データを保持しない場合の理由
- rollback方法

をPR本文へ記録する。

---

## 9. テスト戦略

可逆的で低影響の変更に機械的なテストを増やさない。**意味のある不変条件だけを自動化する。**

### 必須unit/domain test

- snapping arithmetic
- transform/coordinate conversion
- Command apply/revert
- undo/redo coalescing
- invalid geometry rejection
- room polygon rules
- entity identity preservation
- serialization round-trip
- constraint deterministic evaluation
- measurement revision linkage

### 必要時integration test

- Document -> RenderProxy mapping
- viewport picking -> SelectionState
- inspector edit -> Command -> render update
- save -> reopen -> same Document

### GUIテスト

pixel-perfect screenshot testは主戦略にしない。

Windows実機で以下をsmoke acceptanceする。

- select
- move
- rotate
- snap
- undo/redo
- cancel
- room vertex edit
- save/reopen
- scene/inspector sync

Qt/VTKのbackend差による不安定なテストを大量に作らない。

---

## 10. 性能目標

初期受入の目安:

- normal edit scene: mouse操作が視覚的に即応する
- 1000程度のentity/markersでselectionとorbitが実用的
- drag中にDB writeや重いacoustic solveをしない
- analysis layerは必要に応じdecimation/LOD/instancing
- expensive prediction/optimizationはeditor UI thread外で実行

固定FPSを品質の唯一指標にせず、selection latency、drag latency、camera interaction、save latencyを個別に見る。

---

## 11. GitHub運用

ローカル作業場所は `C:\Users\ka092\Desktop\HTDT\` とする。実機確認、Windows rendering、mouse interaction確認に使用する。

ただし**作業の正本はGitHub**。

各実装PRに最低限残す:

- milestone ID (`N20`, `N30`等)
- 目的
- architecture decision
- 参考OSSと該当source path
- 実装内容
- 手動/自動検証結果
- Windows実機確認結果
- 既知の制限
- 次工程

長期作業をローカルだけに保持しない。重要な設計変更はADRまたはroadmap更新を同じPRへ含める。

---

## 12. PR #37の扱い

`WIP: native 3D CAD-style spatial editor` (#37) は、この正本に沿う**最初の実装track**として継続する。

既に確認済み:

- PySide6 + PyVista/VTK + PyVistaQt Windows PoC
- concave polygon room描画
- speaker/MLP描画
- AffineWidget3D transform interaction
- initial ContextDraft / snap / undo-redo semantics

ただし現在のsnapshot-copy型`ContextDraft`はPoCとして扱い、N20でCommandHistory/transaction modelへ段階的に置換する。

---

## 13. 直近の実装順

1. **N10**: PR #37でnative shellを完成
2. **N20**: selection / command / gizmo / snapping foundation
3. **N30**: room CAD
4. **N40**: speaker/seat/screen/furniture placement
5. **N50**: G10 constraint visualization
6. **N60**: measurement/REW integration
7. **N70**: acoustic visualization
8. **N80**: placement optimization UI
9. **N90**: package/release

O20等の最適化backendを先に増やすより、**既存のgeometry/constraint/search結果を人間が3Dで理解・編集できる基盤を先に完成させる。**

---

## 14. Definition of Done — CAD foundation

N10〜N40を通過した時点で、以下を満たせば「HTDTの新GUI基盤が成立」と判定する。

- browserを使わずnative applicationだけでroomを作れる
- mouseでspeaker/seat/screen/furnitureを配置できる
- move/rotate gizmoが使える
- snapと数値入力を併用できる
- scene tree / viewport / inspectorが同期する
- top/front/side/perspectiveで同じDocumentを編集できる
- undo/redo/cancelが予測可能に動く
- save/reopenで同じsceneが復元する
- measurement/analysisを載せるためのrenderer非依存Documentが確立している

この基盤を満たさない状態で、GUIの見栄えだけを仕上げたり、高度な最適化backendだけを増やしたりしない。