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
| 測定マイク | 未所有 | 実機受入のみ保留。合成fixture開発のブロッカーにはしない |
| REW | 未導入 | file/APIともmock・合成fixtureで実装済み。実機互換性受入だけ保留 |

## 中心目標

HTDTは未測定の状態で「最適位置」を断定せず、**配置を保存 → 測定 → 同条件再測定 → A/B比較 → 次の候補を試す**反復を再現可能にする。

## mainへ反映済み

- M01: Windows起動基盤、FastAPI、React/Vite、CI
- M01運用: loopback空きポート選択、ブラウザ自動起動、PowerShell一発起動
- M01運用: 同一データ領域の単一インスタンス排他。二重起動時は既存UIを再利用
- M02: REW周波数応答テキストparser、原本SHA-256
- M03: Project / Context revision / Measurement / Dataset / RawAsset / SQLite
- M04: 96 PPO、log2(f)補間、A−B、mean/RMS、level offset、shape RMS
- M05/M06: 部屋・MLP・可変スピーカー・RX-A4A条件、取込プレビュー
- M07: Dataset/Context版を固定した比較履歴
- M08: DB + RawAsset ZIPバックアップ/復元
- M09: Plotly FRグラフと最小3D
- M10: Windows合成E2Eと実機受入手順
- M10補強: build済みfrontendをFastAPIから配信するWindows smoke test
- A01: 矩形室モードと6面の一次image-source反射候補。結果は`predicted_geometry_candidate`
- schema v2: 測定品質、再測定グループ、Raw添付、整合性検査、A/B confounder分離
- UI: quality / repeat_group / attachments / intended changes / confounders / interpretation warnings
- A03 backend: localhost限定・GET専用のREW 5.40系APIアダプター
- A03 UI: offline表示、測定一覧、PPO/unit/smoothing指定FRプレビュー、requested/returned来歴表示
- A04: 96 PPO特徴検出、room mode/一次反射の候補対応、quality/evidence gate、UI
- R01: 保存済みComparisonから自己完結HTML/JSONレポート、inline SVG、UIダウンロード導線
- V01: 実測配置の比較一覧。channel/measurement point、移動量、品質、条件差、保存済み比較を横並び表示
- V02: schema移行前ZIP、移行後整合性検査、失敗時DB/RawAssetロールバック

## A03 — 読取専用REW API / UI

REW 5.40系の公式API仕様を対象に、任意のGET専用アダプターとUIを実装済み。

- 既定 `http://127.0.0.1:4735`、localhost以外を拒否
- `GET /measurements` と measurement UUID参照
- `GET /measurements/{uuid}/frequency-response`
- 32-bit float Base64をbig-endianで復号
- `startFreq + ppo` または`startFreq + freqStep`から周波数軸を復元
- requested PPO/unit/smoothingとREW返却PPO/unit/smoothingを分離
- 測定一覧のlist/object-keyed形状を正規化
- 壊れたBase64、NaN/Inf、空配列、spacing欠損、phase長不一致を拒否
- REW未起動時はofflineを正常状態として扱い、保存済みHTDTデータは通常利用可能
- UIから測定一覧とFRをGETし、log周波数軸の軽量SVGでプレビュー
- 取得曲線は現段階ではHTDT Measurement/Datasetへ自動保存しない
- REWへのPOST/PUT/DELETE、Generator、測定開始、設定変更は実装しない

所有PC上の実REW接続がないため、実API応答との最終互換性だけを保留する。

## A04 — ピーク/ディップと幾何候補対応

周波数応答をHTDT内部の96 PPO / log2補間へ再標本化し、固定パラメータを返す特徴検出を実装済み。

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

## 保存・復旧・Windows受入

- V02: 旧schemaを開く前にDB＋assetsをpre-migration ZIPへ退避し、移行失敗または移行後整合性失敗時に旧状態へロールバックする。
- M10: Project→R1→測定/再測定→Raw添付→R2→A/B→report→再open→backup→別フォルダrestore→integrityをWindows合成E2Eで固定。
- built-app smoke: Vite build後、FastAPIから`index.html`、実JS bundle、`/api/health`、SPA fallbackが取得できることをWindows CIで確認する。
- launcher: CLI、PowerShell構文、空きポートfallback、単一インスタンス排他をWindows CIで確認する。

## 現時点でハードウェア/実データ待ちの項目

- 実REW安定版テキストとのparser互換性
- REW 5.40系APIの所有PC上での実接続とA03 UI実機確認
- 測定マイク校正・絶対SPL
- RX-A4A HDMIチャンネル割当と実際の発音源確認
- 高さチャンネルをREWから個別励振できるかの確認
- 実部屋での同条件再測定ばらつき
- A04の閾値/prominenceが実部屋で実用的か
- V01を複数の実配置・実測で使った操作性
- M10の実データ通し確認

## 次の実行ゲート

1. REWを導入し、まずFL/FRの同条件repeatを含むテキストexportを取得する。
2. 測定マイク導入後、校正ファイル・向き・Windows入力経路を記録する。
3. RX-A4AでFL/FR/C/Heightの実発音経路を確認し、input roleと実音源を分離して記録する。
4. `docs/WINDOWS_ACCEPTANCE.md`の実機最終受入を実行する。
5. 実REW APIを確認できた後、API取得をHTDT Datasetへ保存する場合はresponse/query来歴をRawAsset/metadataへ固定し、実API確認前に`measured`へ自動分類しない。
6. IR/ETCは実IRサンプル取得後にA02として開始する。

現時点では、合成データだけで安全に進められるv0.1中核と周辺品質作業は実装済み。次の大きな情報増分は実REW/実測から得る。
