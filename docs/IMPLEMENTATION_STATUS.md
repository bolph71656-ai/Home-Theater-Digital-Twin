# 実装ステータス

> 更新: 2026-09-18 / N90 stable Windows 0.1.0 A15 PASS / O60 software validation main反映済み・実室model gate未通過
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)。旧browser/backendの詳細履歴は[2026-09-16 archive](IMPLEMENTATION_STATUS_ARCHIVE_2026-09-16.md)へ保存する。

## Native CAD — 現在地

**N05〜N90のnative CAD release pathとO10〜O60 software authorityは実装済み。O60はPR #78 merge `b0b56497255425b5b343c6f5f52763d11dbf5ee6`でmain反映済み。N90 stable Windows 0.1.0はproduct CI #458、release artifact #23、owned-Windows A15をPASSした。実室の独立validation evidenceはまだ無いため、O70/O80 automatic recommendation/extended searchはdisabledのまま。**

N70はIssue #63 / PR #64、N80 workspaceはIssue #65 / PR #74、O60 software validationはIssue #75 / PR #76・#78で完了済み。N90はIssue #77 / PR #79でstable Windows releaseを実装し、A15を通過した。N80a最終製品コード変更は `c6cc15e76edbc1ac263911ee084803ca1e32b42c`、accepted gate/headは `ff4dc8078eb9ca0b3effaed66b523cff175fea1a`。

| 区分 | 現在の状態 |
|---|---|
| main | **N05〜N90 stable releaseとO10〜O60 software authorityをmerge済み**。N90 PR #79 merge `d1f0f7cf1bf24e4590954071d78c9ac281fc15b9` |
| N80 tracking | Issue #65（closed） / Issue #67（O20 closed） / PR #74 merged |
| O60 tracking | Issue #75 / PR #76（implementation history） / PR #78 merged。final head `ce92d6d04e3ca7463fdf8cfc002e271ffdc00bc3`、CI #427 PASS |
| O60 validation state | software gate実装済み。owned-room calibration/holdout/repeatability evidence未登録のため、実model validatedとは扱わない |
| N80a last product-code head | `c6cc15e76edbc1ac263911ee084803ca1e32b42c` |
| N80a accepted gate head | `ff4dc8078eb9ca0b3effaed66b523cff175fea1a` |
| N80a product CI | #321 / run `35280237062` PASS |
| N80a acceptance docs CI | #324 / run `35286052855` PASS |
| N70 tracking | Issue #63 / PR #64（完了） |
| N70 last product-code head | `76c21eed7d7efcff23905e8af977854669df2752` |
| N70 accepted gate head | `2a6eaae351beb8b2cbbef23a07e3054bb4fb1c93` |
| acceptance docs head | `bff12d4a379a5458f7dcf6cfa7e2b55b570ea4ec` |
| product CI | #309 / run `35270706491` PASS |
| final harness CI | #312 / run `35272332747` PASS |
| acceptance docs CI | #313 / run `35276546531` PASS |
| A13 | stale、UI responsiveness、明示cancel、document change、clean close/no worker PASS |
| A14 | 8頂点L-room、rectangular-only model=`unsupported`、無silent approximation、overlayなし、scalar control gated PASS |
| F5 | 50 editable objects＋10,000 markers、1 non-pickable actor、初回11.406 ms、orbit p95 27.963 ms PASS |
| native entry | `htdt-native` / `run-native.ps1` / `python -m htdt.native_cad` はN80a `OptimizationWorkspaceWindow` compositionを起動 |
| browser UI | 新CAD機能は凍結。native release CIからfrontend buildを除外済み。二重実装しない |
| N90 stable product head | `968a9461435ac37138ddd15526140c06613fccb8` / CI #458 PASS / Windows Release Artifact #23 PASS |
| N90 accepted gate head | `3ee2fb91b4976d7b0cac7b13718222cd6e359b76` / A15 owned-Windows PASS |
| stable version | `0.1.0` |
| 次工程 | **O60R software audit gateはPR #85でmain反映済み。実室でpreregistered O60E campaignを作成し、human-operated配置変更/REW測定でowned-room evidenceを収集する。O70/O80はeligible campaign-backed ValidationRecord + O60R audit PASSまでdisabled** |

