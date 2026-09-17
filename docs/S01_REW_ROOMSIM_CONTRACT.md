# S01 / O20 design — REW Room Simulator model contract

Tracking: Issue #67  
Parent: Issue #65  
Branch: `feat/s01-rew-roomsim-o20`  
Base main: `0e29c24e7176174e26714b8975da15dd63701022`

## 1. Purpose

Promote the existing read-only REW Room Simulator adapter into a verified, reversible prediction-model transaction for N80b/O20.

This is a **rectangular-room low-frequency baseline predictor only**. It is not an exact polygon-room solver and does not model source directivity.

## 2. Existing authority boundary

- Native `SceneRevision`, native SearchSpec and native candidate identity remain HTDT authority.
- REW Room Simulator is an external prediction engine, not storage authority.
- Existing measurement records and REW measurement list are outside this transaction.
- Room Simulator outputs are `predicted` evidence and never become `measured` evidence.
- Legacy Context remains transient adapter data only.

## 3. Supported REW contract

Initial model ID: `rew-room-simulator-rectangular-v1`.

The implementation is limited to localhost REW API and a pinned observed API/OpenAPI contract.

Allowed Room Simulator endpoints are explicitly enumerated:

- `/version`
- `/roomsim/room-size`
- `/roomsim/room-is-sealed`
- `/roomsim/absorptions`
- `/roomsim/options`
- `/roomsim/head-position`
- `/roomsim/mic-posn-offsets`
- `/roomsim/sources`
- `/roomsim/source-names`
- `/roomsim/mic-positions`
- `/roomsim/:src/position`
- `/roomsim/:src/configuration`
- `/roomsim/frequency-response`
- `/roomsim/:src/frequency-response`

No measurement-create, measurement-delete, sweep, import or application-state endpoint is part of the model transaction.

## 4. Geometry and coordinates

HTDT coordinate authority remains:

- origin = front-left-floor
- X = right
- Y = rear
- Z = up

REW Room Simulator positions are mapped:

- `fromLeft = x`
- `fromRear = room_depth - y`
- `fromFloor = z`

Geometry support:

- exact rectangular prism only;
- non-rectangular source scenes are rejected for this model;
- a future rectangular approximation must be explicit, separately identified and persist its approximation rule/input;
- no silent bounding-box substitution.

## 5. Reversible state transaction

Every writable prediction operation follows this sequence:

1. Read and validate the complete supported Room Simulator snapshot.
2. Canonicalize/hash the snapshot and record REW version/API contract identity.
3. Apply only the fields required for the prediction request.
4. Read back the mutated supported state and verify the requested values.
5. Read predicted frequency response(s).
6. In `finally`, restore the original snapshot using the same explicit endpoint allowlist.
7. Re-read and canonicalize the supported state.
8. Treat the operation as failed unless the restored state equals the original canonical snapshot.

Cancellation and exceptions do not bypass restore.

Restore failure is higher priority than returning a prediction result; the caller receives an explicit restore error and the output is not accepted as a completed PredictionRun.

## 6. Write semantics

REW documents that model values can be set with POST or PUT and that multi-field models accept partial models. HTDT uses PUT for idempotent model replacement/update semantics.

The generic HTTP helper:

- restricts host to localhost through existing URL validation;
- JSON encodes request bodies;
- accepts JSON responses or an empty successful response;
- converts HTTP/network failures to existing REW API error types;
- never follows a caller-supplied arbitrary URL.

Per-endpoint writer methods validate payload shape before sending.

## 7. S01 OpenAPI probe

Owned-Windows probe must retrieve `/version` and `/doc.json` from the installed REW instance and record:

- REW version string;
- OpenAPI info/version;
- canonical SHA-256 of the Room Simulator subset of `paths` plus referenced schemas;
- HTTP methods available on supported Room Simulator endpoints;
- request-body schema references;
- response schema references.

The probe stores no local artifacts in the repo. A compact evidence document is committed from its output.

A writable acceptance phase then performs one reversible transaction:

- snapshot;
- change one or more Room Simulator values to explicitly chosen temporary values or a semantically equivalent no-op where the API still exercises PUT;
- read a frequency response;
- restore;
- verify exact supported-state equality.

## 8. O20 batch identity

Each future batch run must bind:

- source document ID / SceneRevision ID / scene content hash;
- SearchSpec ID / SHA;
- candidate ID / candidate-set SHA;
- model ID/version;
- REW version and OpenAPI contract hash;
- Room Simulator input snapshot;
- mic position;
- requested frequency-response scope;
- algorithm/batch version.

Candidate outputs are immutable. Retry/resume creates or completes candidate-run records without rewriting older accepted outputs.

## 9. Async / cancellation

Room Simulator I/O stays off the GUI thread.

A batch job must:

- capture exact inputs at submission;
- expose cancellation;
- stop submitting new candidates after cancellation;
- finish the active reversible REW transaction and restore state;
- never apply stale output to a changed document/SearchSpec;
- preserve individual candidate failure reasons.

## 10. Focused verification

Automated tests are required because state restoration is a high-impact invariant:

- GET snapshot round-trip canonicalization;
- PUT method/path/body contract;
- snapshot → mutate → response → restore;
- restore after prediction error;
- restore after cancellation signal;
- restore mismatch rejects output;
- unknown/unsupported endpoint is inaccessible through writer API;
- coordinate round-trip;
- non-rectangular model rejection;
- input/provenance hashing stability;
- batch partial failure/resume semantics when O20 layer is added.

## 11. Scope boundary

This slice does not adopt pyroomacoustics and does not claim non-rectangular exact prediction.

O30 objective vectors and O40 Pareto search can be implemented independently after their own pure-domain contracts, but no UI should present Pareto results until those algorithms exist and have deterministic synthetic fixtures.
