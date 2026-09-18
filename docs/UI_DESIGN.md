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

## 11. Visual & interaction language

HTDTは**dark-first**で仕上げる。単に背景を黒くするのではなく、視覚階層・直接操作・feedback・motion・3D renderingを一体のsystemとして設計する。初期releaseのappearanceはdarkをauthoritativeにし、light themeはdark版がUX160を通過した後の別scopeとする。

参考原則:
- HTM: dark/light対応、real-time 3D scene、stackable overlays、Viewing/Editing mode、feature search、phase-based workflow。
- Apple HIG: dark appearanceでは背景/elevated surfaceの差で階層を作る、toolbarを過密にしない、sidebarはflatなnavigationへ限定する、重要情報に十分なspaceを与える、feedbackは状態と結果を明確にする。
- Windows native applicationとして実装するため、Apple固有asset/font/controlを模倣しない。platform-native keyboard/focus/window semanticsとWindows向けfont renderingを優先する。

### 11.1 Content first / chrome second

最も重要な情報または編集対象が最も高い視覚優先度を持つ。

優先順位:
1. room / object / plot / candidate / warningなど、ユーザーが判断するcontent;
2. current selection / current task / primary action;
3. navigation / inspector;
4. secondary metadata;
5. provenance / diagnostic / internal identifiers.

navigationやpanelがcontentより明るい・彩度が高い状態を禁止する。常設chromeは静かにし、hover / selected / warningの時だけ必要なcontrastを上げる。

### 11.2 Dark surface hierarchy

pure black一色で領域分割しない。semantic surface tokenで階層を作る。

- `surface.canvas`: 3D viewport / graph background。最も深いneutral dark。
- `surface.base`: main page background。
- `surface.raised`: sidebar / inspector / cards。
- `surface.overlay`: popover / command palette / temporary tool HUD。
- `surface.modal`: modal/sheet。backdropと明確に分離。

相対的な明度差を使い、強いborderで全componentを箱囲みしない。separatorは必要なgroup境界だけに使う。

透明・blurは**contextを残すためのtemporary overlay**に限定する。Measurementsの表、plot、長文、数値入力panelをdecorative glassにしない。読解contentは原則opaque surfaceでcontrastを安定させる。

### 11.3 Accent discipline

accent colorは「押せるもの全部」に使わない。

accent用途:
- primary action;
- current selection;
- active navigation/context;
- focus ring;
- one-off interactive affordance.

semantic data/state colorはaccentと分離する。

- measured;
- predicted;
- selected/current;
- warning;
- error;
- unsupported;
- stale;
- acoustic heatmap/scientific colormap.

同じ色を別の意味に再利用しない。色だけで状態を伝えず、icon / line style / badge textを併用する。

### 11.4 Typography and numeric presentation

Windowsではplatform UI fontを基本にし、`Segoe UI Variable` が利用可能なら第一候補とする。AppleのSF系fontをbundle/模倣しない。

階層は少数に固定する。

- workspace title;
- section title;
- body/control label;
- secondary/metadata;
- numeric/readout.

page titleを大きくしすぎず、desktop appとして情報密度を保つ。重要数値は周囲の説明文より読み取りやすくする。寸法、周波数、dB等で桁が揺れる場合はtabular numeral相当を評価する。

boldを状態表現に乱用しない。secondary textのcontrastを落としすぎてdark background上で読めなくしない。

### 11.5 Spacing, shape and control rhythm

ad-hoc marginを禁止し、token化する。

初期token候補（UX150で実機調整してfreeze）:
- spacing: 4 / 8 / 12 / 16 / 24 / 32 logical px;
- compact control: 約28–30 px;
- standard control: 約32–36 px;
- primary/prominent control: 約38–42 px;
- small / standard / large radiusの3段階以内.

全controlをpill/rounded cardにしない。shapeはhierarchyの補助であり装飾ではない。隣接panel・button・popoverのcorner geometryに一貫性を持たせる。

### 11.6 Direct manipulation and continuity

「設定してApply」より、可能な範囲で**対象を直接操作し、即座にpreviewし、確定・取消できる**ことを優先する。

- drag中はghost / delta / snap targetを即時表示;
- inspector数値変更も同じCommand lifecycleへ接続;
- hover / pressed / selected / disabled / focusを見た目で即座に区別;
- selection変更でInspectorの場所を飛ばさず、同じ領域でcontentだけ更新;
- workspace移動後に元のselection/contextへ戻れる;
- Undo可能な操作を不用意なconfirmation dialogで止めない;
- destructive/evidence-changing actionだけ明確なconfirmationを使う.

### 11.7 Motion

motionは装飾ではなく**因果関係とcontinuityの説明**に限定する。

使う:
- sidebar / inspectorのopen-close;
- selectionによるcontext panel更新;
- page/sub-context transition;
- popover / command palette;
- applied candidateのpreview -> commit;
- warning / completion feedback.

使わない:
-常時 pulsing/glowing;
- bounce/springを標準feedbackにする;
- large plot/3D objectを意味なくanimateする;
- compute待ちで画面全体をblockする.

初期duration目安:
- micro state: 100–160 ms;
- panel/context transition: 160–220 ms;
- page transition: 180–240 ms.

