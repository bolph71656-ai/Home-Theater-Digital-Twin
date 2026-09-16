# 計画レビューと修正記録

> レビュー日: 2026-09-15（初回・追加）
> 初回対象: 6d0c0da99ad69d4f3d8228844a45949c121fff8cのREADME.md、docs/PROJECT_PLAN.md
> 追加対象: mainの10dabf995453e1351fce32e2041790c925d2e31bにある計画6文書
> 範囲: 計画書の検証・詳細化。アプリ実装、Windows実機検証、実測データ検証は実施していない。

**最新のCAD-firstレビューは[§7](#7-cad-first追加レビュー2026-09-16)を参照。§1–6は当時の判断の記録であり、旧browser方針を今後の指示として適用しない。**

§1–5は初回レビューの記録を残す。追加レビューの指摘と反映先は[§6](#6-追加レビュー)を参照。現在の仕様は各設計文書を正本とする。

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

## 6. 追加レビュー

### 結論と修正箇所

前回のREW優先・ファイル取込先行・Windows個人利用という方針は維持する。追加レビューでは、実装時に異なる解釈が生まれるデータ契約と、比較の再現性を損なう不足を修正した。新しい測定エンジンや依存ライブラリは追加していない。

| ID | 優先度・種類 | 対象箇所 | 問題と反映した修正 |
|---|---|---|---|
| R17 | 高・外部仕様の見落とし | 測定§5、データ§4 | REWテキストは位相なしでも0.0を出力する。列の存在から有効位相と判定せず、phase_statusと出所を保持 |
| R18 | 中・処理条件不足 | 測定§7 | APIのppo指定は追加平滑化を伴い得る。内部の96 PPO再標本化と分け、取得要求と実際の処理状態を保存 |
| R19 | 高・分類の矛盾 | データ§2、測定§5/8 | derived分類が後回しで、予測にも実測Contextを要求し得た。4分類をv0.1から保持し、予測に架空の実機条件を割り当てない |
| R20 | 高・履歴契約不足 | データ§1/4 | 不変配置だけではマイク訂正・再解析・算法更新後の比較が変わり得る。Measurement/Dataset/Contextの版を固定参照し、比較結果も保存 |
| R21 | 高・数値契約不足 | データ§6 | 全表示曲線の共通帯域では第三曲線がA/B指標を変える。ペア別帯域、固定グリッド、除外区間、点数不足・基準帯域不足の挙動を定義 |
| R22 | 高・品質条件不足 | 測定§4、データ§5 | 有限の数値でもクリッピング等の不良測定はあり得る。品質状態と理由、繰返し差を保持し、改善の判定と分離 |
| R23 | 高・保存範囲不足 | データ§9、測定§4 | .mdat・校正の保管方針に具体的な添付参照がなかった。RawAssetと参照、任意添付、完全バックアップの対象・欠損時の失敗を定義 |
| R24 | 中・重複の扱い不足 | 測定§5 | ハッシュだけでは再取込/同一測定の再出力/独立測定を区別できない。原本の重複排除と測定の同一性を分離 |
| R25 | 中・工程の矛盾 | ロードマップ§3/4、全体§10 | 復元が実A/B比較完成に依存していた。DB直後に最小復元を行い、v0.2/v0.5の全機能をv1.0の必須工程にしない |

### 一次資料の再確認と設計判断

- R17は[REW File Menu](https://www.roomeqwizard.com/help/help_en-GB/html/file.html)の位相なし出力仕様に基づく。形式プロファイルも1測定1ファイル、数値形式・出力設定の記録へ具体化した。
- R18は[REW API — Frequency response](https://www.roomeqwizard.com/help/help_en-GB/html/api.html)のppo指定時の平滑化に基づく。対象ビルドの応答での検証はA03で実施する。
- R22のクリッピングによる応答誤差は[REW Making Measurements](https://www.roomeqwizard.com/help/help_en-GB/html/makingmeasurements.html)に基づく。品質状態・A→B→A・繰返し差の扱いはHTDTの設計提案であり、統計的な有意差を保証するものではない。
- 版参照、固定グリッド、保存済み結果、添付管理、工程変更は、このプロジェクトの要件から導いた設計判断。外部製品の仕様と混同しない。

### 確認と残る制限

指摘はREADMEと設計4文書へ反映し、ロードマップのF12–F18と数値・復元受入条件へ結び付けた。文書6本の差分、内部リンク/見出し参照18件、M01–M10の依存関係に循環がないこと、96 PPOグリッドと一定レベル差の数式を確認した。parser・バックアップの実装や実機での精度は未検証である。

対象Windows、REWビルド、実測・出力サンプルは引き続き未確認。これは文書修正の未完了ではなく、P0-01〜P0-05と各追加機能の開始時に確認する事項である。

## 7. CAD-first追加レビュー（2026-09-16）

### 対象・方法

- main: [1b510206](https://github.com/bolph71656-ai/Home-Theater-Digital-Twin/commit/1b510206e7c2fe84ff15fe544a6e3fe2d896dc84)
- 実装track: [PR #37 / 初回9724f4b](https://github.com/bolph71656-ai/Home-Theater-Digital-Twin/tree/9724f4b84aa34b32a77a169b73ce68290de69fdd)、[追加確認0353768](https://github.com/bolph71656-ai/Home-Theater-Digital-Twin/tree/035376816c755f2917119a730c415c31f9ea0d6e)
- mainの計画・状況・幾何/データ契約、models/geometry/依存/CIとPRのspatial_editor/進捗文書を確認。レビュー中の追加commitについてnative_editor、run-native、依存pinも確認。
- 13のOSSで選定したソースをcommit固定で確認。コード・symbol・採否は[OSS調査](CAD_EDITOR_OSS_RESEARCH.md)。
- 今回は計画レビューと文書修正。native GUI実装、依存追加、Windows実機再検証は行っていない。

### 指摘と反映

| ID / 優先度 | 所見 | 反映 |
|---|---|---|
| C01 / 高 | PROJECT_PLANはReact/Three.js、native保留、3D後回しのまま。UI_DESIGNもbrowser画面とmobile受入が主仕様 | 両文書をCAD-firstへ改訂、正本の責務を統一 |
| C02 / 高 | IMPLEMENTATION_STATUSは次工程をO20と記載。実測待ちだけが主blockerに読める | N05先行、O20保留、実機測定trackを独立表記 |
| C03 / 高 | 初回headにはshell未掲載。追加0353768でshell/起動/依存pinが入ったが、編集とSave/UndoのGUI接続・package受入は未完 | 追加実装を認めてstatus更新。main/branch/報告/未確認を分離し、N05で通し受入 |
| C04 / 高 | 一測定点Contextを全Sceneへ拡張すると家具/複数席/測定との責務が混在 | SceneRevision、WorkingDocument、AcquisitionContext、ViewStateを分離 |
| C05 / 高 | Snapshot履歴のis_dirty=index!=0ではSave後clean/Undo分岐を表現できない | content hash、Save成功後clean、no-op、redo分岐、失敗/復旧仕様 |
| C06 / 高 | 壁を端点ID列だけで識別するとsplit/mergeで開口/制約が失われる | 安定wall ID、影響確認、制約revision、原子的Undo、G10対応表 |
| C07 / 高 | VTK transformをdomainの左手系へそのまま戻すと向き/面/左右を誤る | 一箇所の座標adapter、方向/法線/winding、非対称fixture |
| C08 / 高 | PyVista callbackは確認commitでmatrix更新より先、camera styleも変更する | HTDT transactionとadapter、最終値再取得、cancelとobserver解放 |
| C09 / 中 | snapがworld距離だけではzoom/DPIで操作感が変わる。入力競合・capture lossが未定義 | screen距離/hysteresis、優先順位、入力表、Esc/Alt+Tab/画面外release |
| C10 / 高 | 重い計算をthread外に出すだけでは、古い結果が編集済みsceneへ適用される | immutable job input、generation、取消/stale、GUI thread境界 |
| C11 / 中 | 保存復旧/配布がN90に集中し、N20のsnap範囲も過大 | N05の縦断package、N10復旧、N20a/b・N30a/b、独立可能なN50/N60 |
| C12 / 中 | 1000 entityで実用的等の評価が曖昧、Godotが無条件fallback | fixture/計測手順/目標値、原因別の代替比較。計測済みと表示しない |
| C13 / 中 | 多数のOSS名と一般URLだけでコード根拠・取得可否が追えない | 固定commit/path/symbol、確認範囲、license根拠、Sweet Home 3Dの404を訂正 |
| C14 / 中 | 旧API/domain契約維持やfeature parityが互換不要方針を弱める | 新schema開始可、必要なadapterだけ再利用、旧frontendの凍結/廃止条件 |

### 決定・未完事項

Qt/VTKは第一実装として維持する。選定理由を「WindowsなのでWebは不適」から、Python解析/科学可視化/操作を統合する費用の比較へ修正した。Godot/C#/TypeScriptも、N05/N20の未達原因に応じて比較できる。

新しい[編集契約](CAD_EDITOR_SPEC.md)と[受入仕様](CAD_EDITOR_ACCEPTANCE.md)は実装前仕様。初期数値目標・snap半径・配布候補はWindows受入で確認/調整する。旧PoCの版で今回のソース所見を再現したとは主張しない。

### この改訂の検証

14文書の内容整合、80のrelative link、milestone ID、旧方針の残存、28の固定commitソースリンク、変更範囲を確認した。文書のみのため新規testは追加していない。既存CIの結果とGitHub反映先はこの変更のPRに記録する。Windows実機gateは未実施。

次工程はPR #37へ本改訂を取り込み、N05の選択→移動→取消/Undo→保存/reopen→packageをGitHubから再現可能にすること。
