# O60E Owned-Room Validation Campaign

Tracking: Issue #81

## Problem

O60 software validation already separates calibration and holdout inside a
ValidationRecord, but the split can currently be supplied when the record is
built. For real owned-room evidence that permits choosing holdout candidates
after observing measurements.

O60E preregisters the study before candidate measurements are completed. O70
must not consume an owned-room validation that is not tied to such a persisted
campaign.

## Immutable campaign authority

A campaign freezes:

- document, SearchSpec id/SHA and candidate-set SHA;
- model id/version;
- requested validation band and holdout residual threshold;
- candidate ids and calibration/holdout split;
- canonical objective-evaluation spec/SHA and objective ids;
- trend tolerances/minimum comparable pairs/minimum agreement ratio;
- sensitivity candidate pairs and thresholds;
- candidates requiring repeated measurements and minimum repeat count;
- candidate-separation pairs and repeatability reference candidate;
- required applicability check codes;
- creation timestamp and campaign identity SHA.

The repository regenerates the exact SearchSpec candidate set before saving and
rejects unknown candidate ids or a changed candidate-set SHA.

For every candidate in the campaign, a measured Measurement Plan must not
already exist at campaign-save time. Planned-but-not-measured plans are allowed
because they can be prepared before physical measurement. This prevents
post-measurement split selection.

## Readiness

Readiness is derived from immutable repositories and never creates or
reclassifies evidence. For each campaign candidate it reports:

- one exact completed Room Simulator prediction attempt for the campaign model;
- one completed Measurement Plan and its measured N60 evidence;
- predicted/measured objective evaluations whose evaluation-spec SHA exactly
  equals the preregistered campaign spec;
- repeatability count for candidates that require repeated measurements.

Missing or ambiguous evidence is listed explicitly. No default ranking or
automatic physical action is performed.

## Validation build

Owned-room full validation is built from the persisted campaign. Candidate split
and thresholds come from the campaign, not from a caller-supplied BuildSpec.

Evidence selection is deterministic and fail-closed:

- the response measurement for a candidate is the earliest captured measured
  evidence in its completed Measurement Plan;
- prediction requires exactly one matching completed attempt, otherwise
  readiness is ambiguous;
- objective evidence requires exactly one matching predicted and one matching
  measured evaluation for each objective and campaign evaluation-spec SHA;
- repeatability uses all measured evidence in the campaign candidate plan;
- required applicability codes must be supplied exactly once when the record is
  built.

A resulting owned-room ValidationRecord stores the campaign id and the
validation repository verifies that campaign binding before persistence.

## O70 boundary

The O70 entry API may return only a persisted `eligible` ValidationRecord whose
owned-room campaign exists and matches the record. Synthetic fixtures and legacy
owned-room records without a campaign never open the automatic-recommendation
gate.

## Non-goals

- no autonomous speaker movement;
- no autonomous REW playback;
- no synthetic promotion to owned-room evidence;
- no adaptive planner implementation before a genuine campaign passes O60.