値はUX150で体感評価してfreezeする。animationはinterruptibleにし、Reduce Motion相当の設定または簡略modeを用意できる構造にする。

### 11.8 Responsiveness and perceived latency

操作感はframe rateだけでなく**入力に対する即時feedback**で評価する。

- click/selectionは100 ms以内のfeedback targetを維持;
- drag/orbitは既存p95 frame time <=33 ms targetを維持;
- long compute開始時は即座にqueued/running stateを出す;
- blocking spinnerでapplication全体を止めない;
- compute中もnavigation/viewport inspection/cancelを可能な範囲で維持;
- slow operationはprogressとcancelを同じ場所に置く;
- stale resultを遅れてcurrentとして表示しない.

### 11.9 Empty, loading, blocked states

空panelを置かない。

empty stateは:
-何が無いか;
- なぜ必要か（必要な場合のみ）;
- primary next action 1個;
- optional secondary action.

blocked stateはdisabled controlだけで終わらせず、近接位置に短い理由と解消actionを出す。

### 11.10 Dark 3D viewport

Room 3DはHTM同様、UI shellと連続したdark appearanceを持つ。ただしsceneの可読性を最優先する。

基本:
- neutral graphite/charcoal系background。pure black voidを避ける;
- floor/gridは低contrast。gridがroom geometryより目立たない;
- room surfaceは低彩度neutral material;
- wall/floor/ceilingの面向きが分かる程度のsoft lighting;
- soft key + fill + ambientを基本にし、harsh specularや過度なphotorealismを避ける;
- contact/ground cueを用いてobjectが浮いて見えないようにする;
- selected objectはsurface色変更だけでなくoutline/handleで示す;
- gizmo axisは識別可能だがsceneの主役にならない;
- labelは必要時だけ表示し、常時大量labelで埋めない;
- screen/projector cone / speaker coverage / reflection / mode / field等のoverlayはbase geometryとは別のvisual layerとして管理.

Editing / Viewing / Analysisでoverlay密度を変える。全overlayを同時表示できても、defaultは必要最小限とする。focus modeでProjection only / Acoustics only / Cabling only等へ切り替え可能なarchitectureを維持する。

### 11.11 Scientific visualization in dark mode

FR、waterfall、heatmap、mode map等は「綺麗なneon」にしない。

- backgroundとgridのcontrastを抑える;
- primary traceを明確にし、secondary traceはline weight/opacityで後退;
- predicted / measuredを色だけでなくline style/badgeでも区別;
- perceptually ordered colormapを使い、selection accentとscientific scaleを混用しない;
- warning colorをheatmapの通常値へ流用しない;
- cursor/selected frequency/seat等はcrosshair + labelで明確にする.

### 11.12 Inspector and floating controls

Inspectorはselection-dependentで、同じ位置に留まりcontentだけ更新する。大量fieldを最初から見せず、Basic / Acoustic / Advanced等のdisclosureを使う。

3D上のfloating controlは小さく保つ。viewportを覆う大型HUDを作らない。頻繁にtypingするfieldはfloating HUDではなくInspector側へ置く。

### 11.13 Interaction density

一画面にprimary actionを複数競合させない。

- 1 context = 1 dominant next action;
- toolbarは頻繁な操作のみ;
- rare actionはMore / context menu;
- sidebarはnavigation;
- inspectorはselection property;
- command paletteは場所を知らない時のescape hatch.

同じactionをtoolbar、dock、card、context menuへ無秩序に重複させない。重複させる場合はkeyboard shortcutとcontext menuのように役割が明確な場合に限定する。

### 11.14 Reference guidance

設計判断の参考:
- Apple HIG Dark Mode: https://developer.apple.com/design/human-interface-guidelines/dark-mode
- Apple HIG Layout: https://developer.apple.com/design/human-interface-guidelines/layout
- Apple HIG Sidebars: https://developer.apple.com/design/human-interface-guidelines/sidebars
- Apple HIG Toolbars: https://developer.apple.com/design/human-interface-guidelines/toolbars
- Apple HIG Feedback: https://developer.apple.com/design/human-interface-guidelines/feedback
- Apple HIG Searching: https://developer.apple.com/design/human-interface-guidelines/searching

これらはWindows上でApple UIを再現する仕様ではなく、content priority、hierarchy、feedback、navigation densityの判断材料として使う。

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
- dark-first theme/design token foundation
- semantic surface / accent / typography / focus state

### UX120 — Room
- viewport-centric dark 3D workspace
- contextual tools
- selection Inspector
- object palette
- neutral scene lighting / low-contrast grid / selection outline
- overlay layer/focus mode
- permanent toolbar/dock削減

### UX130 — Measurements
- import -> assign -> quality -> compare
- plots/cards/tablesをpage layout化

### UX140 — Optimize
- Setup / Candidates / Compare / Measure-Validate
- current monolithic right scroll panelを廃止

### UX150 — visual / motion / perceived-quality polish
- dark-first appearanceをauthoritativeにfreeze
- spacing/alignment/typography/surface/accent token統一
- 3D lighting/grid/material/overlay visual tuning
- hover/pressed/focus/disabled/selected feedback
- motion duration/easing/interruptibility
- 1280×800 / 1440×900
- 100 / 150 / 200% DPI
- keyboard/focus/hit targets
- scientific plot dark-mode readability

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
