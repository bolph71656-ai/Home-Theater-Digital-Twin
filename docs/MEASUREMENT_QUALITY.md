# Measurement quality authority — Issue #172

Tracking: Issue #172  
Base: main `c205e4dbb772a8a8efc95b5178655cebfa934f4a`  
Scope: immutable per-measurement quality evidence and downstream capability gates

## Authority boundary

This implementation extends the existing native N60 measurement authority. It does not replace the REW import/measurement engine, `CadMeasurementRecord`, `CadFrequencyResponseDataset`, SceneRevision persistence, O50 MeasurementPlan, or O60 validation/campaign authority.

The quality layer consumes one already-persisted native measurement/dataset and records a separate immutable report. It never infers acquisition facts from frequency/level samples. In particular:

- finite frequency+dB samples do not establish clipping, noise floor, SNR, calibration, common timing, polarity, or IR quality;
- a phase array, including `phase_status=valid`, does not establish a common timing reference;
- missing evidence is `UNKNOWN` or `NOT_EVALUATED`, never implicit `PASS`;
- `FAIL` means contrary evidence exists and remains distinct from missing evidence;
- quality is not reduced to one score.

`CadAcquisitionContextBinding` is an immutable reference (ID + content hash + source kind) to an acquisition-context authority. It is intentionally not a second AcquisitionContext implementation. When no such binding exists, the report leaves it absent and timing/calibration claims that need it remain unknown rather than fabricating microphone/AVR state.

## Immutable identity

Every `CadMeasurementQualityReport` is bound to:

- measurement ID and deterministic hash of the immutable `CadMeasurementRecord`;
- dataset ID and deterministic hash of the immutable `CadFrequencyResponseDataset`;
- exact raw-asset SHA-256 already used by N60 content-addressed storage;
- document ID, SceneRevision ID/content hash, measurement entity ID, and frozen measurement position;
- optional exact AcquisitionContext ID/hash reference;
- quality algorithm version;
- complete quality profile plus deterministic profile SHA-256;
- complete explicit evidence payload and per-check decisions.

Repository save re-reads the N60 measurement/dataset authority, verifies every binding/hash, validates repeat measurements against the same acquisition binding, reconstructs the canonical report from its inputs, and rejects a report whose stored decisions/capabilities do not match the algorithm output.

Changing a threshold/profile creates another report. Existing reports are append-only and are never rewritten.

## Quality decisions

The report has independent checks for clipping, noise/SNR, usable frequency band, timing reference, polarity, IR window/truncation, calibration provenance, and repeatability.

| Check | PASS evidence | FAIL evidence | Missing / not applicable |
| --- | --- | --- | --- |
| Clipping | explicit metadata says no clipping | explicit clipping indication | UNKNOWN |
| Noise / SNR | explicit SNR meets profile threshold | explicit SNR below threshold | UNKNOWN; FR levels never imply SNR |
| Usable band | explicit usable band satisfies profile band, or an explicit usable band exists when no profile band is required | explicit band fails required profile coverage | UNKNOWN |
| Timing reference | explicit valid reference plus reference ID, clock source, sample rate, and delay correction | explicit invalid timing reference | UNKNOWN |
| Polarity | explicit correct polarity with confidence meeting profile threshold | explicit reversed polarity | UNKNOWN when evidence/confidence is insufficient |
| IR window | IR window bounds present and explicit non-truncation | explicit truncation | NOT_EVALUATED without IR; UNKNOWN when IR metadata is incomplete |
| Calibration | applied calibration SHA equals expected SHA | hashes are both known and mismatch | UNKNOWN when provenance is absent/incomplete |
| Repeatability | >=2 explicit repeat IDs plus RMS within profile threshold | explicit RMS exceeds threshold | NOT_EVALUATED without sufficient repeat evidence |

