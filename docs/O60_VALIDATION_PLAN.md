# O60 full validation metrics plan

Tracking: Issue #75  
Branch: `feat/o60-validation-metrics`  
Base: N80 merge `171f30a25ef322b09046adfee5f8eabe76e8c51b`

## Goal

Extend the accepted O60 residual authority with independent holdout diagnostics required by the placement-optimization roadmap before O70 may use automatic next-candidate recommendations.

This slice does not change the measured/predicted evidence boundary and does not introduce a scalar sound-quality score.

## Diagnostics

1. **Per-objective holdout trend**
   - Compare predicted and measured ordering for each objective independently.
   - Persist concordant/discordant/tied pair counts and pairwise agreement.
   - No aggregate cross-objective rank is created.

2. **Sensitivity**
   - For explicit nearby candidate pairs, persist placement delta and per-objective predicted/measured delta.
   - Compute slope magnitude in objective-unit/metre.
   - Thresholds are objective-specific and stored with the assessment.

3. **Repeatability**
   - Use repeated measured objective values for the same candidate/objective.
   - Persist repeat count and RMS deviation around that candidate mean.
   - Compare repeatability scale with observed between-candidate measured differences.

4. **O70 eligibility gate**
   - Requires the underlying immutable O60 validation record to have residual_gate=pass.
   - Requires at least the configured number of distinct holdout candidates.
   - Requires per-objective trend agreement to meet its threshold.
   - Requires sensitivity to remain below explicit objective-specific limits.
   - Requires repeatability data for the required holdout candidates and candidate separation to exceed the configured repeatability factor.
   - Any missing/unstable condition produces explicit stop reasons.
   - Eligibility is technical evidence status only; it does not select or rank a candidate.

## Authority

The assessment binds to:
- exact O60 validation ID + SHA;
- exact SearchSpec/candidate-set/model identity inherited from that record;
- explicit objective IDs and units;
- immutable input sample identities used to derive each diagnostic;
- algorithm/threshold version.

Persistence re-loads and revalidates the referenced O60 record. Tests use synthetic fixtures only to verify the mathematics and refusal conditions; they do not mark the REW model validated.

## Non-goals

- overall sound-quality score;
- weighted best-candidate selection;
- O70 surrogate/acquisition implementation in this slice;
- automatic speaker movement, AVR changes or REW playback;
- treating synthetic tests as owned-room validation evidence.
