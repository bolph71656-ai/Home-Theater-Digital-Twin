# 実装ステータス

> 更新: 2026-09-17 / N60 merged・A12/A13 Windows実機受入完了 / 次工程 N70
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。旧browser/backendの詳細履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05 / N10 / N20a / N20b / N30a / N30b / N40 / N50 / N60 の技術gateを実装し、N60までWindows実機受入を通過した。**

N60はIssue #61 / PR #62で完了し、merge commit `f1694eb879a250835efa026ac5dacdec18362788` でmainへ反映済み。Issue #61は`completed`でclose済み。最終製品コード変更は `8551963c4dc3e5eb5a22bd0683edbaea6e891cdb`、最終acceptance harness/headは `73b77866ebdc42f70a016e2ebd13ad99858b01b8`。後者はA13取消検証を時間依存から決定的ラッチへ変更しただけで、製品runtime codeは変更していない。A12/A13は2880×1800・200% DPIの実Win32 mouse interactionでPASSした。

| 区分 | 現在の状態 |
|---|---|
| main | **N60までmerge済み**。PR #62 merge `f1694eb879a250835efa026ac5dacdec18362788` |
| N60 tracking | Issue #61 / PR #62（完了） |
| N60 last product-code head | `8551963c4dc3e5eb5a22bd0683edbaea6e891cdb` |
| N60 accepted gate head | `73b77866ebdc42f70a016e2ebd13ad99858b01b8` |
| acceptance docs head | `5cd8c3f02e31e6e46af0a81b8a213364bd055c94` |
| product CI | #300 / run `35223222374` PASS |
| final harness CI | #301 / run `35225682111` PASS |
| acceptance docs CI | #302 / run `35226382149` PASS |
| A12 | saved A選択、offline FR、mouse move/save B、A binding不変、historical ghost、A/B revision binding PASS |
| A13 | edit-stale、UI responsiveness、明示cancel、document change、clean close/no worker PASS |
| native entry | `htdt-native` / `run-native.ps1` / `python -m htdt.native_cad` はN60 `MeasurementWorkspaceWindow` compositionを起動 |
| browser UI | 新CAD機能は凍結。二重実装しない |
| 次工程 | **N70 — 予測・可視化** |

## N60 — 完了内容

### Measurement authority / persistence

- 測定はexact `SceneRevision`、document ID、scene content hash、measurement/acoustic-reference entityへimmutable bindingする。
- native `CadMeasurementRepository`を`cad-scenes.sqlite3`へ追加し、source revisionとの整合を保存時に検証する。
- raw assetとFR datasetはlocalに不変保存し、REW停止中でも表示可能。
- external REW UUIDはprovenanceであり、HTDT primary keyにはしない。
- capture time、calibration/reference、phase、routing等のunknownを推測で埋めない。
- legacy `Context`をnative authorityへ昇格させない。

### Native measurement workspace

- 日本語優先の`実測` workspaceをnative CADへ統合した。
- 保存測定tree、provenance/measurement point/revision metadata、FR plot、REW text/API importを提供する。
- A/B比較はexact dataset IDと各source SceneRevision IDを固定して保存する。
- current sceneと異なる測定はexact source revisionからhistorical ghostを表示し、ghostはpick不可。
- PyQtGraph 0.14.0をnative FR描画に採用した。

### Async REW / stale-result boundary

- REW I/OはQThread workerでGUI thread外へ出す。
- job tokenはsubmission時のdocument/revision/hash/measurement point/queryを固定する。
- `MeasurementJobGuard`はcancelled、superseded、stale revision、document mismatchをcurrent sceneへ適用しない。
- close時はtokenをcancelし、bounded wait後にworkerを残さない。

### 200% DPI composition fix

実機ではmeasurement form自体のscrollだけでは足りず、継承したright dockのvertical splitが下段controlを画面外へ押し出していた。

- `_MeasurementScrollArea`で長いcontent heightをscroll内部に閉じ、dock minimumへ伝播させない。
- `RightDockWidgetArea`に存在する全dockをいったんrebuildし、単一のCAD-style tab stackへ統合する。
- known dock: `Inspector`, `Room`, `壁・開口`, `オブジェクト詳細`, `制約`, `実測`。
- future unknown right-side dockも動的に同じstackへ含める。
- 以前の部分修正が見落としていた`Room` / `壁・開口`を含めたことで、200% DPIの構造的overflowを解消した。