## N90 — stable Windows release / A15 PASS

詳細: [N90 Windows acceptance](N90_ACCEPTANCE_2026-09-18.md)

- stable product version: `0.1.0`
- product/artifact head: `968a9461435ac37138ddd15526140c06613fccb8`
- final A15 gate head: `3ee2fb91b4976d7b0cac7b13718222cd6e359b76`
- CI #458 / run `35299355927`: PASS
- Windows Release Artifact #23 / run `35299355977`: PASS
- gate-harness fix CI #459 / run `35300374434`: PASS
- SQLite backup API + version/hash manifest + measurement asset verificationを実装。
- packaged `--backup` / `--restore` / `--version` はQApplication生成前に実行する。
- committed Windows dependency lockからPyInstaller onedir packageを再現する。
- stable AppIdのper-user Inno Setup installerを採用し、program rootとuser-data rootを分離する。
- uninstallはuser dataを削除しない。
- native release CIを正本とし、frontend buildはnative releaseの必須gateから外した。
- owned Windowsで `0.1.0.dev0 -> 0.1.0` update、backup/restore、reopen、uninstall/reinstall、data retentionを一連でPASS。
- gate後はowned-PC repoを元のdetached SHA `5ede848e8e0b0967a50c04c83ff679a649ca439b`へ戻し、clean statusを確認した。

## N70 — 完了内容

### Prediction authority / persistence

- prediction resultをexact native `SceneRevision`、scene content hash、model ID/version、canonical parameters、canonical input snapshotへimmutable bindingする。
- 完了結果のrequest identityをsubmission時identityと照合し、入力取り違えを保存しない。
- measured evidence、prediction、仮説を同じ証拠種別として扱わない。
- legacy `Context`をnative prediction authorityへ昇格させない。

### Geometry compatibility

- axis-aligned rectangular roomは既存のroom-mode / first-order image-source geometryをnative Sceneへadapter接続する。
- 非矩形polygon roomへ矩形専用modelを無言で適用しない。
- F2の8頂点L-roomでは`unsupported`を明示保存し、mode/reflection payloadやoverlayを生成しない。
- 将来rectangular approximationを使う場合は、exact polygonとは別にapproximation rule/error/useを明示保存する。

### Native prediction workspace

- 日本語`予測` dockを既存right-side CAD tab stackへ統合した。
- saved prediction history、model/assumption/compatibility/input revisionを表示する。
- direct path、first-order reflection path/pointはnon-pickable analysis overlayとして表示する。
- room-mode frequency候補はpredicted geometryとして表示し、空間SPL fieldと偽装しない。
- validated scalar fieldが存在する場合だけheatmap/slice/volume controlを有効化する。

### Async stale/cancel boundary

- prediction計算はGUI thread外で実行する。
- job tokenはsubmission時のdocument/revision/content hash/model/inputを固定する。
- edit、cancel、document switch後に遅延完了した結果をcurrent sceneへ自動適用しない。
- close時にworkerを残さない。

### F5 bulk marker rendering

- 10,000 analysis markersを1 marker=1 actorにしない。
- arbitrary `N×3` domain point cloudを1つの`PyVista.PolyData`へ変換し、1 mesh actorとして描画する。
- marker actorはnon-pickableで、editable scene entityと分離する。
- owned PCで50 editable objects＋10,000 markersを計測し、first render `11.406 ms`、orbit p50 `22.993 ms`、p95 `27.963 ms`、max `31.205 ms`を記録した。
- F5の64^3 scalar gridは「後続」。validated scalar-field modelがない現段階ではsynthetic fieldを生成しない。

## N70 Windows受入

詳細: [N70 Windows acceptance](N70_ACCEPTANCE_2026-09-18.md)

最終受入環境:

