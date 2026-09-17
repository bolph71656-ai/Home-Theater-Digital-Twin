# N30b A09 Windows実機受入 — 2026-09-17

Issue: #53  
PR: #54  
受入対象commit: `fccfdfbfb056a72906499a814f58f0957b0a65e4`

## 結果

**A09 PASS**。所有Windows PCでWin32の実OS mouse inputを使用し、F3の壁選択・移動、分割、結合、削除、参照追跡、曖昧操作の拒否、Undo/Redoを確認した。受入前後のGit worktreeはclean。

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

## F3 fixture

- F2と同じ8頂点凹polygon room、天井高2.4 m
- front wallに`door-front` opening
- front wallに`clearance-front = 0.35 m`
- 2 measurement points: `seat-left`, `seat-right`
- SceneDocument schema v3 / stable wall topology

front wallを実マウスで選択して移動した後もopening/clearanceは同じstable wall IDを参照した。split後はopeningを包含する子wallへ移送し、clearance bindingは両子wallへ追従。merge後は両参照を新wall IDへ統合した。

参照を持つmerged wallの削除は履歴を増やさず拒否された。別wallへ中央配置したopeningがsplit pointを跨ぐケースも、wall数と履歴を変えず確定拒否された。未参照wallの削除は成功し、既存opening/clearance参照は維持された。最後にUndo/Redoで完全一致を確認した。

## 実機環境

| 項目 | 値 |
|---|---|
| OS | Microsoft Windows 11 Pro 10.0.26200 / build 26200 |
| CPU | AMD Ryzen 7 8845HS w/ Radeon 780M Graphics |
| GPU | AMD Radeon 780M Graphics / driver 32.0.13032.11 |
| RAM | 31.3 GiB |
| Display | 2880×1800 |
| DPI | AppliedDPI 192 = 200% |
| Python | 3.12.10 |
| PySide6 | 6.11.2 |
| PyVista | 0.49.0 |
| VTK | 9.7.0 |

## 操作経路

`C:\Users\ka092\Desktop\HTDT\repo` のclean checkoutを対象commitへdetachし、`scripts/validate_n30b_windows.py`を実行した。wall selectとwall dragはWin32 `mouse_event`を使用し、Qt/VTKの内部イベント直呼び出しで代替していない。split/merge/deleteは実UI QAction経路を使用した。

A09はheadless CIの代替ではない。GitHub Actionsはdomain回帰、launcher、harness compile等を別途検証する。