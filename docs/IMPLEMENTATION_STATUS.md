# 実装ステータス

> 更新: 2026-09-16

## 確定した実環境

| 項目 | 現在の値 | 実装上の扱い |
|---|---|---|
| OS | Windows 11 x64 | 正式な第一対象 |
| 開発/利用PC | 同一PC | サーバー運用・別PC配布をMVP要件にしない |
| AVR | Yamaha RX-A4A | AVR設定は不変スナップショットとして手入力から開始 |
| スピーカー構成 | 現在3.0.2 | 役割・本数は可変 |
| サブウーファー | なし | 現在の主要シナリオ。将来追加可能 |
| 測定マイク | 未所有 | 実装ブロッカーにしない |
| REW | 未導入 | 合成fixtureで実装し、実REW出力での互換性受入は保留 |

## 中心目標

HTDTは「最適位置」を未測定の段階で断定するのではなく、**配置を保存 → 測定 → 同条件再測定 → A/B比較 → 次の候補を試す**反復を再現可能にする。

## mainへ反映済み

- M01: Windows起動基盤、FastAPI、React/Vite、CI
- M02: REW周波数応答テキストparser、原本SHA-256
- M03: Project / Context revision / Measurement / Dataset / RawAsset / SQLite
- M04: 96 PPO、log2(f)補間、A−B、mean/RMS、level offset、shape RMS
- M05/M06: 部屋・MLP・可変スピーカー・RX-A4A条件、取込プレビュー
- M07: Dataset/Context版を固定した比較履歴
- M08: DB + RawAsset ZIPバックアップ/復元
- M09: Plotly FRグラフと最小3D
- A01: 矩形室モードと6面の一次image-source反射候補。結果は`predicted_geometry_candidate`

## v0.1補完 — schema v2

- schema v1を起動時に加算的にv2へ移行
- Measurementへ`quality_status`（usable / warning / invalid / unknown）、理由、確認元、再測定グループ、routing evidenceを保存
- 有限なFRを自動でusableに昇格させない。実データ未確認時はunknownを既定にする
- 同じRawAsset SHA-256でもMeasurement/Datasetは自動統合せず、重複候補として通知する
- `.mdat`、マイク校正、AVR設定、画像等をProject / Context / MeasurementへRawAsset添付できるAPIを追加
- バックアップ前と復元時に外部キーと全RawAssetの実在を検証し、欠損を成功扱いしない
- A/B結果へ両測定の品質スナップショットを保存
- Context差分を保存し、`expected_change_paths`に一致する意図した変更と、それ以外のconfounderを分離
- 同じ`repeat_group`同士の比較は`repeatability`として分類

## 未検証・保留

- 実REW安定版テキストとの互換性
- 測定マイク校正・絶対SPL
- RX-A4A HDMIチャンネル割当
- 高さチャンネルの個別励振
- 実部屋での同条件再測定ばらつき
- M10の実データ通し確認

## 次

1. REW 5.40系の公式REST API仕様に沿ったGET専用アダプターを追加する。REW未起動/5.31系でもHTDTはオフライン動作を維持する。
2. API由来FRのsmoothing/PPO/単位を来歴として保存し、HTDT内部96 PPO再標本化と分離する。
3. A04としてピーク/ディップ検出条件を固定し、モード/一次反射との候補対応を実装する。原因確定とは表示しない。
4. IR/ETCは実IRサンプル取得後にA02として開始する。