- Windows 11 Pro build 26200
- Ryzen 7 8845HS / Radeon 780M / 31.31 GiB
- Radeon driver 32.0.13032.11
- 2880×1800 / AppliedDPI 192 (200%)
- Python 3.12.10
- PySide6 6.11.2
- PyVista 0.49.0
- VTK 9.7.0
- PyQtGraph 0.14.0

Final gate:

```text
A13_N70_RESULT PASS
A14_RESULT PASS
N70_A13_A14_RESULT PASS
F5_RESULT PASS
N70_GATE_A13_A14_EXIT=0
N70_GATE_F5_EXIT=0
N70_RESTORED_SHA=5ede848e8e0b0967a50c04c83ff679a649ca439b
N70_POST_STATUS_COUNT=0
N70_RESTORE_OK=True
N70_HARDWARE_GATE_RESULT=PASS
```

A14はN70–N80にまたがるgate。今回の`unsupported` branchでは候補を生成しないためapply/Undoは発生しない。候補preview/適用と1-command UndoはN80でSearchSpec/O10/O20接続後に検証する。

## 継承済みCAD基盤

- N20b: multi-select、common pivot、object/grid/angle snap、hide/lock、entity Undo/Redo。
- N30a: 凹polygon room、stable RoomVertex、頂点挿入/移動/削除、edge寸法、ceiling height、self-intersection拒否。
- N30b: stable wall ID、opening、wall clearance binding、wall move/split/merge/delete、参照migration、曖昧操作拒否、room/topology atomic transaction。
- N40: speaker / seat / screen / furniture / AV equipment / measurement point、3.0.2 template、duplicate、寸法、acoustic reference、explicit aim。
- N50: G10 adapter、allowed/exclusion、walkway/wall clearance、constraint reason overlay、invalid commit rejection。
- N60: immutable measurement/revision binding、REW import/read、FR dock、historical ghost、A/B comparison、stale/cancel guards。
- N70: immutable prediction authority、geometry compatibility、prediction overlays、async guards、bulk marker rendering。

実機受入記録:

- [N05](N05_ACCEPTANCE_2026-09-16.md)
- [N10](N10_ACCEPTANCE_2026-09-16.md)
- [N20a](N20A_ACCEPTANCE_2026-09-16.md)
- [N20b](N20B_ACCEPTANCE_2026-09-17.md)
- [N30a](N30A_ACCEPTANCE_2026-09-17.md)
- [N30b](N30B_ACCEPTANCE_2026-09-17.md)
- [N40](N40_ACCEPTANCE_2026-09-17.md)
- [N50](N50_ACCEPTANCE_2026-09-17.md)
- [N60](N60_ACCEPTANCE_2026-09-17.md)
- [N70](N70_ACCEPTANCE_2026-09-18.md)

## N80 — workspace完了 / O60独立継続

N80a（native SearchSpec + candidate workspace）はWindows実機受入を完了した。詳細: [N80a Windows acceptance](N80A_ACCEPTANCE_2026-09-18.md)。

- last product-code head: `c6cc15e76edbc1ac263911ee084803ca1e32b42c`
- accepted gate head: `ff4dc8078eb9ca0b3effaed66b523cff175fea1a`
- product CI #321 / run `35280237062` PASS
- final gate CI #323 / run `35280664154` PASS
- A13 stale/cancel/document/clean close PASS
- A14 SearchSpec→candidate preview→1-command apply→1 Undo exact restore PASS

N80 workspaceはPR #74で完了しmain反映済み。O20〜O50のprediction/objective/Pareto/measurement-loop authorityをnative CADへ接続し、N80c/O50 owned-Windows acceptanceもPASSした。O60 full validationはIssue #75 / PR #76へ分離して継続する。

