# 実装ステータス

> 更新: 2026-09-18 / N80a・O30/O40 core・O20 Room Simulator transaction+persistence実装・owned-Windows writable acceptance PASS / N80継続
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。旧browser/backendの詳細履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05 / N10 / N20a / N20b / N30a / N30b / N40 / N50 / N60 / N70 / N80a はmainへmerge済み。N80ではさらにO30/O40 objective/Pareto coreとO20 REW Room Simulator position transactionまでmainへmerge済みで、immutable batch result/persistence・native比較UI・measurement loopを継続する。**

N70はIssue #63 / PR #64で完了済み。N80aはIssue #65の部分sliceとしてPR #66からmerge commit `7473bb3efdbc511369c9a023b0b210eb5cde3553` でmainへ反映済み。Issue #65はN80b/cのためopenのまま維持する。N80a最終製品コード変更は `c6cc15e76edbc1ac263911ee084803ca1e32b42c`、accepted gate/headは `ff4dc8078eb9ca0b3effaed66b523cff175fea1a`。

| 区分 | 現在の状態 |
|---|---|
| main | **N80 O20 transactionまでmerge済み**。PR #70 merge `b4381f4b01683bba65b3857514ea583160f0eb7b` / PR #71 merge `cdbd0f45f8c66b01522fcc3006b8019e2cd1ba88` |
| N80 tracking | Issue #65（open） / Issue #67（O20 open） / PR #66・#70・#71 merged |
| N80a last product-code head | `c6cc15e76edbc1ac263911ee084803ca1e32b42c` |
| N80a accepted gate head | `ff4dc8078eb9ca0b3effaed66b523cff175fea1a` |
| N80a product CI | #321 / run `35280237062` PASS |
| N80a acceptance docs CI | #324 / run `35286052855` PASS |
| N70 tracking | Issue #63 / PR #64（完了） |
| N70 last product-code head | `76c21eed7d7efcff23905e8af977854669df2752` |
| N70 accepted gate head | `2a6eaae351beb8b2cbbef23a07e3054bb4fb1c93` |
| acceptance docs head | `bff12d4a379a5458f7dcf6cfa7e2b55b570ea4ec` |
| product CI | #309 / run `35270706491` PASS |
| final harness CI | #312 / run `35272332747` PASS |
| acceptance docs CI | #313 / run `35276546531` PASS |
| A13 | stale、UI responsiveness、明示cancel、document change、clean close/no worker PASS |
| A14 | 8頂点L-room、rectangular-only model=`unsupported`、無silent approximation、overlayなし、scalar control gated PASS |
| F5 | 50 editable objects＋10,000 markers、1 non-pickable actor、初回11.406 ms、orbit p95 27.963 ms PASS |
| native entry | `htdt-native` / `run-native.ps1` / `python -m htdt.native_cad` はN80a `OptimizationWorkspaceWindow` compositionを起動 |
| browser UI | 新CAD機能は凍結。二重実装しない |
| 次工程 | **N80 — 最適化workspace** |

## N70 — 完了内容

### Prediction authority / persistence

- prediction resultをexact native `SceneRevision`、scene content hash、model ID/version、canonical parameters、canonical input snapshotへimmutable bindingする。
- 完了結果のrequest identityをsubmission時identityと照合し、入力取り違えを保存しない。
- measured evidence、prediction、仮説を同じ証拠種別として扱わない。
- legacy `Context`をnative prediction authorityへ昇格させない。

### Geometry compatibility

- axis-aligned rectangular roomは既存のroom-mode / first-order image-source geometryをnative Sceneへadapter接続する。
- 非矩形polygon roomへ矩形専用modelを無言で適用しない。
- F2の8頂点L-roomでは`unsupported`を明示保存し、mode/reflection payloadやoverlayを生成しない。
- 将来rectangular approximationを使う場合は、exact polygonとは別にapproximation rule/error/useを明示保存する。

### Native prediction workspace

- 日本語`予測` dockを既存right-side CAD tab stackへ統合した。
- saved prediction history、model/assumption/compatibility/input revisionを表示する。
- direct path、first-order reflection path/pointはnon-pickable analysis overlayとして表示する。
- room-mode frequency候補はpredicted geometryとして表示し、空間SPL fieldと偽装しない。
- validated scalar fieldが存在する場合だけheatmap/slice/volume controlを有効化する。

### Async stale/cancel boundary

- prediction計算はGUI thread外で実行する。
- job tokenはsubmission時のdocument/revision/content hash/model/inputを固定する。
- edit、cancel、document switch後に遅延完了した結果をcurrent sceneへ自動適用しない。
- close時にworkerを残さない。

### F5 bulk marker rendering

- 10,000 analysis markersを1 marker=1 actorにしない。
- arbitrary `N×3` domain point cloudを1つの`PyVista.PolyData`へ変換し、1 mesh actorとして描画する。
- marker actorはnon-pickableで、editable scene entityと分離する。
- owned PCで50 editable objects＋10,000 markersを計測し、first render `11.406 ms`、orbit p50 `22.993 ms`、p95 `27.963 ms`、max `31.205 ms`を記録した。
- F5の64^3 scalar gridは「後続」。validated scalar-field modelがない現段階ではsynthetic fieldを生成しない。

