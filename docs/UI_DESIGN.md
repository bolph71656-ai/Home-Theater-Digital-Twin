# Native CAD UI / Interaction Design

> 改訂: 2026-09-18 / Issue #118 workflow-first UI/UX overhaul
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)、編集・保存契約は[SPEC](CAD_EDITOR_SPEC.md)、判定は[受入仕様](CAD_EDITOR_ACCEPTANCE.md)。
> 本書は従来の「viewportを常に主画面＋dock追加」方針を置き換える。

## 1. 設計問題と変更方針

現行native GUIは機能を追加するたびに `QToolBar` / `QDockWidget` / tree / formを継承階層へ足してきたため、最終workspaceで認知負荷とlayout競合が増えている。

現行composition:

~~~text
NativeEditorWindow
  -> RoomEditorWindow
  -> WallEditorWindow
  -> CadEditorWindow
  -> TheaterEditorWindow
  -> TheaterWorkflowWindow
  -> ConstraintEditorWindow
  -> MeasurementEditorWindow
  -> MeasurementWorkspaceWindow
  -> PredictionWorkspaceWindow
  -> OptimizationWorkspaceWindow
~~~

問題は配色ではなく**information architecture**である。今後は「機能追加=新dock」ではなく、task単位のworkspaceとprogressive disclosureで構成する。

## 2. UX benchmark — Home Theater Maestro

HTMの公開UI/Live Demoをworkflow benchmarkとして参照する。画面・asset・codeをコピーせず、以下の設計原則を抽出する。

Official references:
- https://hometheatermaestro.fr/en/
- https://hometheatermaestro.fr/en/features.html
- https://hometheatermaestro.fr/demo/?lang=en

Official screenshots:
- Room / 3D: https://hometheatermaestro.fr/images/screens/salle-complex-en.png
- Acoustics: https://hometheatermaestro.fr/images/screens/acoustique-en.png
- Measurements: https://hometheatermaestro.fr/images/screens/audio-en.png
- Overview: https://hometheatermaestro.fr/images/screens/synthese-en.png

参考にする点:

- global navigationを少数のdestinationに限定する。
- Room内だけでcontext navigationを出し、全機能を一つのtoolbarへ並べない。
- Overviewは状態一覧ではなく「次に何を直すか」を優先順に出す。
- 3DはRoom/Placementでは主役だが、Measurements/analysisまで無理にdockへ押し込まない。
- Advanced/provenance/internal IDは必要時だけ開示する。
- Measurementsはimport -> assignment -> quality -> comparisonと上から読めるpage構造にする。
- feature search / command paletteを持ち、場所を記憶しなくても操作へ到達できる。
- page title / section / card / field / badgeのvisual hierarchyを全画面で統一する。

## 3. Top-level information architecture

HTDTのuser-facing navigationはdomain/service境界ではなくtaskで構成する。

~~~text
Project
├─ Overview
│   ├─ current room/system summary
│   ├─ readiness / blockers
│   ├─ recent measurement / prediction
│   └─ next actions -> deep link
│
├─ Room
│   ├─ Geometry
│   ├─ Objects
│   ├─ Speakers & seats
│   ├─ Materials / acoustic participation
│   └─ Acoustics / spatial overlays
│
├─ Measurements
│   ├─ Import / acquire
│   ├─ Assignment
│   ├─ Quality / timing capability
│   └─ Predicted vs measured
│
├─ Optimize
│   ├─ Search setup
│   ├─ Candidates
│   ├─ Objectives / Pareto
│   ├─ Measurement plan
│   └─ Validation / adaptive
│
└─ Help / Settings
~~~

Predictionを単独global destinationとして固定しない。

- spatial prediction -> Room / Acoustics
- predicted-vs-measured -> Measurements
- candidate batch prediction -> Optimize

とし、同じresult authorityをtask context別に見せる。

## 4. Shell

### Left rail

常設するもの:

- project selector + save state
- feature search / `Ctrl+K`
- Overview
- Room
- Measurements
- Optimize
- Help / Settings at bottom

global destinationは原則4〜5個以内。icon-onlyを既定にせず、short labelを併記する。必要ならrail自体をcollapseできる。

### Top context bar

現在workspace内のsub-contextとprimary modeだけを表示する。

例:

- Room: Geometry / Objects / Speakers / Acoustics
- Measurements: Import / Assign / Compare
- Optimize: Setup / Candidates / Pareto / Validate

Editor / Room / Wall / Object / Audio等の複数toolbarを常時併置しない。

### Main content