- PR #70: objective-vector / Pareto algorithms + immutable native objective/Pareto persistenceをmerge済み。
- PR #71: position-only REW Room Simulator transaction + native Scene/SearchSpec/Candidate adapterをmerge済み。CI #345 PASS。
- O20 exact batch spec / candidate attempt / resume-cancel persistenceとowned-Windows writable gateはIssue #67で完了・close済み。
- N50/N60/N70とO20〜O40の該当gateを前提にする。
- SearchSpec編集とO10候補集合をnative Sceneへadapter接続する。
- 候補preview/適用は1 commandでUndo可能にする。
- hard constraintとobjectiveを混同しない。
- objective vectorを保持し、Pareto比較を基本表示にする。
- 「音質総合点」へ縮約しない。
- 実測loopへ接続する場合も、独立検証前に自動推薦へ昇格しない。

N70で外部solverを暗黙採用しなかった方針を維持する。REW Room SimulatorはS01相当、polygon predictorはS03相当のWindows/座標/精度/性能/再現性証拠を通過した場合だけprediction authorityとして追加する。
### PR #74 — N80c / O50 / O60 現在地

- native Pareto比較はSearchSpec/Scene/constraintのstale状態をfail-closedし、候補間でobjective集合またはunitが不一致なら比較を保存しない。
- 同一semantic Pareto snapshotはSHAで再利用し、ボタン再実行で同一内容を重複保存しない。
- provenance列は `evidence_class:source_kind:source_id` を表示し、measured/predicted等を潰さない。
- O50 Measurement PlanはSearchSpecからcandidateを再生成し、candidate-set SHAと、候補を適用したexact Scene content hash、直接parent revisionまで検証して保存する。
- native最適化dockに実測キューを追加し、同じapplied SceneRevision/content hashのN60 `measured` evidenceのみを明示選択して `planned -> measured` のappend-only履歴へ関連付ける。
- O60 validationはcalibration/holdoutを候補単位で分離し、exact SearchSpec/candidate-set/model version/prediction attempt/Measurement Planへcross-evidence bindingする。
- holdout residualは `pass/fail/insufficient` として保存するが、これだけでrecommendationを有効化しない。trend/rank、sensitivity、repeatabilityの独立検証が未成立ならrecommendation gateはdisabledのまま。
- O70 adaptive plannerはO60の実データgate未通過のため自動推薦としては未実装・無効化を維持する。


## N80c / O50 acceptance

PR #74 product head `2a891dbc1796d3cfdaebbe762d0d6e0d2636563f` はCI #397 / run `35294094501`をPASSし、gate head `44628a1e51c199c10b883ed8accba452578bb1eb`でowned-Windows受入もPASSした。

- Pareto比較・evidence provenance・semantic snapshot de-dup: PASS
- candidate apply/save → exact SceneRevision Measurement Plan: PASS
- exact revisionのN60 measured evidence関連付け: PASS
- planned→measured append-only history: PASS
- stale SearchSpecでのPareto再計算拒否: PASS
- gate後のローカルcheckout復元/clean status: PASS

詳細は [N80c/O50 Windows acceptance](N80C_ACCEPTANCE_2026-09-18.md)。

N80 workspaceのIssue #65完了条件はこの受入で満たす。残るO60 full validationはIssue #75で独立継続し、trend/rank・sensitivity・repeatabilityと実データgateが成立するまでO70 automatic recommendationはdisabledを維持する。


## O60 — full model-validation implementation

PR #76 final head `ce92d6d04e3ca7463fdf8cfc002e271ffdc00bc3` はCI #427 / run `35295833407` PASS。connector上のdraft状態を解除できなかったため、同一headをnon-draft merge-only PR #78でmainへmergeし、merge commitは `b0b56497255425b5b343c6f5f52763d11dbf5ee6`。

- calibration / holdout candidateを分離し、両方が無ければrecommendation gateを開かない。
- objectiveごとのholdout pairwise-ordering agreementを保存し、tie/insufficient/failを独立表示する。
- placement perturbationのobserved sensitivityとprediction error / mをobjectiveごとに保存する。
- 同一SceneRevisionの再測定からrepeatability floorを算出し、candidate差がnoise floor以下ならgateを停止する。
- geometry/band/routing等のapplicability checkとstop reasonをimmutable recordへ保存する。
- O20 prediction attempt、O30 objective evaluation、O50 Measurement Plan、N60 measured evidence、SearchSpec/candidate-set SHAをrepository save時に再照合する。
- `synthetic_fixture` はrecommendation eligibleにならない。`owned_room` は参照measurement provenanceの `validation_scope=owned_room` も必須。
- native最適化dockでresidual / trend / sensitivity / repeatability / applicability / stop reasonを別々に表示する。
- O70向けには永続化済み `eligible` recordだけを取得するAPIを設けたが、Adaptive Planner自体は実室O60 gate通過まで実装・有効化しない。

