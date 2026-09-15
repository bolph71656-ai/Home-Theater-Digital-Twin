# 計画レビューと修正記録

> レビュー日: 2026-09-15
> 対象: mainの6d0c0da99ad69d4f3d8228844a45949c121fff8cにあるREADME.md、docs/PROJECT_PLAN.md
> 範囲: 計画書の検証・詳細化。アプリ実装、Windows実機検証、実測データ検証は実施していない。

## 1. 総合判断

REWを中心に据え、HTDTが部屋・条件・履歴を結び付ける方向は維持する。Windows・個人利用・ローカル完結・過剰なセキュリティを持ち込まない方針も妥当。

修正の中心は、技術の選び直しよりも「既存機能をどこまで使うか」「何を測ったデータか」「どこまで比較・予測できるか」を具体化すること。旧計画には章間の矛盾、所有機器の未確認前提、履歴の後回し、音響モデルから得られる情報の過大評価につながる記述があった。

## 2. 旧計画からの主な変更

| ID | 種類・優先度 | 旧計画の該当箇所 | 問題と修正 |
|---|---|---|---|
| R01 | 矛盾・高 | §6.1、§23 v0.1 | APIを第一経路としながらv0.1はファイル先行。**v0.1=ファイル、v0.2=任意API**に統一 |
| R02 | 再利用不足・高 | §5、§18、§19 | REW Room SimulatorとAPIを評価せず独自予測へ進む構成。**REW再利用評価を先行**し、追加エンジンは不足がある時だけ |
| R03 | 履歴要件の矛盾・高 | §12、§23 v0.2 | 配置変更比較がMVPなのにLayoutRevisionがv0.2。**配置・部屋状態・AVR条件・測定点のスナップショットをv0.1へ** |
| R04 | データモデル不足・高 | §12 Measurement | 「1チャンネル×1席」だけでは低音転送やL+Rに対応できない。**入力役割と実際の音源群を分離** |
| R05 | 条件不足・高 | §8、§17 | room_correctionの単一enumだけでは比較を再現できない。**EQ、音場モード、距離、ゲイン、低音振り分けを別保存** |
| R06 | 精度の前提不足・高 | §6.3、§9、§20 | spl_db配列だけでは絶対SPL/相対値の区別や補正状態を保てない。**単位、校正、窓、平滑化、時間原点、来歴を必須化** |
| R07 | 未確認前提・高 | README、§8.2 | RX-A4A、Windows 11、USBマイクが所有・確定情報として読める。**ユーザー制約と検証環境案を分ける** |
| R08 | 出力経路の前提不足・高 | README、§3、§10 | Atmos配置と個別測定可能性の区別がない。**チャンネル対応を実確認**し、未対応高さは配置管理のみでも可 |
| R09 | 数式の適用条件不足・高 | §9、§17、§18 | 境界距離だけのSBIR候補では幾何条件が曖昧。**実音源/鏡像の経路差**を使い、c/(4d)は限定近似とする |
| R10 | 最適化の成立条件不足・高 | §19、§23 v1.0 | モード周波数だけでは位置依存の応答を評価できず、点音源でtoe-inも評価できない。**実測候補比較を先行、予測探索は条件付き** |
| R11 | 過度な一般化・中 | §9.4、§18 | image-sourceと低域の関係を一括りに読める。**モデルの理論的性質と実部屋の再現性を分離** |
| R12 | 保存設計不足・高 | §13、§23 v1.0 | 外部配列・原本とDBの整合、復元、移行が曖昧。**初期はSQLite BLOB、原本確保→DB commit、復元をv0.1へ** |
| R13 | 実装順序の矛盾・中 | §14、§23 v0.5、§26 | グラフをMVPで作るのにライブラリ最終選択をv0.5で評価。**最初のグラフで第一候補を評価**し未達時のみ比較 |
| R14 | 座標契約不足・中 | §11 | 位置軸だけで姿勢、handedness、Three.js変換が未定義。**方向ベクトルと変換を規定** |
| R15 | 工程不足・高 | §20、§23–26 | 完了条件が抽象的で実ファイル・異常系・数値許容差がない。**作業ID・依存・fixture・受入条件を追加** |
| R16 | 運用の表現修正・中 | §2.3、§22 | 127.0.0.1だけで安全対策が完結すると読める。**同一originと軽い入力検証**を加え、認証基盤は導入しない |

「資料上誤り」と「実装前に必要な追加仕様」は区別した。例えば旧計画のREW API既定ポートや自動スイープのライセンス注意は大筋で正しく、そのまま精密化している。採用ライブラリがすべて不適切だったという評価ではない。

## 3. 調査から変えた判断

### REWでできることを先に使う

