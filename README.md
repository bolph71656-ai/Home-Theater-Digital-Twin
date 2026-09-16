# Home Theater Digital Twin

Windows 11 x64で個人利用する、**部屋・スピーカー配置・REW測定・AVR設定・変更履歴を結び付け、再現可能なA/B比較でスピーカーセッティングを改善するローカルツール**です。

現在は実装を開始しており、v0.1の中核であるプロジェクト保存、配置/条件スナップショット、REWテキスト取込、A/B比較、バックアップ/復元、最小空間表示まで実装中です。測定マイクと実REWデータはまだないため、実機互換性の受入だけは保留しています。

## 現在の対象環境

- Windows 11 x64
- 開発PC = 利用PC
- Yamaha RX-A4A
- 現在3.0.2（増減可能なデータモデル）
- サブウーファーなしを主要シナリオとするが、将来追加可能
- REW/測定マイクがなくてもアプリ開発・合成fixtureテストは可能

## 開発起動

### Backend

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
python -m htdt
```

API: `http://127.0.0.1:8765/api/docs`

### Frontend

別のPowerShellで:

```powershell
cd frontend
npm install
npm run dev
```

UI: `http://127.0.0.1:5173`

本番相当では`npm run build`後、FastAPIが`frontend/dist`を配信します。

## v0.1で実装している流れ

1. プロジェクトを作る。
2. 部屋寸法、MLP、スピーカー、RX-A4A条件を不変版として保存する。
3. REWの周波数応答テキストをプレビューして取り込む。
4. 原本SHA-256、入力role、実音源ID、条件版を測定に固定する。
5. A/Bを96 PPOの共通グリッドで比較する。
6. 平均差、RMS差、レベルオフセット、形状RMSと比較設定を保存する。
7. 配置を変える場合は新しいContext revisionを作り、過去測定を現在位置へ動かさない。
8. DBとRawAssetをZIPへバックアップし、別データ領域へ復元できる。

## 設計文書

| 文書 | 内容 |
|---|---|
| [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | スコープ、アーキテクチャ、段階別到達点 |
| [DATA_AND_ANALYSIS.md](docs/DATA_AND_ANALYSIS.md) | 不変履歴、比較数式、座標、保存契約 |
| [MEASUREMENT_WORKFLOW.md](docs/MEASUREMENT_WORKFLOW.md) | REW/Windows/AVRの測定境界 |
| [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) | M01以降の作業と受入条件 |
| [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | 現在の実装済み/未検証項目 |
| [PLAN_REVIEW.md](docs/PLAN_REVIEW.md) | 計画レビューと根拠 |

## 重要な制約

実REW出力がまだないため、parserは合成fixtureではテスト済みでも、特定REWビルドとの互換性をまだ保証しません。また、HTDTは現段階で「最適位置」を自動断定しません。まず同条件再測定のばらつきと配置A/B差を比較し、再現した改善を次の基準にします。
