# 実装ステータス

> 更新: 2026-09-16

## 確定した実環境

| 項目 | 現在の値 | 実装上の扱い |
|---|---|---|
| OS | Windows 11 x64 | 正式な第一対象 |
| 開発/利用PC | 同一PC | サーバー運用・別PC配布をMVP要件にしない |
| AVR | Yamaha RX-A4A | AVR設定は不変スナップショットとして手入力から開始 |
| スピーカー構成 | 現在3.0.2 | 役割・本数は可変。初期UIだけ3.0.2の行を提示 |
| サブウーファー | なし | 現在の主要シナリオ。将来追加可能 |
| 測定マイク | 未所有 | 実装ブロッカーにしない |
| REW | 未導入 | 合成fixtureで実装し、実REW出力での互換性受入は保留 |

## 中心目標

HTDTは「最適位置」を未測定の段階で断定するのではなく、**配置を保存 → 測定 → 同条件再測定 → A/B比較 → 次の候補を試す**反復を再現可能にする。最初の実利用シナリオはMLPでのFL/FR基準測定と配置A/B比較。

## mainへ反映済み — v0.1 core

- M01: Python 3.12 / FastAPI / React / Vite / Windows CI / health check
- M02: REW周波数応答テキストparser。UTF-8/BOM/CRLF、ヘッダー保持、frequency/level/optional phase、異常値検証、SHA-256
- M03: Project、Context revision、Measurement、Dataset、RawAsset、SQLite BLOB、不変履歴
- M04: 96 PPO、log2(f)補間、A−B、mean/RMS、level offset、shape RMS、比較結果保存
- M05/M06: 部屋・MLP・可変スピーカー・RX-A4A条件編集、取込プレビュー、input role/source speaker IDs分離
- M07: Dataset/Context版を固定した比較履歴
- M08: SQLite Backup API + RawAsset ZIP + schema/Zip Slip検証 + Windows復元テスト
- M09: PlotlyによるFRグラフと最小3D空間表示

Windows GitHub Actionsではbackend 13テストとfrontend buildを通過してmainへ反映した。

## 実装中 — v0.2 analysis foundation

### 配置複製UX

選択したContext revisionを編集フォームへコピーできる。コピーしただけでは旧版を変更せず、保存時にparent_context_idを持つ新しい不変版になる。

### 比較の除外帯域

UIで `70-90, 120-130` のような除外帯域を指定し、ComparisonSpecへ保存する。96 PPOグリッドの全点数と有効点数を分離した既存契約をそのまま使う。

### A01: 矩形室モード

矩形室について

`f = c/2 * sqrt((nx/W)^2 + (ny/D)^2 + (nz/H)^2)`

を計算し、axial / tangential / obliqueを区別する。音速と周波数上限を入力値として結果へ残す。

### 一次反射の幾何候補

各配置済みスピーカーを6面に鏡像化し、MLPへの一次反射について反射点、直接距離、反射距離、経路差、追加遅延を求める。経路差だけから180°になる最初の周波数 `c/(2ΔL)` も候補として表示する。

これは**実測診断ではない**。反射係数、反射位相、スピーカー指向性、開口、家具を扱っていないため、結果分類は `predicted_geometry_candidate` とする。表示周波数が実測ディップの原因だとは断定しない。

## 測定品質の扱い

実REW測定がない現段階で、品質を自動的にgoodへ昇格させない。REWのクリップ/レベル/タイミング警告、測定時条件、同条件再測定が揃うまではUI上 `quality: unknown` とする。parserが正常に読めたことを「良好な音響測定」と同一視しない。

## 未検証・保留

以下は実機/実データがないため受入未完了。

- 実際のREW安定版から出力したテキストとの互換性
- 測定マイク固有の校正・絶対SPL
- RX-A4AへのPC HDMIチャンネル割当の実機確認
- 3.0.2の高さチャンネルをREWから個別に励振できるか
- 実部屋寸法・スピーカー型番・実座標
- 同条件再測定の実際のばらつき
- 幾何候補と実測ピーク/ディップの対応検証

これらが揃うまで、HTDTは「REW実機互換性確認済み」「最適配置を予測可能」とは表示しない。

## 次に実機なしで進められる範囲

- 幾何解析のWindows CI受入
- 測定品質情報をREW実データから受け取るためのデータ契約
- IR/ETCの内部型と合成IR fixture
- 比較レポートの保存形式
- REW APIは対象REW版/OpenAPIを実際に取得してから読取専用アダプターを実装する

実REWファイルを入手した時点では、最優先でfixtureへ追加してM02/M10の実互換性を受入する。