- Overview: summary / blockers / next actions
- Room: viewport-centric
- Measurements: page / plot / table-centric
- Optimize: candidate / comparison / chart-centric

**viewportを全画面で常に主役にする旧方針は撤回する。** 3Dが意思決定に必要なworkspaceでのみ主役にする。

### Right contextual inspector

selectionまたはactive taskに応じて必要なpropertiesだけ表示する。

- object selected -> transform / dimensions / acoustic role
- wall selected -> geometry / opening / material
- speaker selected -> role / pose / aim / source model

Constraint / Measurement / Prediction / Optimizationをpermanent dock tabとして常設しない。

### Bottom/status

短い状態だけ:

- saved / unsaved / stale
- units
- snap state
- active compute / cancel
- concise tool hint

長い説明、tree、設定formは置かない。

## 5. Overview / guided workflow

Overviewはnavigation authorityを持つ。

表示例:

- Room geometry incomplete -> Complete room geometry
- Speaker role unknown -> Assign speaker roles
- No measurement -> Import REW measurement
- Measurement is magnitude-only -> Timing/phase validation unavailable
- Prediction stale -> Re-run prediction
- Validation blocked -> reason + deep link

各actionはworkspace/entity/subsectionへdeep-linkする。

初回projectの軽いguided path:

1. Room
2. Speakers / seats
3. Measurements (optional)
4. Predict / analyze
5. Optimize

wizardで入力を強制せず、常にOverviewへ戻れる。

## 6. Command palette / feature search

`Ctrl+K` から以下を検索できる。

- navigation destination
- common command
- entity
- task: Draw room / Add speaker / Import REW / Run prediction / Compare candidates
- settings / help

検索結果はcurrent contextとavailabilityを反映し、disabledの場合は短い理由を表示する。

## 7. Room workspace

Roomだけは3D viewportを主作業領域にする。

### Contextual controls

表示するのはactive sub-contextに必要なものだけ。

Geometry:
- draw/edit room
- vertex/wall/opening tools
- dimensions

Objects:
- add palette
- move/rotate/duplicate
- hide/lock

Speakers & seats:
- role/template
- pose/aim
- placement constraints

Acoustics:
- materials/acoustic participation
- prediction overlay
- reflection/field layer controls

### Direct interaction

| 入力 | 動作 |
|---|---|
| 左click | 物体選択。空白clickで解除 |
| Ctrl＋左click | 選択を追加/解除 |
| 選択後の左drag | handle/active planeで変形 |
| 中button drag | pan |
| 右button drag | orbit |
| wheel | cursor近傍を基準にzoom |
| 右click | context menu。active edit中はcancel optionを優先 |
| Esc | active操作をcancel。Idleではselection/toolを安全な状態へ |
| Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y | Undo / Redo |
| Ctrl+S / Delete / Ctrl+D | Save / Delete / Duplicate |
| F / Home | selection fit / scene fit |
| X/Y/Z | transform axis constraint |
| Shift | precision move |
| Alt | snap一時反転。Windows menu競合があれば再割当 |

textbox focus中は文字入力を優先する。

### Feedback

| 状態 | 表示 |
|---|---|
| Hover | weak outline + name |
| Selection | clear outline + handle + Inspector sync |
| Drag | ghost position + delta + active axis + snap marker |
| Invalid geometry | exact edge/vertex + short reason; commit disabled |
| Constraint violation | offending entity + clearance line + reason |
| Unknown aim | unknown badge; fake arrowを出さない |
| Unsaved/save failed | project title area |
| Historical/stale result | ghost/line/badgeでcurrentと区別 |

色だけに意味を持たせずshape/line/labelを併用する。

## 8. Measurements workspace

Measurementsは巨大右dockではなくpageとして設計する。

推奨順序:

1. Import / acquire
2. Assign to speaker / receiver / SceneRevision
3. Quality and capability
4. Predicted vs measured
5. Detailed plots / advanced metadata

主画面にはmeasurement name、channel/seat、measured badge、quality warnings、主要plotを見せる。

通常画面へUUID、raw hash、repository row IDを出さない。必要なprovenanceはAdvanced drawer。

measurementとsceneの相互selectionは維持し、必要なら小さい3D context/ghostを補助表示する。

## 9. Optimize workspace

現行一枚scroll panelを廃止し、少数のsub-contextへ分ける。

### Setup
- movable entities
- bounds / constraints
- objective selection
- model / valid band

### Candidates
- list/table + spatial preview
- filter
- failure reason

