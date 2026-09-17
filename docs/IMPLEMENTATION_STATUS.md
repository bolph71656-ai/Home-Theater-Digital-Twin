# 実装ステータス

> 更新: 2026-09-17 / N30a room sketch・Windows A08受入反映
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。詳細な旧browser/backend実装履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05 / N10 / N20a / N20b / N30a の技術gateは通過。** N30aはIssue #51 / PR #52で、空sceneからの凹polygon room作図、頂点編集、寸法・高さ、bounds自動更新、Undo/RedoとA08 Windows実機受入まで完了した。

| 区分 | 現在の状態 |
|---|---|
| main | N30aまで反映済み。PR #52 merge `3a5db7f5c0101644e9e9a1271157f5756d4f88b3` |
| N30a tracking | PR #52 / Issue #51（完了） |
| N30a実機受入 | Windows 11 / 実OS 200% DPIでA08 pass |
| A08 | F2を空sceneから8 clickで作図、midpoint挿入、vertex drag、edge寸法、天井高、削除、invalid拒否、Undo/Redoをpass |
| room domain | stable vertex ID、凹simple polygon、負XY、footprint由来bounds、self-intersection拒否 |
| room edit | Top view sketch、vertex/midpoint handle、数値X/Y・edge length・height、1操作=1 Undo |
| 保存 | SceneDocument schema v2 roomをSceneRevision/SQLite/recoveryへ保存。旧F1矩形canonical hash互換を維持 |
| native entry | `htdt-native` / `run-native.ps1` / package entry はN30a `RoomEditorWindow` を起動 |
| N20b継承 | multi-select、common pivot、object snap、grid/angle snap、hide/lock、entity Undo/Redoを保持 |
| 次工程 | **N30b — wall / opening、stable wall ID、split/mergeと参照保持、A09** |

実機記録:

- [N05 Windows acceptance](N05_ACCEPTANCE_2026-09-16.md)
- [N10 Windows acceptance](N10_ACCEPTANCE_2026-09-16.md)
- [N20a A05/A06](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b A07](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a A08](N30A_ACCEPTANCE_2026-09-17.md)

## N30a — 完了内容

### Scene / room model

- `SceneDocument.room` は空sceneでは`None`を許可し、room作成後はpolygon prismを保持する。
- explicit footprintは順序付き`RoomVertex(vertex_id, x_m, y_m)`で保存する。
- `make_polygon_room()`がShapely simple-polygon validationを通し、自己交差・重複・非有限値を確定前に拒否する。
- width/depthはreference box入力ではなくfootprint boundsから導出する。
- 新Sceneでは負座標を許可する。
- legacy F1矩形は`footprint_vertices`をcanonical JSONから省略し、N05/N10/N20の保存hash互換を維持する。

### Editor interaction

- `Draw Room`でTop orthographicへ移り、clickで頂点、始点clickまたはEnterでclose、Escでcancelする。
- room editではvertex handleとedge midpoint handleを表示する。
- midpointからvertexを挿入し、vertexをmouse dragまたはInspector X/Yで移動できる。
- edge lengthを数値指定すると終点を同方向へ移動して精密化する。
- ceiling heightを数値編集できる。
- vertex deleteは3頂点未満を拒否する。
- provisional invalid geometryはpreviewに留め、SceneRevisionへ確定しない。
- room変更は`RoomWorkingDocument`のCommandHistoryへ1操作=1 commandとして入り、Undo/Redoできる。

### A08結果

所有Windows PC（2880×1800 / 200% DPI / Qt DPR 2.0）で実Win32 mouse inputを使用した。

```text
A08_DRAW_F2 True HISTORY 1
A08_INSERT_VERTEX True
A08_MOVE_VERTEX True
A08_EDGE_DIMENSION True
A08_HEIGHT True 2.6
A08_DELETE_VERTEX True HISTORY 6
A08_INVALID_REJECT True HISTORY 6
A08_UNDO_REDO True
A08_RESULT PASS
A08_EXIT=0
```

200% DPIではVTK physical display pixelとQt logical pixelを混在させない。floor/sketch targetとroom handle targetの座標経路を受入harnessで分離し、room handleは製品側 `_project_room_to_qt()` と同じlogical-pixel projectionで検証した。

## 既存の実装資産

N30a以外の測定・解析backend、旧browser UI、G00/G10/O10、REW read-only integration、比較・backup/restore等は削除していない。詳細な実装履歴と契約は[archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)と各仕様書を参照する。

現在の方針ではbrowser UIへ新CAD機能を二重実装しない。native editorを主経路とし、旧backend/serviceから再利用価値のあるdomain/serviceだけ段階的に接続する。

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

## 次工程 — N30b

N30a完了をwall編集完成とは扱わない。次はロードマップどおりN30b / A09を実装する。

- stable `wall_id` とvertex参照
- openingのwall-local配置
- wall thicknessの表示属性
- wall move / split / merge / delete
- opening・constraint参照のtransactional migration
- 曖昧なsplit/mergeは確定停止して解決を要求
- Undoでwall ID、opening、constraint参照を一括復元
- F3 / A09 Windows実機受入

N30b完了後にN40 theater objectsへ進む。