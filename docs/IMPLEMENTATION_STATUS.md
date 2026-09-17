# 実装ステータス

> 更新: 2026-09-17 / N30b wall・opening・参照保持・Windows A09受入反映
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。旧browser/backendの詳細履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05 / N10 / N20a / N20b / N30a / N30b の技術gateを実装・実機受入まで通過。** N30bはIssue #53 / PR #54で、stable wall topology、opening、wall clearance参照、壁move/split/merge/delete、atomic Undo/Redo、日本語優先native UI、N30a/N30b cross-tool guard、F3/A09 Windows実機受入まで完了した。PR #54は最終CI確認後にmainへmergeする。

| 区分 | 現在の状態 |
|---|---|
| main | N30aまで反映済み。N30bはPR #54がmerge待ち |
| N30b tracking | PR #54 / Issue #53 |
| N30b実機受入 | commit `5ede848e8e0b0967a50c04c83ff679a649ca439b`、Windows 11 / 実OS 200% DPIでA09 PASS |
| A09 | F3で実マウスwall選択・移動、split/merge/delete、opening/clearance追従、曖昧split拒否、Undo/RedoをPASS |
| wall domain | stable wall ID、from/to vertex参照、wall-local opening、clearance binding、thickness表示属性 |
| topology edit | move/split/merge/deleteをpure candidate editとして検証し、room+topologyを1 CommandHistory transactionで確定 |
| 保存 | SceneDocument schema v3でwall topologyをSceneRevision/SQLiteへ保存。topologyなし旧sceneのcanonical hash互換を維持 |
| native entry | `htdt-native` / `run-native.ps1` / package entry はproduct composition `CadEditorWindow` (`htdt.native_cad`) を起動 |
| GUI | 既存Editor/Room主要操作とN30b Wall操作を日本語優先表示 |
| cross-tool guard | topology作成後もroom頂点移動/寸法/高さは再validate。頂点数変更はwall split/deleteへ誘導しstable refsを暗黙破壊しない |
| N20b継承 | multi-select、common pivot、object/grid/angle snap、hide/lock、entity Undo/Redoを保持 |
| 次工程 | **N40 — theater objects、mouse主導のspeaker/seat/screen/furniture配置、A10** |

実機記録:

- [N05 Windows acceptance](N05_ACCEPTANCE_2026-09-16.md)
- [N10 Windows acceptance](N10_ACCEPTANCE_2026-09-16.md)
- [N20a A05/A06](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b A07](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a A08](N30A_ACCEPTANCE_2026-09-17.md)
- [N30b A09](N30B_ACCEPTANCE_2026-09-17.md)

## N30b — 完了内容

### Scene / wall topology

- `WallSegment`はstable `wall_id`、ordered room vertexへのfrom/to参照、wall thickness、split lineage用`source_wall_id`を保持する。
- `WallOpening`はstable `opening_id`、`wall_id`、wall始点からのoffset、width、sill、height、kind/open stateをwall-localで保持する。
- N30b用`WallConstraintBinding`はwall IDとclearance値の参照連続性だけを担当し、本格solver semanticsはN50へ分離する。
- `WallTopology`はRoomPrism境界edgeと1:1でなければ確定できず、opening/constraintのdangling参照を禁止する。
- thicknessは室内footprintを暗黙に縮めない表示属性として扱う。

### Topology edit / Undo

- wall moveは両endpointを同一XY deltaで移動し、wall/opening/constraint IDを保持する。
- splitは旧wallをretireし2子wallへ`source_wall_id`を残す。openingは包含側へ移し、clearance参照は両子wallへ追従する。
- split pointを跨ぐopeningは曖昧操作として確定拒否し、履歴を増やさない。
- mergeはordered隣接、共線、同方向、同thicknessの場合だけ成立し、opening offsetとclearance参照を新wall IDへ統合する。
- deleteは対象wallとsuccessorのopening/constraint参照が残る場合に確定拒否する。未参照時のみ明示replacement wallへ更新する。
- room geometry + wall topology + migrated referencesは`RoomWorkingDocument.replace_room_topology()`で1 commandとしてUndo/Redoされる。

### Native UI / cross-tool coordination

