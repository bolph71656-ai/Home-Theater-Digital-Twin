# R100B pyroomacoustics stochastic seed / convergence gate

Issue #153 extends the merged pyroomacoustics direct/first-reflection reference with stochastic evidence. It does not select a production solver and does not finalize the R100B ADR.

## Frozen authorities

- R100A-2 fixture: `geometric-seed-repeatability-v1`.
- Candidate: `pyroomacoustics-v0.10.1-f02b01d`.
- Upstream source: tag `v0.10.1`, commit `f02b01dd6609709e2089aefa5d1e59c91d3a0601`.
- R100B stochastic controls: `benchmarks/acoustics/r100b_pyroom_stochastic_authority.json`.
- Exact R100A manifest hash, exact fixture hash, candidate manifest hash and stochastic-authority hash are embedded in every raw-evidence envelope. A stale hash is rejected rather than promoted to current evidence.

The R100A-2 fixture itself is unchanged. Its source, receiver, room, material bands, sound speed/density, frequency grid, timing convention, normalization, random seed, resource budget and observable tolerance remain the authority.

## Pre-registered stochastic controls

The same-seed replay uses the R100A seed `20260918` twice at the finest refinement level. Both the selected raw histogram SHA-256 and the extracted decay curve must be exactly identical. This is **repeatability only**, not statistical convergence.

Independent-seed evidence uses `20260919`, `20260920`, `20260921`, and `20260922` at every refinement level:

| Level | Rays | Receiver radius | Histogram bin |
|---|---:|---:|---:|
| coarse | 8,192 | 0.60 m | 8 ms |
| medium | 32,768 | 0.45 m | 4 ms |
| fine | 131,072 | 0.30 m | 2 ms |

The estimator is normalized Schroeder cumulative ray-energy decay. The common observable grid is 500/1000/2000 Hz at 40, 80, 120, 160, 200, 240, 280 and 320 ms. All times align exactly to every histogram-bin level. Air absorption is disabled because the frozen geometric fixture does not authorize an additional atmospheric-loss model; room sound speed is explicitly overridden to the R100A value.

A required sample with no positive cumulative ray energy is `insufficient_support`. It is retained as non-converged evidence and is never converted to a zero response.

## Convergence criterion

For each refinement level, the four independent-seed decay curves are retained individually. The evaluator then computes the per-sample independent-seed mean and sample standard deviation (`ddof=1`).

Statistical convergence requires all of the following, fixed before the numerical run:

1. coarse→medium and medium→fine RMS changes of the independent-seed mean curve decrease strictly;
2. the final medium→fine absolute RMS change satisfies the frozen R100A absolute tolerance;
3. the final relative RMS change satisfies the frozen R100A relative tolerance;
4. the maximum pointwise seed-to-seed standard deviation at the fine level satisfies the frozen R100A statistical standard-deviation tolerance.

The central R100B observable reports the maximum of replay and convergence error metrics, and the existing central R100B validator applies the R100A tolerance without relaxation. Same-seed identity cannot make a non-converged budget sequence pass.

## Raw and resource evidence

The dedicated workflow stores:

- complete JSON authority/provenance and evaluator result;
- selected-band raw ray histograms in a compressed NPZ archive;
- per-observation seed, ray budget, receiver radius, histogram bin, histogram digest and support state;
- per-observation setup, solve, postprocess and peak-RSS measurements;
- aggregate setup/solve/postprocess/RAM/output evidence passed into `BakeoffFixtureEvidence`;
- official wheel filename/SHA-256 and exact Python package versions;
- candidate source ref/commit;
- standard `BakeoffRun` output validated by the central R100B evaluator.

The workflow outcome and candidate outcome are printed separately. A workflow PASS therefore does not imply stochastic candidate PASS.

## Numerical result

Pending the dedicated GitHub Actions run for this PR. The result will be recorded here without changing the pre-registered criterion or frozen R100A tolerance.
