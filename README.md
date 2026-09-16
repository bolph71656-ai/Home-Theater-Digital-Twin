# Home Theater Digital Twin

Windows 11 x64で個人利用する、**部屋・スピーカー配置・REW測定・AVR設定・変更履歴を結び付け、再現可能なA/B比較でスピーカーセッティングを改善するローカルツール**です。

v0.1の中核であるプロジェクト保存、配置/条件スナップショット、REWテキスト取込、A/B比較、バックアップ/復元、最小空間表示、Windows合成E2Eまで実装済みです。REW V5.40 beta 135 API版は所有PCへ導入し、実APIとUI経由のFR取得まで確認済みです。測定マイクと実測FRを使う最終受入は継続中です。

## 現在の対象環境

- Windows 11 x64
- 開発PC = 利用PC
- Yamaha RX-A4A
- 現在3.0.2（増減可能なデータモデル）
- サブウーファーなしを主要シナリオとするが、将来追加可能
- REW V5.40 beta 135 API版を所有PCへ導入済み。測定マイクは未導入
- REW/測定マイクがなくても保存・比較・解析・バックアップ機能は利用/テスト可能

## Windowsでローカル起動

リポジトリ直下のPowerShellで:

```powershell
.\scripts\run-local.ps1
```

初回は`.venv`を作り、backend依存を導入し、必要ならfrontend依存を導入して`frontend/dist`をbuildします。その後FastAPIがUIとAPIを同一originで配信し、既定ブラウザを開きます。

- 既定は`127.0.0.1:8765`
- 8765が使用中ならloopback上の空きポートへ自動フォールバック
- 同じHTDTデータ領域では1プロセスだけが起動し、二重起動時は新しいserverを作らず既存UIを開く
- staleなinstance metadataはOSの排他ロックを取得できれば上書きされるため、異常終了後も再起動可能
- 終了は起動したPowerShellで`Ctrl+C`
- ブラウザを自動起動しない場合: `.\scripts\run-local.ps1 -NoBrowser`
- 既に`frontend/dist`が最新でbuildを省略したい場合: `.\scripts\run-local.ps1 -SkipFrontendBuild`

データはWindowsのローカルアプリデータ領域に保存され、ブラウザタブを閉じても残ります。REWは必須ではなく、未起動時も保存済みHTDTデータは利用できます。

## 開発起動

backendだけを直接起動する場合:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
python -m htdt
```

`python -m htdt`は8765を優先し、使用中なら空きポートを選びます。同じデータ領域ですでにHTDTが動いていれば二重起動せず、その既存URLを利用します。ブラウザを開かない場合は`python -m htdt --no-browser`、優先ポートを変える場合は`python -m htdt --port 9000`のように指定できます。

API docsは起動URLの`/api/docs`です。

frontendをVite開発サーバーで動かす場合は別のPowerShellで:

```powershell
cd frontend
npm install
npm run dev
```

開発UIは`http://127.0.0.1:5173`で、APIはVite proxy経由でbackendへ接続します。本番相当では`npm run build`後、FastAPIが`frontend/dist`を配信します。

## v0.1の流れ

1. プロジェクトを作る。
2. 部屋寸法、MLP、スピーカー、RX-A4A条件を不変版として保存する。
3. REWの周波数応答テキストをプレビューして取り込む。
4. 原本SHA-256、入力role、実音源ID、条件版、品質状態を測定に固定する。
5. 同条件再測定の再現性を確認する。
6. 配置や設定A/Bを96 PPOの共通グリッドで比較する。
7. 平均差、RMS差、レベルオフセット、形状RMS、意図した変更、交絡要因と比較設定を保存する。
8. 配置を変える場合は新しいContext revisionを作り、過去測定を現在位置へ動かさない。
9. 保存済みComparisonから自己完結HTML/JSONレポートを生成する。
10. DBとRawAssetをZIPへバックアップし、別データ領域へ復元できる。

REW 5.40系のAPIについてはlocalhost限定・GET専用のブラウザを実装済みです。所有PCのREW V5.40 beta 135で実接続し、測定一覧と96 PPO FRの実デコード、UI表示まで確認しました。REWの測定開始、Generator、設定変更、API取得データの自動保存は行いません。

## 設計文書

| 文書 | 内容 |
|---|---|
| [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | スコープ、アーキテクチャ、段階別到達点 |
| [DATA_AND_ANALYSIS.md](docs/DATA_AND_ANALYSIS.md) | 不変履歴、比較数式、座標、保存契約 |
| [MEASUREMENT_WORKFLOW.md](docs/MEASUREMENT_WORKFLOW.md) | REW/Windows/AVRの測定境界 |
| [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) | M01以降の作業と受入条件 |
| [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | 現在の実装済み/未検証項目 |
| [WINDOWS_ACCEPTANCE.md](docs/WINDOWS_ACCEPTANCE.md) | Windows合成E2Eと実機最終受入手順 |
| [REW_API.md](docs/REW_API.md) | 読取専用REW API契約 |
| [REW_REAL_VALIDATION.md](docs/REW_REAL_VALIDATION.md) | 所有PC上の実REW API/UI検証記録 |
| [PLAN_REVIEW.md](docs/PLAN_REVIEW.md) | 計画レビューと根拠 |

## 重要な制約

REW APIアダプターは所有PC上のV5.40 beta 135で実接続・FRデコード・UI表示まで確認済みです。ただし同一measurementのREW text exportとの照合と実測FRは未完了なので、parserを含む実測ワークフロー全体の互換性はまだ完了扱いにしません。また、HTDTは現段階で「最適位置」を自動断定しません。まず同条件再測定のばらつきと配置A/B差を比較し、再現した改善を次の基準にします。