## N70 Windows受入

詳細: [N70 Windows acceptance](N70_ACCEPTANCE_2026-09-18.md)

最終受入環境:

- Windows 11 Pro build 26200
- Ryzen 7 8845HS / Radeon 780M / 31.31 GiB
- Radeon driver 32.0.13032.11
- 2880×1800 / AppliedDPI 192 (200%)
- Python 3.12.10
- PySide6 6.11.2
- PyVista 0.49.0
- VTK 9.7.0
- PyQtGraph 0.14.0

Final gate:

```text
A13_N70_RESULT PASS
A14_RESULT PASS
N70_A13_A14_RESULT PASS
F5_RESULT PASS
N70_GATE_A13_A14_EXIT=0
N70_GATE_F5_EXIT=0
N70_RESTORED_SHA=5ede848e8e0b0967a50c04c83ff679a649ca439b
N70_POST_STATUS_COUNT=0
N70_RESTORE_OK=True
N70_HARDWARE_GATE_RESULT=PASS
```

A14はN70–N80にまたがるgate。今回の`unsupported` branchでは候補を生成しないためapply/Undoは発生しない。候補preview/適用と1-command UndoはN80でSearchSpec/O10/O20接続後に検証する。

## 継承済みCAD基盤

- N20b: multi-select、common pivot、object/grid/angle snap、hide/lock、entity Undo/Redo。
- N30a: 凹polygon room、stable RoomVertex、頂点挿入/移動/削除、edge寸法、ceiling height、self-intersection拒否。
- N30b: stable wall ID、opening、wall clearance binding、wall move/split/merge/delete、参照migration、曖昧操作拒否、room/topology atomic transaction。
- N40: speaker / seat / screen / furniture / AV equipment / measurement point、3.0.2 template、duplicate、寸法、acoustic reference、explicit aim。
- N50: G10 adapter、allowed/exclusion、walkway/wall clearance、constraint reason overlay、invalid commit rejection。
- N60: immutable measurement/revision binding、REW import/read、FR dock、historical ghost、A/B comparison、stale/cancel guards。
- N70: immutable prediction authority、geometry compatibility、prediction overlays、async guards、bulk marker rendering。

実機受入記録:

- [N05](N05_ACCEPTANCE_2026-09-16.md)
- [N10](N10_ACCEPTANCE_2026-09-16.md)
- [N20a](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a](N30A_ACCEPTANCE_2026-09-17.md)
- [N30b](N30B_ACCEPTANCE_2026-09-17.md)
- [N40](N40_ACCEPTANCE_2026-09-17.md)
- [N50](N50_ACCEPTANCE_2026-09-17.md)
- [N60](N60_ACCEPTANCE_2026-09-17.md)
- [N70](N70_ACCEPTANCE_2026-09-18.md)

## N80 — 進行中

N80a（native SearchSpec + candidate workspace）はWindows実機受入を完了した。詳細: [N80a Windows acceptance](N80A_ACCEPTANCE_2026-09-18.md)。

- last product-code head: `c6cc15e76edbc1ac263911ee084803ca1e32b42c`
- accepted gate head: `ff4dc8078eb9ca0b3effaed66b523cff175fea1a`
- product CI #321 / run `35280237062` PASS
- final gate CI #323 / run `35280664154` PASS
- A13 stale/cancel/document/clean close PASS
- A14 SearchSpec→candidate preview→1-command apply→1 Undo exact restore PASS

N80全体は未完了。O30/O40 pure coreとnative persistence、O20 position-only transaction + immutable batch/result persistence + resume/cancelは実装済み。O20 owned-Windows writable acceptanceもREW 5.40 Beta 135 API 0.9.8でPASSした。次はnative Pareto比較UIとmeasurement loopへ接続する。

- PR #70: objective-vector / Pareto algorithms + immutable native objective/Pareto persistenceをmerge済み。
- PR #71: position-only REW Room Simulator transaction + native Scene/SearchSpec/Candidate adapterをmerge済み。CI #345 PASS。
- 現在: exact batch spec / candidate attempt / resume-cancel persistenceをIssue #67で継続する。
- N50/N60/N70とO20〜O40の該当gateを前提にする。
- SearchSpec編集とO10候補集合をnative Sceneへadapter接続する。
- 候補preview/適用は1 commandでUndo可能にする。
- hard constraintとobjectiveを混同しない。
- objective vectorを保持し、Pareto比較を基本表示にする。
- 「音質総合点」へ縮約しない。
- 実測loopへ接続する場合も、独立検証前に自動推薦へ昇格しない。

N70で外部solverを暗黙採用しなかった方針を維持する。REW Room SimulatorはS01相当、polygon predictorはS03相当のWindows/座標/精度/性能/再現性証拠を通過した場合だけprediction authorityとして追加する。