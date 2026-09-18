# O60 progress

Tracking: Issue #75 / PR #76  
Branch: `feat/o60-model-validation`  
Base: main after N80c/O50 merge `171f30a25ef322b09046adfee5f8eabe76e8c51b`

## Implemented on branch

- O60 algorithm version advanced to `model-validation-2`.
- Existing residual holdout gate remains independent and cannot alone enable recommendation.
- Calibration and holdout candidate sets are explicitly disjoint; full eligibility requires both.
- Per-objective holdout pairwise-ordering checks preserve independent objectives and do not create a composite ranking.
- Explicit tie tolerance, minimum comparable pairs and minimum agreement ratio are saved.
- Placement sensitivity stores observed objective change per metre and prediction-vs-measured sensitivity error per metre, with per-objective thresholds.
- Same-SceneRevision repeated measurements produce an immutable pairwise RMS repeatability floor.
- Candidate measured-response separation is compared against the repeatability floor and a saved minimum multiple.
- Applicability checks are explicit immutable stop reasons.
- `synthetic_fixture` evidence can never enable recommendation.
- `owned_room` persistence additionally requires referenced measurement provenance to contain `validation_scope=owned_room`.
- Repository save revalidates prediction attempts, Measurement Plans, objective evaluations, regenerated candidate-set identity/placement distance, repeatability responses and candidate separation.
- `CadModelValidationService` builds a record from O20/O30/O50/N60 repositories instead of accepting hand-entered metric snapshots as product authority.
- Native optimization panel shows residual, trend, sensitivity, repeatability, applicability, candidate separation and stop reasons separately.

## Focused tests added

- trend concordance/discordance and tie/insufficient behavior;
- sensitivity threshold behavior;
- repeatability floor and candidate-separation gate;
- full gate composition including synthetic-vs-owned scope;
- full repository cross-evidence recomputation and owned-room provenance rejection;
- repository-backed build service.

## Validation status

- Earlier O60 core head `260e7fc67b09c4ebb3d70bf74d505648479e4f93`: CI #411 PASS.
- Later full-gate / GUI / service changes are still awaiting their latest GitHub Actions run. Do not treat PR #76 as accepted until the current head passes.
- RDC usage for O60: 0. Synthetic/algorithm verification does not justify an owned-Windows hardware session.
- O70 remains disabled. No adaptive recommendation is implemented or enabled from synthetic evidence.

## Remaining before PR completion

1. Resolve latest CI failures, if any.
2. Add only fixes/tests justified by those failures.
3. Review native validation panel against the Issue #75 display requirements.
4. Update canonical implementation status after green CI.
5. Use owned-room data only if genuine repeated/calibration/holdout measurements already exist; do not manufacture an O60 acceptance by synthetic fixtures.