このCI PASSは算法・authority実装の検証であり、REW Room Simulator等の特定modelが実室で妥当と証明されたことを意味しない。現時点ではowned-roomのcalibration/holdout/repeatability evidenceが無いため、O70 recommendation gateはdisabled。


## O60E — owned-room validation campaign / software authority完了

Issue #81 / PR #82。product head `e3bdd111cfb2ed0487cdf98d93adfa58e759532b` は
CI #512 / run `35305119035` PASS。O60 real-data gateを実測後の恣意的splitから保護する
preregistration authorityとnative workflowを実装した。実室campaignそのものはまだ実施していない。

- calibration / holdout candidateを測定前にimmutable固定する。
- exact SearchSpec / candidate-set SHA / model version / target response / evaluation band / thresholdをcampaign hashへ含める。
- stale SearchSpec/current constraint mismatch、SearchSpec SHA mismatch、candidate-set SHA mismatchをfail-closedする。
- sensitivity / repeatability / candidate separation / applicability requirementsを事前固定する。
- 対象candidateにmeasured Measurement Planが存在した後のcampaign新規登録を拒否する。
- campaign作成時刻より前にcapturedされたmeasurementをowned-room validation evidenceへ使わない。
- REW APIのtimezoneなしlegacy日時はhost local timezone ruleでoffset-aware ISOへ正規化し、raw値/解釈元をprovenanceへ残す。
- generic N60 importはvalidation evidenceへ自動昇格しない。明示的なCampaign REW読込だけが
  `measured + validation_scope=owned_room + validation_campaign_id` を保存する。
- O20 prediction / O50-N60 measured evidenceから、campaignと完全一致するO30 objective vectorを同じtarget responseでmaterializeする。
- readinessはmissing/ambiguous evidenceをcandidate単位で表示し、自動測定や自動推薦を行わない。
- applicabilityはgeometry/band/routingを未確認/PASS/FAILで明示し、PASSには確認根拠を必須とする。
- owned-room ValidationRecordはcampaign ID/SHAへbindingし、repository saveとO70 entry取得時に再検証する。
- synthetic fixtureはeligibleにならず、O70/O80はgenuine owned-room campaignがO60全gateを通過するまでdisabledを維持する。

N90 stable 0.1.0のacceptanceは完了済みで、O60E software authorityのためにRDC/N90実機gateは再実行していない。

## O60R — real-data audit software gate / main反映済み

Issue #83 / PR #85で、実室campaign完了後に使うread-only監査harnessをmainへ追加した。

- source `cad-scenes.sqlite3`はSQLite `mode=ro` / `query_only=ON`で開く。
- committed WALを含む一貫snapshotをtemp DBへ作り、full save-time authority replayはsnapshot上だけで実行する。
- current O70-entry ValidationRecord、campaign ID/SHA、readiness、residual/trend/sensitivity/repeatability/separation/applicabilityを再検証する。
- clean worktree / exact product-head ancestor / checkout restoreをWindows runnerが保証する。
- CI preflightはPASS済み。実室PASSはまだ主張しない。
- `inventory_o60_owned_room.py`でcampaign/readiness/REW read-only状態を1コマンド確認できる。
- owned-Windows inventory preflightで検出したtemp SQLite `WinError 32`に対し、Search/RoomSim/Objective/ModelValidation repositoryの接続を明示closeへ統一し、DB存在時のinventory cleanup回帰testを追加した。
- 残る作業は人手のspeaker/setup移動とREW実測を伴うowned-room campaign実行のみ。これを満たすまでO70/O80はdisabled。
