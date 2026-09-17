# 実装ステータス

> 更新: 2026-09-17 / N50実装・Windows A11受入完了、PR #60 merge待ち、次工程N60
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。旧browser/backendの詳細履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05 / N10 / N20a / N20b / N30a / N30b / N40 / N50 の技術gateを実装し、N50までWindows実機受入を通過した。**

N50はIssue #59 / PR #60で実装完了。最終A11はbranch head `a8ba8d0507c404a9058c0ffe12475fce4dca968c` でPASSし、最後のproduct-code変更 `8762c5e15c1f8c9442ce6ef6378f24881e0f5236` はGitHub Actions CI #238 / run `35201888464` で全項目PASSした。現在はPR #60のmerge待ち。

| 区分 | 現在の状態 |
|---|---|
| main | **N40までmerge済み**。N50 PR #60 は受入完了・merge待ち |
| N50 tracking | Issue #59 / PR #60 |
| N50 accepted runtime head | `a8ba8d0507c404a9058c0ffe12475fce4dca968c` |
| N50 last product-code head | `8762c5e15c1f8c9442ce6ef6378f24881e0f5236` |
| N50 CI | #238 / run `35201888464` PASS |
| A11 | 実Win32 mouse inputで壁離隔違反・通路違反→拒否→理由選択→対象/距離/壁/領域表示→通常編集復帰 PASS |
| wording | feasibilityは`制約を満たす / 制約違反`のみ。音質評価・ランキングへ変換しない |
| native entry | `htdt-native` / `run-native.ps1` / `python -m htdt.native_cad` はN50 `ConstraintEditorWindow` compositionを起動 |
| browser UI | 新CAD機能は凍結。二重実装しない |
| 次工程 | **N60 — 実測workspace、REW読取/取込、SceneRevision↔測定点、FR dock、ghost配置、比較、A12/A13** |

## N50 — 完了内容

### Constraint domain / G10 adapter

- 既存`placement_constraints.py`をG10 placement feasibility authorityのまま再利用し、solverを複製しない。
- native側にallowed region / exclusion・walkway / wall clearance / pair distanceのimmutable constraint modelを追加した。
- `SceneDocument` / `WallTopology`をG10 Context/ConstraintSetへ写す純粋adapterを追加した。
- stable N30b `wall_id`を永続参照とし、legacy `from_vertex_id->to_vertex_id` edge IDは評価時だけ生成する。
- physical bodyは現行G10 envelopeへ保守的な水平外接半径で写し、exact mesh collisionとは表示しない。
- typed evaluation resultへsubject、wall/region、reason、actual、requiredを戻す。

### Native UI / interaction

- N40 product workflowの上に`ConstraintEditorWindow`を重ね、通常native launcherへ接続した。
- 日本語優先`制約` dockで制約状態、理由一覧、actual/required、authoring controlsを表示する。
- allowed/exclusion regionを面＋線/パターンで表示し、色だけに依存しない。
- violation選択時にsubject、counterpart wall/object/region、distance segment、rejected candidateをviewport上で強調する。
- object move previewは既存N20/N40 transform pathをそのまま使い、release前にG10 evaluationを行う。
- 新規hard violationまたは既存scalar violationの悪化はcommitせず、元poseへ戻して具体的理由を残す。
- 既存region violationから脱出する途中の移動は許可し、invalid stateに物体を閉じ込めない。
- full N50 constraintが参照するentity削除や曖昧なwall split/merge/deleteは無言で移行せず明示拒否する。

### Persistence / state boundary

- constraint定義はsceneと同じSQLite内のdocument-scoped authoring workspaceとして保存する。
- constraint evaluation resultは派生値でありauthorityとして保存しない。
- hide/lockは`EditorViewState`のままでconstraint feasibility入力に混ぜない。
- N50では既存SceneRevision hash contractを変更しない。N60/N70の非同期jobはSceneRevisionだけでなく、その時点のconstraint workspace hash/snapshotも入力として固定する必要がある。

### Focused verification

- HTDT座標→G10 mapping
- rectangular body→conservative envelope radius
- stable wall ID↔legacy edge mapping（split後を含む）
- wall/walkway rejectionのreason/actual/required mapping
- position overrideがsceneをmutateしないこと
- unknown wallを推測せず拒否すること
- constraint workspace round-trip
- candidate commit blocking policy
- hide/lock変更でfeasibilityが変わらないこと
- A11 Windows harness compile

pixel/color snapshotのような低価値testは追加していない。

## A11 Windows受入

詳細: [N50 Windows acceptance](N50_ACCEPTANCE_2026-09-17.md)

最終受入環境:

- Windows 11 Pro build 26200
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- Radeon driver 32.0.13032.11
- 2880×1800 / Windows 200% DPI
- Python 3.12.10
- PySide6 6.11.2
- PyVista 0.49.0
- VTK 9.7.0

最終結果:

```text
A11_PRODUCT_COMPOSITION True
A11_INITIAL_FEASIBLE True
A11_MOUSE_WALL_REJECT True
A11_MOUSE_WALL_REASON True
A11_MOUSE_WALKWAY_REJECT True
A11_MOUSE_WALKWAY_REASON True
A11_EDIT_AFTER_REJECT True
A11_CONSTRAINT_PERSISTENCE True
A11_QUALITY_WORDING_ABSENT True
A11_RESULT PASS
A11_EXIT=0
PRE_STATUS_COUNT=0
POST_STATUS_COUNT=0
```

## 継承済みCAD基盤

- N20b: multi-select、common pivot、object/grid/angle snap、hide/lock、entity Undo/Redo。
- N30a: 凹polygon room、stable RoomVertex、頂点挿入/移動/削除、edge寸法、ceiling height、self-intersection拒否。
- N30b: stable wall ID、opening、wall clearance binding、wall move/split/merge/delete、参照migration、曖昧操作拒否、room/topology atomic transaction。
- N40: speaker / seat / screen / furniture / AV equipment / measurement point、3.0.2 template、duplicate、寸法、acoustic reference、explicit aim、A10。

実機記録:

- [N05 Windows acceptance](N05_ACCEPTANCE_2026-09-16.md)
- [N10 Windows acceptance](N10_ACCEPTANCE_2026-09-16.md)
- [N20a A05/A06](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b A07](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a A08](N30A_ACCEPTANCE_2026-09-17.md)
- [N30b A09](N30B_ACCEPTANCE_2026-09-17.md)
- [N40 A10](N40_ACCEPTANCE_2026-09-17.md)
- [N50 A11](N50_ACCEPTANCE_2026-09-17.md)

## 次工程 — N60

ロードマップ上の次工程はN60実測workspace。

- REW読取/取込をnative workspaceへ接続する。
- measurementを不変なSceneRevisionと測定点へ対応付ける。
- FR dockを追加し、保存済み実測と現在sceneを同じworkspaceで確認する。
- 過去配置はghostとして現在配置と明確に区別する。
- revision A/Bの比較でAの測定条件を不変に保つ。
- job開始後の編集・cancel・project変更に対してstale/取消結果を現在sceneへ自動適用しない。
- A12 / A13をWindows実機gateとする。

N50とN60はN40後に独立可能だが、正本の実装順に従いN50完了後にN60へ進む。
