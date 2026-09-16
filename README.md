# Home Theater Digital Twin

HTDTは、Windows上で**部屋・ホームシアター配置・測定・予測・最適化を一つの3D空間モデルへ統合するデジタルツイン**です。

## 現在の開発方針

2026-09-16にGUI方針を全面改訂し、OSSコードと計画の追加レビューを反映しました。

従来のbrowser-first UIとの互換性は要件とせず、今後は**3D CADのようにmouseで部屋とセッティングを直接構築・編集できるnative desktop editor**を製品の中心にします。

- native Windows desktop application
- PySide6 / Qt 6 Widgets
- PyVista / VTK / PyVistaQt
- rendererから独立したDocument model
- CAD型のselection / gizmo / snapping / numeric edit / undo-redo
- room、speaker、seat、screen、furniture、measurement point等を同一sceneで編集
- REW測定、配置制約、予測、最適化結果を同じ3D viewportへ重畳

**今後の実装順と完了条件の正本は [`docs/IMPLEMENTATION_ROADMAP.md`](docs/IMPLEMENTATION_ROADMAP.md) です。**

技術選定の根拠は [`docs/CAD_EDITOR_OSS_RESEARCH.md`](docs/CAD_EDITOR_OSS_RESEARCH.md)、アーキテクチャ決定は [`docs/adr/0001-native-cad-editor-stack.md`](docs/adr/0001-native-cad-editor-stack.md) を参照してください。

## 完成像

HTDTでは、数値フォームを先に埋めるのではなく、3D空間を直接操作します。

- room footprintをclickして描く
- wall vertexをdragし、寸法入力で正確に修正する
- speaker、seat、screen、furnitureをpaletteから配置する
- objectを選択してgizmoでmove/rotateする
- grid / axis / angle / wall / vertexへsnapする
- Top / Front / Side / Perspectiveを切り替える
- Scene tree / viewport / Inspectorが同じselectionへ同期する
- distance / dimension / clearanceをその場で確認する
- measurement、reflection、placement candidate、heatmap等をlayer表示する

将来的には、配置候補の生成、音響予測、多目的/Pareto探索、実測検証を同じworkspaceで行います。

## 現在mainにある実装資産

既存コードはすべて捨てるのではなく、新アーキテクチャへ適合するものを再利用します。

主な実装済み資産:

- Windowsローカル起動基盤
- Project / Context revision / Measurement / Dataset / RawAsset / SQLite
- REW frequency response text import
- REW 5.40系 read-only API integration
- measurement/comparison history
- backup / restore
- room mode / first-reflection candidate
- polygon-prism Room Geometry v2
- placement constraint engine
- deterministic placement search space
- report generation

実装済み・未検証項目の事実は [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) を正本とします。

## Native CAD editor track

[Draft PR #37](https://github.com/bolph71656-ai/Home-Theater-Digital-Twin/pull/37)が実装trackです。過去の進捗文書には、以下のWindows PoC確認が報告されています（今回のレビューで実機再検証はしていません）。

- PySide6 + PyVista/VTK + PyVistaQtのnative Qt window
- 8頂点の凹polygon room描画
- FL/C/FRとMLP描画
- `AffineWidget3D`によるspeaker actorのmove/rotate interaction
- initial snap / undo-redo / immutable Context draft semantics

PR #37の追加commit `0353768`ではnative shell、Scene/viewport選択同期、読取Inspector、view切替、起動スクリプトと直接依存の版固定が追加されています。編集gizmo・数値変更・Save/UndoのGUI接続とpackage受入は未完です。次は**N05: 選択→移動→取消/Undo→保存/再openとstandalone packageの縦断試作**をGitHub上のコードから再現し、その後N10〜N40でCAD基盤を完成させます。

操作・保存・wall/opening参照は[編集契約](docs/CAD_EDITOR_SPEC.md)、Windows/DPI/性能の判定は[受入仕様](docs/CAD_EDITOR_ACCEPTANCE.md)へ具体化しました。旧GUI/API/DBとの互換や機能同等性は完成条件にしません。

## 対象環境

- Windows 11 x64
- 開発PC = 利用PC
- Yamaha RX-A4A
- 現在のspeaker構成: 3.0.2（data model上は可変）
- サブウーファーなしを主要シナリオとするが、将来追加可能
- REW V5.40 beta 135 API版を所有PCへ導入済み
- miniDSP UMIK-1を採用、実機接続/serial登録は未実施

## 現行browser版のローカル起動

native editorへ移行中のため、以下は**現行実装を確認するための手順**です。将来の主UIではありません。

リポジトリ直下のPowerShellで:

```powershell
.\scripts\run-local.ps1
```

backendのみ:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
python -m htdt
```

## 設計文書

| 文書 | 内容 |
|---|---|
| [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) | **今後の実装順・milestone・受入条件の正本** |
| [CAD_EDITOR_SPEC.md](docs/CAD_EDITOR_SPEC.md) | Scene/測定Context分離、操作、保存、座標、wall/opening、非同期契約 |
| [CAD_EDITOR_ACCEPTANCE.md](docs/CAD_EDITOR_ACCEPTANCE.md) | fixture、操作/DPI/性能、packageの受入 |
| [UI_DESIGN.md](docs/UI_DESIGN.md) | native CADの画面・mouse/keyboard設計 |
| [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | CAD-first製品スコープとrelease方針 |
| [CAD_EDITOR_OSS_RESEARCH.md](docs/CAD_EDITOR_OSS_RESEARCH.md) | 3D CAD/OSS調査、採用・不採用理由、参照コード |
| [ADR-0001](docs/adr/0001-native-cad-editor-stack.md) | native CAD editor技術決定 |
| [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | mainへ反映済みの実装事実 |
| [DATA_AND_ANALYSIS.md](docs/DATA_AND_ANALYSIS.md) | 不変履歴、比較数式、座標、保存契約 |
| [MEASUREMENT_WORKFLOW.md](docs/MEASUREMENT_WORKFLOW.md) | REW/Windows/AVRの測定境界 |
| [PLACEMENT_OPTIMIZATION_ROADMAP.md](docs/PLACEMENT_OPTIMIZATION_ROADMAP.md) | 配置探索アルゴリズム詳細。実装順はCAD-first roadmapに従う |
| [ROOM_GEOMETRY.md](docs/ROOM_GEOMETRY.md) | polygon room geometry contract |
| [PLACEMENT_CONSTRAINTS.md](docs/PLACEMENT_CONSTRAINTS.md) | placement hard constraints |
| [REW_API.md](docs/REW_API.md) | read-only REW API契約 |

## 開発運用

ローカル作業は `C:\Users\ka092\Desktop\HTDT\` で行います。Windows renderingやmouse interaction等の実機確認に使用します。

ただし、**計画、考察、設計判断、実装記録、検証結果、進捗、成果物の正本はGitHubに残します。**

各native editor PRではRoadmap milestone ID（N10、N20等）、参考OSS、検証結果、Windows実機確認、既知の制限を記録します。
