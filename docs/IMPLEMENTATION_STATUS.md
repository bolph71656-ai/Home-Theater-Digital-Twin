# 実装ステータス

> 更新: 2026-09-16

## 確定した実環境

| 項目 | 現在の値 | 実装上の扱い |
|---|---|---|
| OS | Windows 11 x64 | v0.1の正式な第一対象 |
| 開発/利用PC | 同一PC | サーバー運用・別PC配布をMVP要件にしない |
| AVR | Yamaha RX-A4A | AVR設定は不変スナップショットとして手入力から開始 |
| スピーカー構成 | 現在3.0.2 | 役割・本数は可変。初期UIだけ3.0.2の行を提示 |
| サブウーファー | なし | 現在の主要シナリオ。将来追加可能 |
| 測定マイク | 未所有 | 実装ブロッカーにしない |
| REW | 未導入 | 合成fixtureで実装し、実REW出力での互換性受入は保留 |

## 中心目標

HTDTは「最適位置」を未測定の段階で断定するのではなく、**配置を保存 → 測定 → 同条件再測定 → A/B比較 → 次の候補を試す**反復を再現可能にする。最初の実利用シナリオはMLPでのFL/FR基準測定と、配置A/B比較。

## 実装済み

### M01 — Windows最小起動基盤

- Python 3.12 / FastAPI / Pydantic / Uvicorn
- React / Vite / TypeScript
- localhost APIと同一UI配信
- Windows GitHub Actions CI
- `/api/health`

### M02 — REW周波数応答テキスト取込

- UTF-8/ASCII、BOM、CRLF/LF
- ヘッダー原文保持
- frequency / level / optional phase
- 正値、有限、厳密増加を検証
- NaN/Inf、重複、逆順、列不整合を明示エラー
- 位相列の存在と有効性を分離し、全ゼロ位相は`unknown`のまま警告
- SHA-256とparser versionを保存

### M03 — 不変履歴とSQLite

- Project
- Context revision（部屋、配置、MLP、AVRを不変JSONとして保存）
- Measurement / Dataset / RawAsset
- 周波数配列をSQLite BLOBへlittle-endian float64で保存
- 原本をハッシュ名でプロジェクトデータ領域へコピー
- 同じ原本はRawAssetを共有

### M04 — 周波数A/B比較

設計仕様に合わせ、比較は以下で固定した。

- グリッド: `1 Hz × 2^(k/96)` の96 PPO
- レベル補間: `log2(f)`軸上の線形補間
- 外挿なし
- 差の向き: A−B
- mean difference / RMS difference
- 基準帯域の平均差によるlevel offset
- shape RMS
- requested band / actual common band / valid point数 / algorithm versionを結果ごと保存

### M05/M06 — 空間・条件編集と取込プレビュー

- 矩形参照寸法、MLP、任意数のスピーカーを編集
- 現在の3.0.2は初期行だけで、固定構成にはしない
- RX-A4Aの設定スナップショット
- ファイルを保存する前にparser結果、帯域、点数、位相状態、SHAを確認
- input roleとsource speaker IDsを別保存

### M07 — 比較履歴

- A/BのDataset IDと比較条件を固定参照
- 計算済み配列と要約値をAnalysisResult相当として保存
- アプリ更新後も保存済み比較を表示可能なデータ構造

### M08 — バックアップ/復元

- SQLite Backup APIでDBスナップショットを作成
- RawAssetを含むZIP
- schema manifestを検証
- Zip Slipを拒否
- 別データディレクトリへの復元を自動テスト

### M09 — 最小空間表示

Plotlyの`scatter3d`を使い、HTDT座標 `(x,y,z)` を画面上 `(x,z,y)` に変換してスピーカーとMLPを表示する。v0.1では空間確認用の最小ビューとし、Three.js専用シーンは高度な反射経路表示が必要になった時点で再評価する。

## 未検証・保留

以下はコード未実装ではなく、**実機/実データがないため受入未完了**の項目。

- 実際のREW安定版から出力したテキストとの互換性
- 測定マイク固有の校正・絶対SPL
- RX-A4AへのPC HDMIチャンネル割当の実機確認
- 3.0.2の高さチャンネルをREWから個別に励振できるか
- 実部屋寸法・スピーカー型番・実座標
- 同条件再測定の実際のばらつき

これらが揃うまで、HTDTは「REW実機互換性確認済み」「最適配置を予測可能」とは表示しない。

## 次

実REWデータ取得前でも進められる次工程は、測定品質フラグ、比較の除外区間UI、配置複製UX、REW API読取アダプターの境界設計。実REWファイル入手後は最優先でfixtureへ追加し、M02/M10の実互換性を受入する。