- wallをTop viewでクリック選択し、実マウスdragで移動できる。
- toolbarから壁分割、次壁との結合、壁削除、ドア開口追加、クリアランス参照追加を行える。
- Inspectorから壁厚と追加clearance値を数値精密化できる。
- inherited Editor/Room toolbar、Inspector、scene tree、status messageを可能な範囲で日本語化した。
- openingはviewport上にwall-local位置として表示し、selected wallを太線で識別する。
- `CadEditorWindow`がroom toolとwall toolの境界を調停する。topology作成前はN30aのroom sketch/insert/deleteが利用できる。
- topology作成後はvertex ID/orderを保つ頂点移動・edge寸法・天井高のみ既存wall/opening/constraintと再validateし、vertex数変更はwall split/deleteへ日本語statusで誘導する。
- room変更でopening/clearance条件を満たせない場合は例外をUIへ漏らさず確定拒否する。

### A09結果

所有Windows PC（Windows 11 Pro build 26200、2880×1800、200% DPI）で通常起動と同じ`CadEditorWindow`と実Win32 mouse inputを使用した。F3はF2凹8頂点room + front opening + wall clearance 0.35 m + 2 measurement points。

```text
A09_JAPANESE_UI True
A09_F3_FIXTURE True
A09_MOUSE_SELECT True wall:v1->v2
A09_MOUSE_MOVE_REFERENCES True
A09_SPLIT_REFERENCE True
A09_MERGE_REFERENCE True
A09_REFERENCED_DELETE_REJECT True
A09_AMBIGUOUS_SPLIT_REJECT True
A09_DELETE_UNREFERENCED True
A09_UNDO_REDO True
A09_RESULT PASS
A09_EXIT=0
POST_STATUS_COUNT=0
```

受入環境はPython 3.12.10 / PySide6 6.11.2 / PyVista 0.49.0 / VTK 9.7.0。受入前後のGit worktreeはcleanだった。

## N30aまでの基盤

- explicit room footprintはstable `RoomVertex(vertex_id, x_m, y_m)`、凹simple polygon、負XY、footprint由来boundsを保持する。
- room作図・頂点挿入/移動/削除・edge length・ceiling height・自己交差拒否・1操作=1 UndoはA08で受入済み。
- N20bのmulti-select、common pivot、object snap、grid/angle snap、hide/lock、entity Undo/RedoをN30bでも保持する。

## 既存の実装資産

測定・解析backend、旧browser UI、G00/G10/O10、REW read-only integration、比較・backup/restore等は削除していない。現在の方針ではbrowser UIへ新CAD機能を二重実装せず、native editorを主経路として再利用価値のあるdomain/serviceを段階的に接続する。

## 確定した実環境

| 項目 | 現在の値 | 実装上の扱い |
|---|---|---|
| OS | Windows 11 x64 | 正式な第一対象 |
| 開発/利用PC | Ryzen 7 8845HS / Radeon 780M / 31.3 GiB | CAD実機gateの基準機 |
| Display | 2880×1800 / OS 200% DPI / Qt DPR 2.0 | high-DPI mouse/pickを実機確認 |
| AVR | Yamaha RX-A4A | AVR設定は不変snapshotとして扱う |
| スピーカー構成 | 現在3.0.2 | role・本数は可変 |
| サブウーファー | なし | 現在の主要シナリオ。将来追加可能 |
| 測定マイク | miniDSP UMIK-1採用 | 48 kHz、個体別校正を前提 |
| REW | V5.40 beta 135 API版 | read-only API実接続・FR decode確認済み |

## 次工程 — N40

N40では「room/wallを編集できるCAD」から「ホームシアターを構築できるCAD」へ進める。

- speakerをrole付きtheater objectとしてmouse配置・向き調整
- seat / measurement point、screen、furniture、AV機器の作成・編集
- object palette / scene tree / Inspectorの日本語導線整理
- 3.0.2等のtemplateは入力補助に留め、固定構成にしない
- F3/N30b wall refsを壊さず保存・再open
- A10: 空project→部屋→speaker→seat/screen/furniture→保存→再openをmouse主導で完遂

N40完了後にN50 constraint/feasibilityへ進む。