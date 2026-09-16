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
| REW | 未導入 | ファイル/APIともmock・合成fixtureで実装し、実機互換性受入は保留 |

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
- schema v2: 測定品質、再測定グループ、Raw添付、整合性検査、A/B confounder分離
- UI: quality / repeat_group / attachments / intended changes / confounders / interpretation warnings
- A03: localhost限定・GET専用のREW 5.40 APIアダプター
- A04: 96 PPO特徴検出、room mode/一次反射の候補対応、quality/evidence gate、UI

## A03 — 読取専用REW API

REW 5.40系の公式API仕様を対象に、任意のGET専用アダプターを実装した。

- 既定 `http://127.0.0.1:4735`、localhost以外を拒否
- `GET /measurements` と measurement UUID参照
- `GET /measurements/{uuid}/frequency-response`
- 32-bit float Base64を公式仕様どおりbig-endianで復号
- `startFreq + ppo` または `startFreq + freqStep` から周波数軸を復元
- requested PPO/unit/smoothingとREW返却PPO/unit/smoothingを分離
- 測定一覧のlist/object-keyed形状を正規化
- 壊れたBase64、NaN/Inf、空配列、spacing欠損、phase長不一致を拒否
- REW未起動時は`/api/rew/status`だけconnected=falseを返し、保存済みHTDTデータは通常利用可能
- REWへのPOST/PUT/DELETE、Generator、測定開始は実装しない

実REW接続がないため、完了条件のうち「オフラインへ戻れる」「REW変更/発音を起こさない」はmock/コード境界で検証し、実機での最終受入だけを保留する。

## A04 — ピーク/ディップと幾何候補対応

周波数応答をHTDT内部の96 PPO / log2補間へ再標本化し、固定パラメータを返す特徴検出を実装した。

- 既定評価帯域: 20–300 Hz（API/UIで変更可能）
- baseline: log周波数上の移動平均、既定1/3 octave幅
- feature threshold: baselineからの偏差3 dB以上
- 最小feature間隔: 1/12 octave
- mode / reflection候補との照合距離: log2周波数距離、既定1/12 octave以内
- room modeはpeak/dip双方の候補、一次反射の`first_destructive_hz`はdipのみの候補
- 結果分類は`candidate_association_not_causal_diagnosis`。近接しても原因確定とは扱わない
- `invalid`測定と非`measured`データでは自動候補照合を無効化
- `warning` / `unknown`品質は候補照合を許すが、手動確認が必要な警告を返す
- 検出・照合のPPO、帯域、prominence、baseline幅、最小間隔、照合許容差、音速、算法版を結果に保持
- UIでDatasetを選び、peak/dip・baseline偏差・候補周波数・log周波数距離・品質警告を同じパネルで表示

合成FRでは既知の狭いpeak/dipを検出し、既知周波数の矩形室モード/一次反射候補との対応をテスト済み。実測での妥当な閾値は実REW測定取得後に再評価する。

## 実装中 — R01 比較レポート

保存済みComparisonを唯一の入力として、再計算せずに自己完結レポートを生成する。

- `GET /api/projects/{project_id}/comparisons/{comparison_id}/report.json`
- `GET /api/projects/{project_id}/comparisons/{comparison_id}/report.html`
- JSONにはProject、ComparisonSpec、保存済みAnalysisResult、測定/Context ID、quality、intended changes、confounders、算法版を同梱
- HTMLには保存済みA/B配列から生成したインラインSVGグラフを埋め込む
- HTMLは外部CDN、外部JavaScript、外部画像なしで単体表示可能
- 完全なJSONスナップショットをHTML内の`application/json`としても埋め込む
- 幾何候補やA/B差を原因・最適性の証明として扱わない解釈境界をレポートに固定
- ファイル名はcomparison IDを含め、`Content-Disposition: attachment`でダウンロード可能

保存済みComparisonを使うため、後から現在の配置や条件を編集しても旧レポートの入力根拠は変わらない。HTML生成器とAPIの回帰テストを追加した。

## 未検証・保留

- 実REW安定版テキストとの互換性
- REW 5.40 APIの所有PC上での実接続
- 測定マイク校正・絶対SPL
- RX-A4A HDMIチャンネル割当
- 高さチャンネルの個別励振
- 実部屋での同条件再測定ばらつき
- A04の閾値/prominenceが実部屋で実用的か
- M10の実データ通し確認

## 次

1. R01のWindows CIを通し、UIからHTML/JSONレポートを開ける導線を追加する。
2. V01の土台として、同じchannel/MLPの複数配置を比較一覧へまとめる。
3. REW API取得をHTDT Datasetへ保存する場合は、API response/queryの来歴をRawAsset/metadataへ固定する。実API確認前にmeasuredへ自動分類しない。
4. IR/ETCは実IRサンプル取得後にA02として開始する。
5. 実REWを導入した時点で、text exportとAPI取得を同一測定で照合する。