The retake recommendation is also non-scalar: any explicit quality `FAIL` yields `RETAKE`; otherwise unresolved `UNKNOWN` yields `UNKNOWN`; fully evaluated required checks yield `NOT_NEEDED`. A `NOT_EVALUATED` check does not by itself claim failure.

## Downstream capability matrix

Capabilities use `ALLOWED | BLOCKED | UNKNOWN` and are stored per claim. `gate_measurement_claim(..., required_band_hz=...)` gives #173/#174 a fail-closed, band-aware interface: an allowed base claim becomes UNKNOWN when usable-band evidence is missing and BLOCKED when the explicit usable band does not cover the requested band.

| Claim | ALLOWED requirement | BLOCKED case | UNKNOWN case |
| --- | --- | --- | --- |
| `magnitude_response` | immutable FR magnitude dataset exists | — | required-band query with no usable-band evidence |
| `phase_response` | phase array exists and `phase_status=valid` | phase explicitly absent | phase validity unknown |
| `common_timing` | AcquisitionContext binding plus complete explicit timing-reference evidence | explicit invalid timing reference | missing context/reference metadata |
| `arrival_time` | IR exists, IR window passes, and common timing is allowed | no IR, explicit timing failure, or bad/truncated IR | partial timing/window evidence |
| `decay` | IR exists and IR window passes | no IR or explicit bad/truncated IR | incomplete IR-window evidence |
| `calibrated_response` | matching applied/expected calibration provenance and AcquisitionContext binding | explicit calibration mismatch | missing/incomplete provenance or context |
| `repeatability` | explicit repeated measurements and passing repeatability metric | explicit repeatability failure | insufficient repeatability evidence |

Magnitude inspection remains available for legacy FR-only imports. That does not open phase, arrival, decay, timing, calibration, or repeatability claims.

## Retake lineage

A retake remains a separate native Measurement with its own Dataset/raw asset. `CadMeasurementLineageRecord` is append-only and records:

- new measurement ID;
- superseded measurement ID;
- explicitly selected measurement ID;
- reason and creation time;
- deterministic lineage SHA-256.

The repository requires old/new measurements to retain the same document, SceneRevision/content hash, measurement entity/position, channel role, source-speaker IDs, and radiation scope. It never deletes or overwrites the prior Measurement, Dataset, raw asset, or quality report.

The lineage repository does not update O50 MeasurementPlan or O60 campaign/calibration/holdout assignments. Reassignment, if desired, remains an explicit operation in those existing authorities.

## Persistence

Two additive tables live in the same native SQLite database:

- `cad_measurement_quality_reports`
- `cad_measurement_lineage`

The repository passes through the existing native schema compatibility gate before DDL/read/write and uses foreign keys to the existing N60 measurement/dataset/raw-asset rows. Stored payloads deserialize back to frozen Pydantic models; identity hashes are revalidated on reopen.

No GUI, REW capture engine, CalibrationPlan (#173), joint DSP optimization (#174), or owned-room physical acceptance is introduced here.

## Regression fixtures

Focused tests cover:

- FR-only measurement;
- valid phase without common timing evidence;
- missing clipping/noise/SNR metadata;
- complete quality metadata;
- calibration-file mismatch;
- profile/threshold change creating a second report;
- retake retaining old measurement/report and explicit selected lineage;
- claim-level ALLOWED/BLOCKED/UNKNOWN outcomes;
- requested-band gating;
- persistence/reopen and hash-binding rejection.

## Verification and remaining work

Software verification for this change is the focused `test_cad_measurement_quality.py` plus repository CI. Owned-room measurement is not an acceptance prerequisite.

Remaining work is intentionally outside Issue #172:

- #173 consumes the per-claim/band capability gate when building CalibrationPlan authority;
- #174 consumes the same capability interface for joint DSP optimization;
- a future native AcquisitionContext implementation may supply the ID/hash binding directly; this quality layer must reference it rather than migrate or duplicate it;
- GUI presentation of quality evidence and retake actions is separate work.
