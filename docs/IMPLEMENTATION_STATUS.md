# 実装ステータス

> 更新: 2026-09-17 / N40実装・Windows A10受入完了、PR #56 merge gate
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。旧browser/backendの詳細履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05 / N10 / N20a / N20b / N30a / N30b / N40 の技術gateを実装し、N40までWindows実機受入を通過した。**

N40はIssue #55 / PR #56で実装中の最終merge gateにあり、accepted product codeは `2e2a3f814276bc3fcd3f392addfd70a10efbe295`。GitHub Actions CI #220と、所有Windows PCでのA10 core / numeric precisionの両方がPASSしている。

| 区分 | 現在の状態 |
|---|---|
| main | N30bまでmerge済み。N40はPR #56のmerge待ち |
| N40 tracking | Issue #55 / Draft PR #56 |
| N40 accepted code | `2e2a3f814276bc3fcd3f392addfd70a10efbe295` |
| N40 CI | run #220 (`35196621511`) PASS |
| A10 core | 実Win32 mouse inputでL字室→3.0.2→seat/aim→screen/furniture→距離修正→Undo→duplicate→hide/lock→Save/reopen PASS |
| A10 precision | speaker寸法・role精密化→Save/reopen完全一致 PASS |
| first-use | 15.75 s、最終mis-selection 0、追加guidance 0 |
| native entry | `htdt-native` / `run-native.ps1` / `python -m htdt.native_cad` はN40 product compositionを起動 |
| browser UI | 新CAD機能は凍結。二重実装しない |
| 次工程 | **N50 — 制約の空間表示、G10 adapter、allowed/exclusion/通路/離隔、拒否理由overlay、A11** |

## N40 — 完了内容

### Theater object domain

- `SceneEntity`でspeaker / seat / screen / furniture / AV equipment / measurement pointを扱う。
- physical bodyのposition / orientation / dimensionsと、body-local `acoustic_reference_offset_m`を分離した。
- measurement pointは物理寸法を持たないstandalone acoustic referenceとして扱う。
- speaker roleは任意stringを保持し、3.0.2は固定schemaではなくtemplate / acceptance fixtureに限定した。
- `aim_xyz=None`はunknownを維持し、追加・移動・複製・resizeだけでは既知化しない。
- `座席へ向ける`はspeakerのacoustic axisだけを更新し、body poseを暗黙回転しない。複数speakerを1 Undo単位で更新できる。

### Command / persistence

- add / batch add / duplicate / property replacementをCommandHistoryへ統合した。
- 3.0.2 templateは1操作=1 Undo単位。
- duplicateは新stable IDを生成し、寸法・role・orientation・reference/aim semanticsを保持する。
- N40 entity dataは既存SceneRevision / SQLite経路で保存し、reopenでrole / dimensions / position / acoustic referenceを完全復元する。
- hide / lockは`EditorViewState`とrepository view stateに留め、物理SceneDocumentや測定条件へ混ぜない。

### Native UI / workflow

- 日本語優先の`オブジェクト` paletteからspeaker / seat / screen / furniture / AV equipment / measurement point / 3.0.2 templateを追加できる。
- Scene treeとviewport primitiveで種類を形状でも区別し、色だけに依存しない。
- Inspectorでphysical dimensions、speaker role、acoustic reference offsetを精密化できる。
- 既存Move/Rotate gizmo、snap、selection、Undo/Redo、hide/lockを同じ編集経路で継承する。
- N30b room/wall guardは`cad_composition.py`に残し、N40 theater behaviorを`theater_editor.py` / `theater_workflow.py`として重ねた。
- room作成成功後はobject modeへ直接戻り、初見ユーザーがtoolbar overflow内のDone操作を探さなくても次工程へ進める。再編集は既存room-edit actionから入る。
- default screenはfront speaker帯と分離し、seat / furniture / AV / measurement point / standalone speakerは初期配置laneを分けてTop viewで選択しやすくした。

### Focused verification

- physical kindのdimension invariantとmeasurement-point semantics
- body-local acoustic reference transform
- add / batch add / duplicate / property updateのUndo/Redo
- speaker explicit aimとmulti-speaker atomic Undo
- repository save/reopen exactness
- native launcher / acceptance harness compile

低影響なlabel/layout変更のための冗長なpixel testは追加していない。

## A10 Windows受入

詳細: [N40_ACCEPTANCE_2026-09-17](N40_ACCEPTANCE_2026-09-17.md)

最終受入環境:

- Windows 11 Pro build 26200
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- 2880×1800 / Windows 200% DPI
- Python 3.12.10
- PySide6 6.11.2
- PyVista 0.49.0
- VTK 9.7.0

最終結果:

```text
A10_MOUSE_L_ROOM True
A10_MOUSE_302_TEMPLATE True
A10_EXPLICIT_SEAT_AIM True
A10_MOUSE_SCREEN_FURNITURE True
A10_MOUSE_DISTANCE_CORRECTION True
A10_MOUSE_UNDO_MISTAKE True
A10_MOUSE_DUPLICATE True
A10_HIDE_VIEW_ONLY True
A10_LOCK_VIEW_ONLY True
A10_MOUSE_SAVE True
A10_REOPEN_EXACT True
A10_FIRST_USE_SECONDS 15.75
A10_MISSELECTIONS 0
A10_GUIDANCE_REQUIRED 0
A10_RESULT PASS
A10_PRECISION_RESULT PASS
PRE_STATUS_COUNT=0
POST_STATUS_COUNT=0
```

実機gate中に見つかったroom mode遷移と初期オブジェクト重なりは、acceptance harnessだけで回避せずproduct workflow側を修正した。

## 継承済みCAD基盤

- N20b: multi-select、common pivot、object/grid/angle snap、hide/lock、entity Undo/Redo。
- N30a: 凹polygon room、stable RoomVertex、頂点挿入/移動/削除、edge寸法、ceiling height、self-intersection拒否。
- N30b: stable wall ID、opening、wall clearance binding、wall move/split/merge/delete、参照migration、曖昧操作拒否、room/topology atomic transaction。
- topology作成後のroom変更はstable refsを暗黙破壊せず、許可された頂点移動/寸法/高さだけを再validateする。

実機記録:

- [N05 Windows acceptance](N05_ACCEPTANCE_2026-09-16.md)
- [N10 Windows acceptance](N10_ACCEPTANCE_2026-09-16.md)
- [N20a A05/A06](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b A07](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a A08](N30A_ACCEPTANCE_2026-09-17.md)
- [N30b A09](N30B_ACCEPTANCE_2026-09-17.md)
- [N40 A10](N40_ACCEPTANCE_2026-09-17.md)

## 次工程 — N50

N50では、N40で編集可能になったtheater sceneへ既存G10系のconstraintをadapter経由で接続し、制約をCAD空間上で理解・修正できるようにする。

- allowed / exclusion領域の表示・編集
- 通路・壁・speaker/seat等のclearance表示
- stable wall選択とconstraint参照
- 配置不可の理由をviewport / Inspectorで具体表示
- rejected candidateを無言で確定しない
- A11でWindows実機受入

N60の実測workspaceはN40後にN50と独立して進められるが、実装順の正本は`IMPLEMENTATION_ROADMAP.md`に従う。