## A12 / A13 Windows受入

詳細: [N60 Windows acceptance](N60_ACCEPTANCE_2026-09-17.md)

最終受入環境:

- Windows 11 Pro build 26200
- Ryzen 7 8845HS / Radeon 780M / 31.3 GiB
- Radeon driver 32.0.13032.11
- 2880×1800 / AppliedDPI 192 (200%)
- Python 3.12.10
- PySide6 6.11.2
- PyVista 0.49.0
- VTK 9.7.0
- PyQtGraph 0.14.0

A12:

```text
A12_PRODUCT_COMPOSITION True
A12_MOUSE_SELECT_SAVED_A True
A12_OFFLINE_FR True
A12_MOUSE_MOVE_SAVE_B True
A12_A_BINDING_IMMUTABLE True
A12_HISTORICAL_GHOST True
A12_AB_REVISION_BINDING True
A12_RESULT PASS
```

A13:

```text
A13_PRODUCT_COMPOSITION True
A13_EDIT_MAKES_RESULT_STALE True
A13_UI_RESPONSIVE True 85
A13_CANCEL_WORKER_STARTED True
A13_CANCEL_REGISTERED True
A13_CANCELLED_RESULT_NOT_APPLIED True
A13_DOCUMENT_SWITCH_RESULT_NOT_APPLIED True
A13_CLEAN_EXIT_NO_WORKER True 0
A13_RESULT PASS
```

Runner cleanup:

```text
N60_GATE_A12_EXIT=0
N60_GATE_A13_EXIT=0
N60_RESTORED_SHA=5ede848e8e0b0967a50c04c83ff679a649ca439b
N60_POST_STATUS_COUNT=0
N60_RESTORE_OK=True
N60_HARDWARE_GATE_RESULT=PASS
```

## 継承済みCAD基盤

- N20b: multi-select、common pivot、object/grid/angle snap、hide/lock、entity Undo/Redo。
- N30a: 凹polygon room、stable RoomVertex、頂点挿入/移動/削除、edge寸法、ceiling height、self-intersection拒否。
- N30b: stable wall ID、opening、wall clearance binding、wall move/split/merge/delete、参照migration、曖昧操作拒否、room/topology atomic transaction。
- N40: speaker / seat / screen / furniture / AV equipment / measurement point、3.0.2 template、duplicate、寸法、acoustic reference、explicit aim、A10。
- N50: G10 adapter、allowed/exclusion、walkway/wall clearance、constraint reason overlay、invalid commit rejection、A11。
- N60: immutable measurement/revision binding、REW import/read、FR dock、historical ghost、A/B comparison、stale/cancel guards、A12/A13。

実機記録:

- [N05 Windows acceptance](N05_ACCEPTANCE_2026-09-16.md)
- [N10 Windows acceptance](N10_ACCEPTANCE_2026-09-16.md)
- [N20a A05/A06](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b A07](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a A08](N30A_ACCEPTANCE_2026-09-17.md)
- [N30b A09](N30B_ACCEPTANCE_2026-09-17.md)
- [N40 A10](N40_ACCEPTANCE_2026-09-17.md)
- [N50 A11](N50_ACCEPTANCE_2026-09-17.md)
- [N60 A12/A13](N60_ACCEPTANCE_2026-09-17.md)

## 次工程 — N70 予測・可視化

ロードマップ上の次工程は**N70 — 予測・可視化**。

- N50のconstraint stateと固定された入力versionを前提に、対応model gateを満たす予測のみnative CADへ載せる。
- modes / reflection、prediction layer、候補雲を扱う。
- fieldが存在する場合に限りheatmap / slice / volumeを表示する。
- predictionはmeasured evidenceと明確に区別し、source revision・適用形状/帯域・再現性・stale状態を保持する。
- 長い計算はsubmission時入力を固定し、編集後の古い結果をcurrent sceneへ自動適用しない。
- GUIが非矩形室を扱えることと、個別の音響modelが非矩形室を正確に予測できることを混同しない。
- roadmap gateはA13/A14およびF5。

N70でも「音質総合点」や根拠のないランキングへ変換しない。予測・実測・仮説を同じ証拠種別として混同しない。