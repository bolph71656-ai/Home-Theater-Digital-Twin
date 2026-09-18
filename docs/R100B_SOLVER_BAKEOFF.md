# R100B Solver Bakeoff Authority and Execution Plan

> Tracking: Issue #101
> Depends on: R100A merged by PR #110 (`1714c078d4063f59da93f0d733171547f7eb486d`)
> Current state: bakeoff infrastructure / candidate-source authority implemented; numerical candidate runs are still pending.

## Purpose

R100B consumes the exact R100A benchmark manifest and produces evidence for solver selection. It must not let each solver redefine the room, openings, materials, source normalization, receiver timing, comparison convention or resource budget.

A candidate appearing in `r100b_candidates.json` means only that it is authorized for a bounded probe. It does **not** mean that its declared probe capabilities have passed, that its Windows packaging works in HTDT, or that it is selected for production.

## Version-pinned initial candidates

| Candidate | R100B role | Pinned source | License | Windows state before HTDT probe |
|---|---|---|---|---|
| PFFDTD | FDTD primary evaluation | `main@aa319f6c86517cb95aabfae8656277da62c3ead5` | MIT | upstream README targets Linux; native/portable Windows path must be proved or rejected |
| MFEM | independent FEM reference / production alternative | `v4.10@d964264cdb9a13e94a201b6c236c7721e0c8765f` | BSD-3-Clause | upstream CMake/Visual Studio path exists; HTDT acoustic/package probe still required |
| pyroomacoustics | geometric reference | `v0.10.1@f02b01dd6609709e2089aefa5d1e59c91d3a0601` | MIT | modern pyproject/CMake/cibuildwheel release; exact HTDT Python 3.12 Windows probe pending |

Upstream evidence is recorded in `benchmarks/acoustics/r100b_candidates.json`. Transitive dependencies are not approved merely because the top-level project has a permissive license.

## Bakeoff authority

`backend/src/htdt/acoustic_bakeoff.py` defines immutable, canonical records for:

- candidate identity, pinned upstream commit and source/license evidence;
- evaluation role and shipping-vs-reference scope;
- Windows/CPU/GPU probe state;
- required compiled representation;
- **probe capabilities**, explicitly distinct from verified capabilities;
- platform/thread/device authority;
- fixture evidence and per-observable status/error summaries;
- compile/solve/postprocess time, RAM and output size;
- hard-gate evidence;
- final decision state.

Every run binds to both:

1. R100A manifest semantic SHA-256;
2. R100B candidate-manifest semantic SHA-256.

A run against a changed physical fixture or changed candidate pin is therefore stale by construction.

## Fail-closed selection

The validator rejects:

- the wrong R100A manifest/hash;
- a changed candidate manifest or source commit;
- unknown fixture evidence;
- execution of a fixture whose required capability is outside the candidate's authorized probe capability set;
- duplicate fixture/gate evidence;
- a passing fixture without all required observable records;
- a PASS observable whose reported error exceeds the R100A quantity-specific tolerance;
- a PASS fixture with missing or over-budget compile/solve/postprocess/RAM/output/thread evidence;
- missing required hard-gate evidence;
- `not_applicable` for a hard gate that applies to the candidate;
- selecting a reference-only candidate for the production stack;
- selecting a shipping candidate while any applicable hard gate or applicable fixture is not PASS.

Performance never rescues a failed correctness gate.

## Current coverage

The initial candidate capability envelope intentionally leaves two R100A fixtures without an authorized candidate:

- `wave-portal-split-room-v1`;
- `hybrid-overlap-continuity-v1`.

That is expected at this stage. Portal semantics must not be claimed until an adapter implements them. Hybrid overlap belongs after compatible wave/geometric evidence exists. The preflight command reports these gaps rather than silently assigning them to an unsuitable backend.

## Repeatable command

Windows CI executes:

~~~powershell
python -m htdt.acoustic_bakeoff preflight `
  --manifest benchmarks\acoustics\r100a_manifest.json `
  --candidates benchmarks\acoustics\r100b_candidates.json
~~~

A recorded candidate run is validated with:

~~~powershell
python -m htdt.acoustic_bakeoff validate-run `
  --manifest benchmarks\acoustics\r100a_manifest.json `
  --candidates benchmarks\acoustics\r100b_candidates.json `
  --run <run-evidence.json>
~~~

The preflight is authority validation only. It is not a numerical benchmark result.

## Next R100B implementation slices

The numerical bakeoff proceeds in this order:

1. implement the common adapter/result protocol and a deterministic analytical reference reader for R100A observables;
2. probe PFFDTD reuse/port feasibility on GitHub-hosted Windows without RDC; if native Windows integration is not practical, record that gate failure instead of reimplementing it silently;
3. implement the minimal MFEM acoustic reference prototype for rigid rectangular/concave fixtures and then the explicit impedance fixture;
4. probe pyroomacoustics v0.10.1 for direct/first-reflection and stochastic-seed fixtures;
5. record exact compile/solve/postprocess/RAM/output evidence under the R100A resource budgets;
6. publish the R100B ADR only after applicable hard gates have real evidence.

If no shipping candidate clears the gates, R100B exits with a no-go ADR and a bounded next experiment. It must not force a winner.

## Non-claims

This slice does not:

- select PFFDTD, MFEM or pyroomacoustics for production;
- claim numerical accuracy for any candidate;
- claim Windows packaging for PFFDTD;
- claim that an upstream capability maps exactly to HTDT Portal/BoundaryTermination/object semantics;
- validate the owned room;
- authorize R110+ production integration yet.

RDC is not used for R100B. GitHub Actions is the execution authority for work that can be tested in the cloud.