### Compare
- objective vectors
- Pareto
- selected candidate A/B
- confidence/uncertainty

### Measure / Validate
- MeasurementPlan
- campaign assignment
- residual / holdout
- adaptive next action

Advanced:
- candidate hashes
- algorithm/seed
- solver backend
- internal provenance

## 10. Progressive disclosure

Standard view:
- primary task
- primary result
- actionable warning
- next action

Advanced view:
- solver/model IDs
- hashes/provenance
- exact numerical settings
- expert diagnostics

rare/dangerous actionsはMore (…)またはcontext menuへ置く。確認dialogはirreversibleまたはevidence semanticsが変わる場合に限定する。

## 11. Visual system / design tokens

screenごとのad-hoc stylesheetをやめ、共通tokenを持つ。

最低限:

- spacing scale
- control heights
- typography hierarchy
- surface levels
- border/separator strength
- card/panel radius
- icon sizes
- focus/hover/selection
- semantic badge: measured / predicted / stale / warning / error / unsupported
- compact / comfortable density

まず一つのthemeを完全に仕上げる。dark/light両方を同時に中途半端に作らない。

HTMはdark UIでも情報階層が明瞭だが、HTDTはHTMの色やassetをコピーする必要はない。重要なのはspacingとhierarchyの一貫性である。

## 12. Layout stability

- fixed/minimum heightを常用しない。
- nested scrollを最小化する。
- page-level scrollを優先する。
- form label width / baseline alignmentを統一する。
- 1280×800 logical pxを最低target。
- 1440×900を標準確認条件。
- 100 / 150 / 200% DPI。
- clipping / overlap / inaccessible control / accidental horizontal scrollを禁止。
- saved dock/splitter stateが壊れた場合はsafe defaultへ戻せる。
- current screen geometryを超えるwindow stateを復元しない。

## 13. Precision input / geometry

寸法はmm/cm/mを入力可能とし内部mへ変換する。未丸め値を保存する。

Inspectorは対象ごとに必要最小限のfieldを表示する。multi-selectで異なる値はmixed stateとし、一つの値で無言に上書きしない。

Room editではvertex / edge midpoint handle、live dimension、opening/wall relationをscene内で扱う。CSV頂点列やID入力を主要導線にしない。

## 14. Constraints / evidence semantics

UI簡略化のためにdomain authorityを弱めない。

- feasible = 音が良い、ではない。
- measured / predicted / derived / hypothesisをbadgeとtextで区別する。
- model valid band / approximation / staleを判断に必要な場所で隠さない。
- phase/timing capabilityが無いmeasurementから強いclaimへ昇格しない。
- old measurementは元SceneRevisionへbindingしたまま表示する。

## 15. Issue #118 implementation slices

### UX100 — information architecture freeze
- current task/control inventory
- top-level/sub-context/deep-link schema
- primary/contextual/advanced分類
- current UI screenshot inventoryとlayout failure catalog

### UX110 — shell
- left rail
- Overview
- workspace router
- context bar
- command palette
- theme/design token foundation

### UX120 — Room
- viewport-centric Room workspace
- contextual tools
- selection Inspector
- object palette
- permanent toolbar/dock削減

### UX130 — Measurements
- import -> assign -> quality -> compare
- plots/cards/tablesをpage layout化

### UX140 — Optimize
- Setup / Candidates / Compare / Measure-Validate
- current monolithic right scroll panelを廃止

### UX150 — visual polish / DPI
- spacing/alignment/typography/token統一
- 1280×800 / 1440×900
- 100 / 150 / 200% DPI
- focus/keyboard/hit targets

### UX160 — first-use / visual acceptance
- first-use walkthrough
- screenshot evidence
- discoverability audit
- Windows owned-PC acceptanceを最後にまとめる

R100B solver bakeoffはUI非依存なので並行可能。**R110以降で新しいacoustic inputを旧dock architectureへ追加しない。**

## 16. Visual QA

visual approvalは「綺麗に見える」だけで合格にしない。

確認するもの:

- primary actionが見つかるか
- どのworkspaceにいるか分かるか
- next actionが分かるか
- clipping/overlapが無いか
- same control typeがsame size/alignmentか
- warning/state badgeの意味が一貫するか
- mouse/keyboard/focusが破綻しないか
- UI整理後もSceneRevision/evidence authorityが変わらないか

Windows実機visual acceptanceはUX160でRDCをまとめて使う。計画・構造レビューではRDCを使わない。

旧browser UIの記録は履歴として残すが、native GUIの合格証拠へ流用しない。
