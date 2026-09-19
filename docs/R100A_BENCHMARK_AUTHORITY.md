# R100A Acoustic Benchmark Authority

> Issue #101 / R-series first implementation slice  
> Schema: `r100a-3`  
> Canonical machine-readable manifest: `benchmarks/acoustics/r100a_manifest.json`

## Revision 2 pressure authority correction

R100B pressure-field work exposed an omission in revision 1: the research contract required both density and sound speed to be fixed, but `BenchmarkEnvironment` did not carry density. Revision 2 makes `density_kg_m3` mandatory and fixes the canonical fixture density at 1.2 kg/m3. This is required for adapters whose native state is not pressure; for example, PFFDTD evolves acoustic velocity potential and HTDT converts it using `P/Q = -i*omega*rho*Phi/Q` under the manifest Fourier convention.

The complex-pressure convergence observable continues to use the original 0.02 Pa absolute and 2% relative tolerances. Its redundant `phase_deg: 0` field was removed because phase is already contained in the complex RMS error; keeping a second exact-zero-degree requirement would contradict an unsampled numerical convergence test.

Revision 2 changes the manifest semantic SHA-256 intentionally. Revision-1 R100B artifacts remain historical records, but they cannot satisfy current solver-selection gates until replayed against revision 2.

## Revision 3 radiation termination authority

Revision 2 still left `BoundaryTermination(kind='radiation')` mathematically ambiguous. Revision 3 fixes that gap rather than allowing each solver adapter to assign its own meaning to the word `radiation`.

For `wave-explicit-radiation-termination-v1`, R100A-3 now freezes:

- outward normal from the modeled `AcousticRegion`;
- local first-order outgoing model `p/u_n = rho*c`;
- `k = omega/c` using the fixture's frozen environment;
- under `exp(-i*omega*t)`, the equivalent Robin form `dp/dn - i*k*p = 0`;
- explicit binding to boundary `b-interface` on the x=6 m aperture;
- dedicated `wave_radiation_termination` capability, distinct from rigid or impedance support.

This is intentionally a local first-order/Sommerfeld-type approximation. It is not described as an exact exterior-domain radiation solution for arbitrary incidence.

The same revision embeds 281 semi-analytical 20–300 Hz reference samples. A repository checker reconstructs them from normalized Neumann transverse modes plus the exact one-dimensional Green function for the frozen Robin boundary. The N=8 -> N=12 modal refinement must remain below `1e-9` complex RMS relative and `1e-8` maximum point-relative error before the N=12 samples are accepted as authority.

Revision 3 intentionally changes the manifest semantic SHA-256. Earlier R100B artifacts remain historical evidence and must replay under the new hash before they can participate in a current selection decision.

## Purpose

R100A freezes the **solver-neutral comparison authority** before any FDTD, FEM, BEM or geometric-acoustics candidate becomes a product dependency.

The manifest is not a solver implementation and does not claim owned-room validation. It defines the physical and numerical problem that R100B adapters must consume without silently changing geometry, openings, materials, source normalization, receiver timing, environment, comparison rules or resource budgets.

The implementation is intentionally backend-independent:

- `AcousticRegion` owns modeled air volumes.
- `AcousticPortal` explicitly connects two modeled regions with pressure/velocity continuity semantics.
- `BoundaryTermination` explicitly terminates an opening when the adjacent volume is not modeled; radiation termination carries an exact model/sign/normal/impedance authority rather than a label alone.
- `AcousticObstacle` represents participating solid/thin objects separately from editor visibility.
- wave material capability and geometric material capability are independent.
- phase-bearing wave impedance is explicit complex authority; it is never synthesized from scalar absorption.
- source excitation/normalization, receiver calibration/timing and environment, including explicit air density, are part of each fixture.
- coordinate system, Fourier sign, time zero, precision, interpolation, frequency/time sampling, window and filter are fixed in the numerical comparison contract.
- expected observables carry quantity-specific tolerances.
- correctness hard gates are separate from compile/solve/postprocess/resource budgets.

## Canonical fixtures

The first manifest revision contains ten common fixtures.

