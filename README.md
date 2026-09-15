# Home Theater Digital Twin

Windowsで個人利用する、部屋・スピーカー配置・REW測定・AVR設定・変更履歴を結び付けるローカルツールです。

**2026-09-16から実装を開始しました。現在はv0.1 / M01の最小起動基盤を実装中です。**

REWを測定・解析の中心に据え、HTDTは「どの配置・条件で測ったか」と比較の再現性を管理します。最終的な狙いは、実測と履歴に基づいて、より良いスピーカー配置・設定を反復的に見つけられることです。

## 現在の対象環境

- Windows 11 x64
- 開発PCと利用PCは同一
- AVR: Yamaha RX-A4A
- 現在のスピーカー構成: 3.0.2（将来の増減を前提に可変構成として扱う）
- 測定マイク: 未導入
- REW: 未導入。v0.1はファイル取込を主経路とし、実データ入手前は合成fixtureで検証
- 最初の検証シナリオ: MLPでFL/FR基準測定 → 同条件再測定 → 配置A/B比較

## 実装構成

- `backend/`: Python 3.12 / FastAPI / Pydantic / Uvicorn
- `frontend/`: TypeScript / React / Vite
- 保存: SQLite（M03で実装）
- 開発時はViteが`/api`をローカルFastAPIへproxyする
- 配布時はビルド済みUIを同一のPythonプロセスから配信する方針

## 開発開始手順

PowerShellでリポジトリ直下から実行します。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
python -m htdt
```

別のPowerShellで:

```powershell
cd frontend
npm install
npm run dev
```

- Backend: `http://127.0.0.1:8765`
- Health check: `http://127.0.0.1:8765/api/health`
- Frontend dev server: `http://127.0.0.1:5173`

テスト:

```powershell
python -m pytest backend\tests
cd frontend
npm run build
```

## 計画書

| 文書 | 内容 |
|---|---|
| [PROJECT_PLAN.md](docs/PROJECT_PLAN.md) | 目的、対象範囲、再利用方針、アーキテクチャ、段階別の到達点 |
| [PLAN_REVIEW.md](docs/PLAN_REVIEW.md) | 初回・追加レビュー、修正理由、一次資料、未検証事項 |
| [MEASUREMENT_WORKFLOW.md](docs/MEASUREMENT_WORKFLOW.md) | Windows・REWでの測定手順、AVR設定、取込契約、API連携 |
| [DATA_AND_ANALYSIS.md](docs/DATA_AND_ANALYSIS.md) | 履歴・データモデル、座標、比較計算、音響モデル、保存 |
| [IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) | 実装作業単位、依存関係、受入条件、検証データ |
| [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | 確定した実環境、現在の実装状態、次の作業 |

## 決定済みの方針

- Windows-first、単独利用、ローカル完結。
- v0.1はREWテキスト出力の取込から始め、APIがなくても成立させる。
- 配置・AVR設定・マイク位置の不変スナップショットをv0.1から保存する。
- 条件訂正後も保存済み比較を再現し、指定された.mdat・校正原本・設定添付をバックアップへ含める。
- 実測、実測からの計算、予測、原因候補を別の表示・型として扱う。
- 既存のREW Room Simulatorを先に評価し、高度な独自シミュレーションや自動最適化を急がない。
- アカウント、クラウドDB、過剰な認証基盤は作らない。
