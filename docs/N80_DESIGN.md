# N80 design — native optimization workspace

Tracking: Issue #65  
Branch: `feat/n80-optimization-workspace`  
Base main: `286f3b86a742ef6e3454d91c609ce1f84d840c57`

## 1. 目的

N80は、N50のhard constraint、N60のmeasurement authority、N70のprediction authorityを、探索候補とobjective/Pareto比較へつなぐnative CAD workspaceとする。

最重要原則は**native SceneRevisionを正本に保つこと**。既存O10実装は算法serviceとして再利用するが、legacy Context / Store / browser Search UIをnative authorityへ昇格しない。

## 2. 実装slice

### N80a — native SearchSpec + candidate workspace

最初にO10の既存 deterministic search-space engineをnative Sceneへ接続する。

- immutable native SearchSpecを保存する。
- SearchSpecはexact `document_id` / `scene_revision_id` / `scene_content_hash` / native constraint workspace hashへbindingする。
- native SceneDocumentを`scene_to_g10_context()`でtransient G10/O10 payloadへprojectionする。
- native `CadConstraintSet`からG10 stored specを構成し、既存`validate_search_spec()` / `generate_search_space()`を呼ぶ。
- candidatesそのものを大量永続化せず、immutable SearchSpecから決定論的に再生成する。
- raw / feasible / rejected / duplicate countと`candidate_set_sha256`を保持する。
- candidate cloudはN70のbulk marker primitiveを再利用する。
- candidate previewはview stateであり、SceneRevisionを変更しない。
- explicit applyだけが`TransformEntitiesCommand`相当の1 commandでWorkingDocumentへ反映し、1 Undoで完全復元する。
- source SceneRevisionまたはconstraint hashが変わったSearchSpecはstale。current sceneへ再生成・applyしない。

N80aではnative constraint modelに存在しないlegacy `linked_placement`を偽装しない。linked derivationはnative constraint contractを追加する独立sliceで扱う。

### N80b — batch prediction / objective vector

O20/O30の該当gateが成立したmodelだけ接続する。

- candidate batch predictionはmodel applicability、model version、source SceneRevision、SearchSpec identityを固定する。
- objectiveは独立vectorとして保存する。
- flatness、peak/dip、左右差、席間差、移動量等を単一スコアへ暗黙縮約しない。
- predicted / measured / derived evidenceを区別する。

### N80c — Pareto / measurement loop

O40以降を接続する。

- Pareto非劣集合を基本表示とする。
- weighted preferenceを追加する場合も元objective vectorとweight/versionを残す。
- candidate → explicit apply → SceneRevision → Measurementを履歴として追跡する。
- O60の独立model validation前に自動推薦へ昇格しない。

## 3. Native SearchSpec authority

初期schemaは最低限次をimmutable保存する。

- `search_spec_id`
- `document_id`
- `scene_revision_id`
- `scene_content_hash`
- `constraint_workspace_hash`
- algorithm `deterministic_grid`
- algorithm version `search-space-grid-1`
- grid axes: entity ID / X,Y,Z / min / max / step
- candidate limit
- canonical SearchSpec JSON + SHA-256
- creation time

SearchSpec更新はしない。編集は複製→新規保存。

Constraint workspace hashはcanonical native `CadConstraintSet.model_dump(mode='json')`から計算する。保存時と生成時に再計算し、一致しなければstaleとして拒否する。

## 4. O10 adapter boundary

既存`search_space.py`はlegacy Context-shaped dictを受けるが、これは算法input contractとしてのみ使用する。

native adapterの手順:

1. exact source SceneRevisionをrepositoryから読む。
2. source content hashがSearchSpec bindingと一致することを確認する。
3. native `CadConstraintSet`のdocument ID/hashを確認する。
4. `scene_to_g10_context()`でtransient context payloadを作る。
5. `build_g10_constraint_request()` + legacy G10 validatorでconstraint stored specを作る。
6. `SearchSpecCreate`を既存O10へ渡し、canonical stored specを得る。
7. 生成時も同じsource revision / constraint hashで`generate_search_space()`を呼ぶ。

legacy project/context/search_spec DBにはnative SearchSpecを書かない。

## 5. Candidate semantics

Candidateは**feasible geometry candidate**であり、音響品質順位ではない。

各candidate:

- deterministic candidate ID
- raw/feasible index
- touched entityのexact XYZ override
- source SearchSpec SHA
- source candidate-set SHA

Candidate preview:

- current sceneをcommitしない。
- non-pickable ghost/analysis representationを使う。
- candidate cloudは候補数に比例してactorを増やさない。

Candidate apply:

- source revision/hash/constraint hashがcurrent authorityと一致する場合のみ可能。
- touched entitiesを一括して1 commandで置換する。
- 1 Undoで全entity位置をbeforeへ戻す。
- applyだけではSceneRevision保存しない。既存Save actionで明示保存する。

## 6. UI

N70 `PredictionWorkspaceWindow`を継承して日本語`最適化` dockを追加する。

N80a UI:

- source revision / constraint workspace状態
- movable entity + axis
- min / max / step
- candidate limit
- raw count preview
- immutable SearchSpec保存/履歴
- generate
- raw / feasible / rejected / duplicate
- candidate cloud
- candidate list/detail
- preview / clear preview / apply

表示語は「候補」「実行可能」であり、「推奨」「最適」「1位」を使わない。

## 7. Async / stale boundary

候補生成がGUI threadをblockingしない規模へ拡張する場合はN70のjob guard型を継承する。少なくともapply前にはcurrent document/revision/hash/constraint hashを再検証する。

document switch、revision change、constraint change後の古いcandidate setをcurrent sceneへapplyしない。

## 8. Test / acceptance

意味のあるfocused testだけ追加する。

N80a automated invariants:

- native SearchSpec save/load round-tripとsource revision/hash binding
- constraint hash mismatchを拒否
- 同一native sourceでO10 candidate IDs/order/set hashが再現
- candidatesがhard-constraint rejectを含めない
- previewがWorkingDocument history/dirty状態を変更しない
- applyが1 commandだけhistoryを増やし、1 Undoで全位置を復元
- stale source revision/constraint workspaceからapply不可
- candidate cloudがbulk actorを再利用

Owned-Windows A14:

- candidate選択→preview→explicit apply→Undoをreal interactionで確認する。
- stale/cancel/document boundaryはA13を継承する。

## 9. 非目標

N80aでは次を実装しない。

- fake objective/Pareto UI
- unvalidated acoustic prediction
- single quality score
- automatic recommendation
- browser UI parity
- legacy Context authority

O30/O40の実装が存在しない現状では、ParetoはN80b/cの明示的な後続sliceとする。