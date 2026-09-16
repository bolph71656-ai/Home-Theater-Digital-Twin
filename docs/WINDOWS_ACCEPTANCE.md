# Windows受入手順

> 対象: Windows 11 x64 / 同一PC / Yamaha RX-A4A / 現在3.0.2

M10は「自動化できる保存・比較・復元契約」と「実REW/実測が必要な受入」を分離する。測定マイクとREW実環境が未準備の間、実機互換性を完了扱いにはしない。

## 1. CIで自動確認する合成E2E

`backend/tests/test_e2e_workflow.py` はWindows CI上で次を1本のシナリオとして実行する。

1. 新規Projectを作成する。
2. baseline repeatability / placement A/B用のMeasurement Sessionを作成する。
3. 矩形室、MLP、RX-A4A、3.0.2相当のspeaker snapshotをR1として保存する。
4. R1へFLの合成REW textをSession付きで取り込む。
5. 同じRawAssetを同Session・同repeat groupの再測定として追加し、Datasetは別、RawAssetは重複候補として扱うことを確認する。
6. `.mdat`相当のRaw attachmentを測定へ紐付ける。
7. R1を親にR2を作成し、FL位置だけを変更する。
8. R2へ別FRを同Sessionで取り込み、R1/R2を比較する。
9. 保存済みComparisonのmeasurement snapshotにA/B双方のSession IDが固定されることを確認する。
10. `speakers.FL.position`が意図した変更で、他条件がconfounderになっていないことを確認する。
11. Sessionのmeasurement_countが3になり、R2作成後もR1の座標が変わっていないことを確認する。
12. 保存済みComparisonから自己完結HTML reportを生成し、Dataset IDとSession IDが含まれることを確認する。
13. ZIP backupを作成する。
14. 同じdata directoryでアプリを再生成し、Project/Session/Comparison/指標/整合性が一致することを確認する。
15. backupを別data directoryへrestoreする。
16. Session、R1/R2、3 Dataset、Raw attachment、Comparison resultが同一ID/同一内容で復元され、3測定すべてが同じSession IDを保持することを確認する。
17. restore後のintegrity checkが`ok`になることを確認する。

このシナリオはファイルI/O、SQLite、schema v3、MeasurementSession、FastAPI、比較保存、report、backup/restoreをWindows runner上で横断する。ただしREWそのものやオーディオデバイスは使用しない。

## 2. 実機を用意した後の最終受入

以下は合成fixtureでは代替しない。

1. 使用するREW安定版を記録し、同じ測定をtext exportと読取専用APIの双方で取得する。
2. 実測開始時にMeasurement Sessionを作り、目的、開始時刻、必要なメモを記録する。
3. マイク校正ファイルと測定設定を保存する。絶対SPLを使う場合は校正状態を確認する。
4. RX-A4Aへの実際のHDMI/チャンネル割当を確認し、FL/FR/C/高さのrouting evidenceを記録する。
5. R1でFL/FRを各2回以上測定し、同じSession内のrepeat groupとして取り込む。
6. スピーカーまたはMLPを1項目だけ変更してR2を作り、同じSession・同じ測定条件で再測定する。
7. A/B比較で意図した変更とconfounderを確認し、HTML/JSON reportを保存する。Comparison snapshotのSession IDも確認する。
8. HTDTとREWを終了し、Windows再起動後に同じProject/Session/Comparisonが再現することを確認する。
9. backup ZIPを別フォルダへrestoreし、Session、RawAsset、添付、Dataset、Comparisonが一致することを確認する。
10. REW textとAPI取得の周波数軸・レベル・平滑化来歴を照合する。
11. A04のpeak/dip prominenceと候補対応が実部屋で過検出/未検出にならないか確認し、必要なら既定値を調整する。

## 3. 完了判定

- セクション1がWindows CIで成功: **合成E2E受入済み**。
- セクション2が所有PC・実測データで成功: **M10実データ受入済み**。

実機項目が未実施の間は、アプリ本体の実装が進んでいても「REW互換性」「RX-A4A routing」「測定品質」「実部屋での閾値」を完了扱いにしない。