| Fixture | Role | Gate |
|---|---|---|
| `wave-rigid-rectangular-modes-v1` | wave | analytical rigid rectangular eigenmodes |
| `wave-rectangular-convergence-v1` | wave | grid/mesh refinement and transfer convergence |
| `wave-normal-incidence-impedance-v1` | wave | closed-form complex reflection from explicit impedance |
| `wave-concave-l-room-v1` | wave | exact concave polygon-prism comparison; no rectangularization |
| `wave-portal-split-room-v1` | wave | region split / Portal continuity invariance |
| `wave-explicit-radiation-termination-v1` | wave | explicit opening termination; no invented adjacent space |
| `geometric-direct-first-reflection-v1` | geometric | direct delay and first specular reflection geometry |
| `geometric-reflecting-counter-v1` | geometric | participating reflecting obstacle changes path authority |
| `geometric-seed-repeatability-v1` | geometric | stochastic seed/repeatability contract |
| `hybrid-overlap-continuity-v1` | hybrid | compatible overlap continuity without invented phase/data |

R150 will still need ray-count, receiver-estimator/radius, time-bin and termination convergence beyond same-seed repeatability. Likewise, FR acceptance does not make frequency-domain IR synthesis or decay metrics accepted automatically.

## Hard gates

R100B candidates are evaluated only after the applicable hard gates are satisfied:

1. physics correctness against the fixture's declared reference/tolerance;
2. CPU correctness baseline without GPU dependency;
3. reproducible Windows 11 x64 packaging/embedding;
4. license/redistribution compatibility;
5. required physics/output capability;
6. reproducible authority including backend/version/precision/grid/seed/approximation controls.

Speed and memory are comparison criteria **after** hard correctness/capability gates. A fast solver that fails a physics or authority gate is not promoted.

## Resource contract

Each fixture records an initial bounded R100B workload:

- CPU thread budget;
- RAM and disk budget;
- candidate count;
- maximum compile time;
- maximum solve time;
- maximum postprocess time;
- maximum produced output size.

These values are benchmark decision limits, not numerical accuracy tolerances. R100B records measured values and may propose a versioned manifest revision if evidence shows a budget itself is inappropriate; adapters must not silently weaken the current manifest.

## Identity

`AcousticBenchmarkManifest.canonical_json()` uses sorted, non-NaN canonical JSON. `semantic_hash()` is SHA-256 over that exact canonical representation.

R100B evidence must bind to the manifest semantic hash plus candidate/reference backend identity. Editing geometry, material data, source/receiver/environment, tolerance, seed or resource budget therefore changes authority identity.

## Fail-closed behavior

The Pydantic authority models reject, among other cases:

- dangling region/face/material/boundary/source/receiver references;
- a Portal connecting a region to itself;
- impedance termination without an impedance boundary;
- radiation termination without explicit boundary/model/sign/normal/characteristic-impedance authority;
- `wave_impedance` fixture capability without explicit phase-bearing impedance data;
- geometric scattering capability without explicit non-zero scattering bands;
- stochastic ray capability without a fixed seed;
- analytical/closed-form observable without expected samples;
- peer-comparison observable referencing an unknown fixture;
- malformed frequency/time/tolerance authority.

Unsupported physics stays unsupported. No default material, anechoic exterior, rectangular room, coherent phase or zero response is invented to make a candidate pass.

## Next implementation gate

R100B consumes this manifest through candidate/reference adapters and records:

- backend/package/version and license evidence;
- required compiled representation;
- Windows packaging result;
- CPU numerical evidence per applicable fixture;
- compile/solve/postprocess time and peak/resource evidence;
- supported and unsupported result capabilities;
- adoption decision or no-go/next-limited-experiment ADR.

FDTD-first remains evaluation order, not a preselected production solver. Existing OSS reuse/adapter/port is preferred over a new kernel unless benchmark evidence establishes a concrete gap.

## Verification boundary

R100A verification is repository/CI based and requires no Remote Desktop Commander. It validates the authority schema, canonical manifest, cross-references and fail-closed semantics. Numerical solver accuracy starts in R100B/R130; owned-room evidence remains gated by R180/O60 and is not created by these fixtures.