公開資料でRoom Simulatorと連携口の存在を確認した。HTDTでは既存モデルの結果と配置・条件を結び付ける作業を優先する。取得可能なデータの範囲、対象版、座標対応は実装時に確認する。[REW API](https://www.roomeqwizard.com/help/help_en-GB/html/api.html)

.mdatを直接読む設計は引き続き採用しないが、REWの再解析用原本としての価値は残す。HTDTがファイルを解析しないことと、原本を保管しないことを混同しない。

### 「比較できる」の意味を先に決める

表示できる2本の曲線が、同じ条件で比較できるとは限らない。差分、形状比較、複素和は必要条件が異なる。保存した比較設定に帯域・補間・レベル調整・算法版を持たせる方針は、この制約からの設計判断である。

### 機器依存の機能をMVPから切り離す

メーカーの具体例を所有機器の確定情報にしない。サブなしや高さチャンネルの扱いは、実際の音声経路を確認して決める。Yamaha資料はYamahaの機能の根拠であり、他メーカーのAVRにも同じ挙動があることの証拠としては使わない。

### 計画を早期に固定しすぎない

旧書の「基礎的なアーキテクチャ判断を再度開かずに実装できるまで固める」という目標を変更した。ドメインとデータ不変条件は明確にする一方、実データ未確認のparser契約やWindows未検証の依存は暫定に留める。

pyroomacousticsの公開説明には新しい版表示と古いPython/Windows導入説明が併存する。説明文だけで対象環境のwheel提供や正常動作を保証しない。必要になった時点で実際の配布物と導入結果を確認する。[pyroomacoustics公式リポジトリ](https://github.com/LCAV/pyroomacoustics)

## 4. 一次資料と用途

以下は2026-09-15に内容を参照した資料。Web上の説明は更新されるため、使用版・導入手順・互換性は実装時に改めて固定する。

| 資料 | この計画での用途 | 検証の限界 |
|---|---|---|
| [REW API](https://www.roomeqwizard.com/help/help_en-GB/html/api.html) | 読取連携、配列形式、識別子、Room Simulator連携の設計 | 所有PCのREWビルドでの提供を未確認 |
| [REW File Menu](https://www.roomeqwizard.com/help/help_en-GB/html/file.html) | テキスト/IRの出力設定が必要という判断 | 実サンプルでのparser互換性は未検証 |
| [REW Soundcard Preferences](https://www.roomeqwizard.com/help/help_en-GB/html/soundcard.html) | Windowsの入出力とEXCL経路の確認項目 | 実際のHDMI/マイクの動作保証ではない |
| [REW Making Measurements](https://www.roomeqwizard.com/help/help_en-GB/html/makingmeasurements.html) | レベル・スイープ・時間基準の記録項目 | 部屋と機器に適した設定値は未決定 |
| [REW Analysis Preferences](https://www.roomeqwizard.com/help/help_en-GB/html/analysis.html) | タイミング・解析設定の来歴 | サンプルに適用された状態は取込時に確認 |
| [REW Impulse Graph](https://www.roomeqwizard.com/help/help_en-GB/html/graph_impulse.html) | IR/ETCを比較する際の処理条件 | HTDT算法と数値一致することは未検証 |
| [REW Room Simulator](https://www.roomeqwizard.com/help/help_en-GB/html/modalsim.html) | 既存ソルバー優先、矩形モデルの適用範囲 | 非矩形室や所有スピーカーへの精度保証なし |
| [REW EQ Window](https://www.roomeqwizard.com/help/help_en-GB/html/eqwindow.html) | EQは既存機能へ委ねる方針の確認 | AVRへ適用できるフィルター形式は対象外 |
| [Yamaha RX-A4A User Guide](https://data.yamaha.com/files/download/other_assets/5/1335595/AV19-0070_RX-A4A_user_guide_En_UCRABGLFP_H0.pdf) | 低音転送、Subwoofer None、Parametric EQの設定を分ける例 | ユーザー所有機種であることを示さない |
| [Yamaha RX-A4A スピーカー構成](https://manual.yamaha.com/av/20/rxa4a/en-US/5449845643.html) | 機種ごとに構成制約を確認する例 | 汎用の5.x/7.x/Atmos保証に転用しない |
| [Microsoft Spatial Sound](https://learn.microsoft.com/en-us/windows/win32/coreaudio/spatial-sound) | 通常出力とSpatial Audio対応を分離 | REWで個別高さ出力が可能なことの証拠ではない |
| [Genelec Monitor Placement](https://www.genelec.com/monitor-placement) | 境界干渉・位置依存性の説明を確認 | 特定の部屋の谷の原因を確定しない |
| [pyroomacoustics](https://github.com/LCAV/pyroomacoustics) | 既存image-source/RIRエンジン候補 | Windows/Pythonの対象組合せは未検証 |
| [SQLite Backup API](https://www.sqlite.org/backup.html) | 稼働中DBの整合したバックアップ方式 | 別保存のrawを自動で含める機能ではない |

数式、データモデル、工程、初期性能目標はこれらを踏まえたHTDTの設計提案であり、外部製品の公称仕様として提示していない。

## 5. 今回の改訂後に残る確認事項

| 未確認事項 | 必要になる段階 | 準備するもの |
|---|---|---|
| 実際のAVR・マイク・Windows環境 | v0.1開始前 | 型番、OS、経路、REW版 |
| 対応するREW出力の厳密な書式 | parser実装前 | FL/FRと再測定の実サンプル |
| 部屋の形と寸法精度 | 配置編集/音響候補 | 概略図と座標 |
| 絶対SPL校正の有効性 | 絶対値比較 | 校正と入力ゲインの記録 |
| APIとIRの扱い | v0.2開始時 | 対象版仕様・応答fixture・IR出力条件 |
| 予測モデルの有効性 | v0.5/探索前 | 比較可能な複数配置の実測 |
| グラフ・保存の実性能 | 初期縦断実装 | 対象Windows PCと代表サイズのデータ |

これらは今回の文書改善を止める理由ではない。未確認を明示した状態で計画を完成させ、実装開始後に必要な順で確認する。
