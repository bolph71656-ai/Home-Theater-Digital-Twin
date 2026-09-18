# Arbitrary-room acoustics research and implementation decision — 2026-09-18

Tracking: Issue #101  
Status: planning/research only. The scope of R100A and R100B is defined; the executable fixture contract, tolerance manifest and benchmark evidence are not yet delivered. Production backend, crossover and shipping dependencies remain benchmark-gated.

## 1. Decision summary

HTDT should not extend the current rectangular predictor into a silently approximate general-room model. The arbitrary-room path will be a **hybrid, multi-fidelity acoustic engine** with separate authorities for wave acoustics and geometrical acoustics.

The implementation baseline is:

1. **20–300 Hz wave domain**: a structured-grid time-domain solver is the first production PoC, with a deterministic CPU implementation as the correctness baseline and optional GPU backends behind the same solver contract.
2. **Mid/high frequency domain**: geometrical acoustics with deterministic direct/specular paths first, then stochastic/diffuse ray energy where justified.
3. **Hybrid result**: combine low-band coherent wave results and upper-band geometric results only inside an explicit overlap/crossover contract. Do not fabricate coherent phase for a stochastic late-field result that does not contain it.
4. **Material authority**: separate energy-domain absorption/scattering from wave-domain complex impedance/admittance. Do not derive a unique phase-bearing impedance from a scalar absorption coefficient without an explicit model.
5. **Source/receiver authority**: keep physical cabinet orientation, acoustic aim, source excitation/level reference and frequency-dependent directivity separate. Receiver position/orientation/calibration/timing authority is equally explicit and binds to the prediction.
6. **Execution**: CPU fallback is mandatory. GPU is an accelerator, not a correctness dependency. Candidate-level parallelism, solver-internal threading and GPU execution must be scheduled together to avoid oversubscription.
7. **Validation**: analytical/reference numerical cases precede owned-room REW/UMIK-1 validation. Simulation alone never opens the production recommendation gate.

This preserves the existing HTDT evidence model: measured, predicted, derived and hypothesis remain distinct, and production recommendation still requires O60 owned-room evidence.

## 2. Why this architecture

### 2.1 Full-wave over the whole audible band is not a practical default

Mesh/grid resolution scales with the shortest wavelength. A single 20 Hz–20 kHz full-wave model would force the whole room to use high-frequency spatial resolution and becomes wasteful in both memory and compute. The engineering response is a banded/hybrid model rather than pretending one discretization is efficient everywhere.

20–300 Hz is a feasibility target, not a demonstrated consumer-PC performance guarantee. R100B must measure representative room/adjacent-region size, boundary state, simulation duration and requested output on a declared CPU/RAM budget before promising interactive or batch performance.

### 2.2 FDTD first, but not as an irreversible commitment

A structured-grid time-domain solver is the first PoC because it has:

- simple deterministic geometry compilation to a voxel/grid representation;
- excellent data parallelism;
- natural broadband impulse-response output from one time-domain run;
- good suitability for consumer GPUs;
- straightforward reuse of a fixed room/material grid for many receiver probes.

Its main risks are staircase error, thin-surface representation and correct frequency-dependent impedance boundaries. Those risks are explicit benchmark gates.

A frequency-domain FEM implementation remains the main independent reference/alternative because it handles irregular boundaries and impedance conditions naturally. HTDT will benchmark FEM rather than assuming FDTD wins every case.

### 2.3 BEM/FMM is a secondary candidate

Boundary-element methods avoid volume meshing and are valuable for radiation/open-boundary problems. For enclosed room optimization they add dense-operator/interior-resonance complexity and are not the first shipping path. They remain useful as an independent reference for selected fixtures if packaging and performance prove acceptable.

## 3. Candidate software / OSS

The table classifies projects by the role they can realistically play in HTDT. “Reference” does not mean “ship as a dependency”.

| Project | Relevant capability | HTDT classification | Main concern |
|---|---|---|---|
| MFEM | C++ FEM, OpenMP/CUDA/HIP/OCCA/RAJA backends, BSD-3-Clause | **High-value FEM reference / possible backend** | Windows packaging and acoustic-specific implementation still need PoC |
| PETSc/SLEPc | sparse linear/eigen solvers, CPU/GPU backends | **Reference / optional solver infrastructure** | native Windows/HPC packaging is materially more complex |
| Gmsh | CAD/mesh generation, Windows SDK, Python/C/C++ APIs | **Meshing candidate subject to license review** | distribution/license terms must be resolved before embedding |
| FEniCSx | modern FEM formulation stack | **Research/reference** | PETSc/MPI dependency and Windows packaging make it a poor first desktop dependency |
| Bempp-cl | Python BEM with OpenCL/Numba paths, MIT | **Secondary BEM reference** | ecosystem/packaging and room-specific robustness need proof |
| k-Wave | k-space time-domain acoustics, C++ OpenMP/CUDA executables, LGPL | **Algorithm/performance reference** | MATLAB-centric workflow and copyleft/distribution implications |
| pyroomacoustics | C++ image-source/ray tracing, general polyhedral/non-convex rooms, MIT | **Geometric-acoustics PoC/reference** | not a low-frequency full-wave authority; directivity support has method/geometry limits |
| Embree | high-performance ray intersection kernels, Apache-2.0 | **Strong CPU ray-intersection candidate** | acoustics transport/scattering/energy bookkeeping still belongs to HTDT |
| Steam Audio | real-time propagation components | **Architecture/reference candidate** | game-audio assumptions must be separated from engineering room-prediction authority |
| OpenFOAM acoustics | finite-volume CFD/acoustics ecosystem | **Not first-line** | too much CFD/runtime complexity for a small-room desktop predictor |
| COMSOL / ANSYS | mature FEM/multiphysics commercial references | **Independent benchmark/reference only** | closed commercial dependency |
| ODEON / CATT / EASE / Treble | mature room-acoustics workflows | **UX/architecture/reference only** | closed implementations; methods/results cannot be assumed equivalent |

Important corrections to the previous roadmap:

- pyroomacoustics can remain useful for general-polyhedral image-source/ray-tracing work and RIR prototyping, but it must **not** be treated as the exact low-frequency predictor for a non-rectangular room.
- REW Room Simulator remains a rectangular baseline/reference path only.
- GPU support is selected per solver/backend; HTDT must not make CUDA/NVIDIA the only valid execution path.

## 4. Verified current implementation facts used by this decision

The research used project/official documentation current on 2026-09-18. Examples:

- MFEM documents CPU, OpenMP, CUDA and HIP-capable backends and is BSD-3-Clause:
  - https://mfem.org/
  - https://github.com/mfem/mfem
- PETSc documents CUDA/HIP/Kokkos/OpenCL backends, while its Windows documentation describes Windows HPC setup as more difficult:
  - https://petsc.org/main/install/windows/
  - https://petsc.org/main/overview/gpu_roadmap/
- Gmsh provides Windows binaries/SDK and C/C++/Python/Julia/Fortran APIs:
  - https://gmsh.info/
  - https://gmsh.info/dev/doc/texinfo/gmsh.html
- pyroomacoustics contains C++ image-source/ray-tracing support for 2D/3D and general polyhedral rooms, and exposes absorption/scattering materials:
  - https://github.com/LCAV/pyroomacoustics
- Embree is an Apache-2.0 ray-intersection kernel library:
  - https://github.com/RenderKit/embree
- k-Wave provides C++ OpenMP and NVIDIA CUDA executables and is LGPL:
  - https://www.k-wave.org/
  - https://www.k-wave.org/license.php
- Bempp-cl is MIT and uses Numba/OpenCL-oriented BEM kernels:
  - https://github.com/bempp/bempp-cl

Exact third-party version pins and redistribution obligations are **not** frozen by this document. They are part of the R100 license/package gate and must be rechecked at the commit/version actually selected.

## 4A. Deep Research refinement: method scope and corrections

The follow-up Deep Research broadens the R100 comparison without changing the core architecture. The important outcome is **not** that one solver has already won; it is that the bakeoff must compare methods on the same physical fixtures and desktop-product constraints.

### Low-band method scope

R100 must consider the following method families explicitly:

| Method family | R100 role | Why it matters | Primary risks / reasons not to preselect |
|---|---|---|---|
| Structured-grid FDTD / related time-domain finite differences | **Primary PoC** | Broadband IR in one run, simple data-parallel update, natural GPU mapping, repeatable grid compilation | numerical dispersion, staircase geometry, thin-surface loss, impedance-filter stability, memory/time-step cost |
| Frequency-domain FEM | **Primary independent reference / production alternative** | irregular geometry and impedance boundaries fit naturally; strong reference value for convergence studies | repeated-frequency sparse solves, meshing cost, preconditioner/packaging complexity |
| Higher-order / DG / spectral-element variants | **Research/secondary bakeoff** | may reduce dispersion per DOF and improve complex-geometry fidelity | implementation and dependency complexity may outweigh benefit for a Windows personal application |
| BEM / FMM-BEM | **Secondary reference** | attractive for boundary/radiation/opening problems and independent cross-checks | dense/hierarchical operators, interior resonance handling, packaging/performance complexity |
| PSTD / k-space approaches | **Algorithm/performance reference** | very low dispersion in suitable domains and useful as a numerical reference | global transforms / regular-domain assumptions and desktop integration constraints |
| Modal/eigenmode methods | **Verification / acceleration candidate** | excellent for analytical box checks, low-mode inspection and possible reduced-order acceleration | not a general replacement for arbitrary geometry/material broadband prediction |
| Digital waveguide mesh / generic finite-volume acoustics | **Background only unless a concrete implementation proves an advantage** | related time-domain formulations can illuminate dispersion/stability trade-offs | no current evidence that they should displace the primary FDTD/FEM bakeoff |

No universal “N points/elements per wavelength” rule is accepted as the production validity criterion. Such rules can seed a starting resolution, but the declared valid band must come from **backend-specific convergence measurements**.

### Geometrical-acoustics scope

R150 should separate transport mechanisms rather than treating “ray tracing” as one authority:

- deterministic direct path and image-source/specular paths where geometry permits;
- general-polyhedral stochastic ray tracing for higher-order transport;
- explicit scattering/roughness energy models;
- diffraction only when an implemented method has a stated validity range and verification fixture;
- late reverberant energy as an energy-domain result unless a method explicitly provides a defensible coherent phase model.

Beam/cone/pyramid tracing, edge-diffraction methods such as UTD/BTM, phonon/particle mapping and other advanced transport techniques remain candidates for later bakeoff if direct/specular + ray transport cannot meet the acceptance fixtures.

### Hybrid implication

The crossover must be an **overlap contract**, not a hard-coded 300 Hz switch. R160 must retain per-band solver provenance and measure the overlap for:

- magnitude/energy continuity;
- arrival-time continuity;
- decay consistency;
- phase validity only where both inputs actually contain coherent phase.

The room's modal/transition context, wave-solver convergence ceiling, source-data validity and geometric-method validity all constrain the overlap.

## 4B. R100 concrete software shortlist

The first bakeoff should stay deliberately small enough to finish, while keeping independent references:

| Layer | First-line shortlist | Secondary/reference | Explicit non-role |
|---|---|---|---|
| Wave time-domain | small HTDT CPU prototype; PFFDTD as implementation/algorithm reference | k-Wave executables where useful for comparison | do not adopt CUDA-only correctness |
| FEM | MFEM-based acoustic prototype, with Gmsh or another controlled mesh path if needed | FEniCSx / PETSc / SLEPc as research or solver-infrastructure references | do not make a heavy HPC stack a desktop dependency before packaging evidence |
| BEM | none as first shipping path | Bempp-cl / FMM-BEM research fixtures | do not block R130 on BEM |
| Geometric | pyroomacoustics for general-polyhedral RIR/reference cases; Embree as CPU intersection-kernel candidate | Steam Audio / Wayverb as architecture/behavior references | do not treat game-audio or GA output as low-band full-wave authority |
| Commercial | none as dependency | COMSOL/ANSYS/Actran/VA One for independent numerical comparison when available; ODEON/CATT/EASE/Treble for workflow/GA comparison | do not copy closed implementation assumptions into HTDT authority |

R100 must record exact version/commit, license, redistribution implications, Windows build/install path and backend availability for every candidate actually executed. A project name in a research matrix is not enough to approve a dependency.

### Deep Research claims intentionally not promoted to architecture facts

The follow-up report contained several broad ecosystem summaries. The roadmap must **not** turn those into requirements without direct verification. In particular:

- do not classify a package as FEM/BEM/FDTD merely because it appears in an acoustics ecosystem list;
- do not equate a partitioner or mesher feature with GPU solver support;
- do not assume a published GPU speedup transfers to HTDT's room sizes, boundary models or consumer hardware;
- do not use a fixed calendar/Gantt date from a research report as the implementation schedule;
- do not use a single elements-per-wavelength heuristic as an acceptance gate.

These remain R100 measurements or source-verification tasks.

## 4C. R100 benchmark and decision matrix

Every primary candidate must be judged against the same fixture families.

**Physics / accuracy**

1. rigid rectangular analytical modal frequencies;
2. grid/mesh convergence and declared valid upper frequency;
3. single impedance boundary with known/reference reflection behavior;
4. L-shaped / concave room;
5. explicit Portal to a modeled adjacent region or an explicit BoundaryTermination;
6. large reflecting obstacle / counter-like geometry;
7. receiver reciprocity/symmetry cases where the formulation permits them.

**Geometry / materials**

- self-intersection/non-manifold/open-boundary diagnostics;
- thin-surface disappearance at coarse resolution;
- material-only change must alter semantic cache identity and prediction;
- no scalar absorption -> unique complex impedance conversion without an explicit model.

**Geometric acoustics**

- direct-path delay;
- first-order reflection point/path length;
- occlusion;
- seeded stochastic repeatability;
- energy-decay behavior;
- diffraction/scattering only when an implemented model can be independently checked.

**Product / execution**

- clean Windows setup or build reproducibility;
- license and redistribution review;
- CPU-only execution;
- CPU thread scaling and oversubscription behavior;
- GPU result within declared numerical tolerance when a GPU backend exists;
- RAM/VRAM estimate versus measured peak;
- cancellation/stale-result behavior;
- cache/resume identity and no duplicate completed candidate work.

R100 produces a decision record with at least: accuracy, runtime, peak RAM/VRAM, setup/build complexity, license, failure modes, valid band and unresolved risks. Production selection is made from this evidence, not from theoretical elegance alone.

## 4D. Plan re-review: benchmark authority before solver bakeoff

R100 is an umbrella with two ordered sub-gates.

### R100A — benchmark authority / fixture contract

Before any solver is compared, define a minimal solver-neutral benchmark representation. This is **not** the final product schema and must stay smaller than R110.

It must represent only what is required to compare candidates without giving each backend a different physical problem:

- acoustic regions / air volumes;
- surfaces with stable fixture IDs;
- explicit portals/openings between regions;
- boundary termination when a portal intentionally leaves the modeled domain;
- source excitation/reference point;
- receiver point/orientation;
- boundary/material model identity;
- environment/air state;
- expected analytical/reference observables and tolerances.

A raw hole in a wall is not a complete acoustic boundary condition. For an opening, the fixture must say whether it connects to an explicitly modeled adjacent air region or to an explicit termination model. Unknown space beyond an opening is never silently converted to an absorbing boundary.

R100A also separates **hard gates** from comparison metrics.

Hard pass/fail gates include:

- physically correct fixture interpretation;
- required geometry/boundary capability for that candidate role;
- demonstrated convergence for the quantity under test;
- reproducible Windows build/run path for shipping candidates;
- acceptable license/redistribution status for shipping candidates;
- CPU correctness path for any shipping wave solver.

Only candidates that pass the applicable hard gates are compared on runtime, RAM/VRAM, implementation complexity and acceleration potential.

### R100B — solver bakeoff / ADR

Run FDTD, independent FEM/reference and geometric reference candidates against the same R100A fixtures. R100B produces the solver-selection ADR and records rejected/secondary candidates with evidence.

This ordering prevents the FDTD and FEM prototypes from each inventing incompatible geometry, opening or material semantics before the production AcousticSceneSnapshot exists.

### Numerical observable contract and staged gates

R100A must fix units and conventions before solver comparison: source quantity and normalization (for example volume velocity and pressure transfer), density/sound speed, Fourier/phase sign, time zero, peak/RMS convention, boundary-normal direction, and the physical source/receiver coordinates. Each adapter records injection/sampling interpolation and coordinate error; moving probes to convenient grid nodes silently is prohibited.

A rigid **lossless closed** room fixture tests eigenfrequencies, symmetry and finite-time energy behavior. Its steady forced response at an excited eigenfrequency is not a finite reference FR, and its decay is not a finite RT60. Compare FR/phase either away from poles under an explicitly shared formulation, or with a separately specified loss/regularization model; compare finite-time IRs with the same excitation, observation duration and processing. Never introduce hidden damping just to make solvers agree. [COMSOL's enclosed-space example](https://www.comsol.com/blogs/how-to-model-fundamental-sources-in-enclosed-spaces) documents the lossless resonance issue.

The manifest also fixes:

- spatial resolution, time step/stability condition or frequency sampling, duration, precision, solver residual/termination criteria and convergence refinement sequence;
- excitation spectrum and normalization/deconvolution, analysis window, resampling/filtering, frequency grid and output units;
- observable-specific absolute/relative tolerances and reference provenance; near-zero pressure uses an absolute floor and phase-validity mask instead of unbounded relative/dB/phase error;
- independently generated analytical/reference outputs and their own convergence evidence; sharing a buggy compiler must not be the only cross-solver check.

Zero padding does not replace a longer observation for resolving nearby modes. Modal-frequency accuracy alone does not establish transfer-amplitude, phase or decay accuracy. Time step, duration, precision and post-processing belong to result identity and resource estimates as well as the benchmark report.

R100A specifies the fixture families and initial hard tolerances before R100B evaluation. A reference-derived tolerance may be finalized after a documented reference convergence study, but must be versioned and frozen before candidate acceptance; do not relax it retrospectively to pass a candidate.

| Gate | Evidence required at this stage |
|---|---|
| R100A | Versioned fixture/observable/tolerance manifest, role-to-fixture applicability and analytical/reference provenance plan. No production kernel or GUI required |
| R100B | Executed primary PoCs on their applicable fixtures, reference convergence, initial Windows/CPU resource envelope and ADR. Report unsupported, failed and deferred separately |
| R110–R130 | Product persistence/editor/compiler, stale/cancel/resource preflight and wave boundary fixtures for each delivered capability |
| R140–R170 | Production scheduler/cache/resume, optional GPU comparisons, hybrid and optimization integration fixtures |
| R180 | Preregistered owned-room campaign evidence |

Later product integration or hybrid acceptance is not a prerequisite for completing R100B. A shipping candidate must demonstrate the required CPU/Windows path; an independent reference may use another platform when its reproducible environment and exported results are recorded. GPU absence is an explicit not-applicable acceleration comparison, never a waiver of CPU correctness.

## 5. Acoustic data model

### 5.1 AcousticSceneSnapshot

Compile an immutable solver snapshot from an exact SceneRevision.

At minimum bind:

- SceneRevision ID/content hash;
- semantic acoustic geometry hash;
- compiled representation hash when a backend-specific mesh/grid/BVH exists;
- acoustic compiler ID/version/tolerance/simplification policy;
- surface/object material assignment hash;
- source excitation + directivity model hash;
- receiver model/calibration hash and receiver set;
- environment/air-state hash used for sound speed/air loss;
- solver ID/version/backend;
- numerical resolution and frequency validity;
- approximation/simplification rules;
- random seed when stochastic algorithms are used.

The semantic acoustic geometry hash describes the physical acoustic interpretation. The compiled representation hash describes the exact generated grid/mesh/BVH and therefore changes when compiler version, tolerance, meshing/voxelization parameters or backend representation changes.

The snapshot is separate from the editable CAD scene. Editing the scene invalidates/stales the snapshot; it never mutates an existing prediction.

### 5.2 Geometry representations

A canonical acoustic region/surface model feeds backend-specific compiled forms:

~~~text
SceneRevision
  -> AcousticRegion(s)
      -> surfaces / objects / explicit Portal(s) / BoundaryTermination(s)
      -> canonical acoustic triangle/surface representation
          -> structured wave grid / voxel boundary map
          -> FEM surface/volume mesh (reference backend)
          -> ray-tracing BVH
~~~

This prevents each solver from inventing its own interpretation of doors, openings, furniture and materials. An opening is not represented only as “missing wall geometry”: it either connects two modeled acoustic regions or carries an explicit termination model. Unmodeled adjacent space remains unknown/unsupported rather than being silently treated as anechoic.

The compiler must detect and report:

- self intersections;
- non-manifold surfaces where a backend requires manifold geometry;
- open boundaries not explicitly marked as an opening;
- zero-area/degenerate faces;
- thin surfaces that would disappear at the selected wave-grid resolution;
- simplification error.

No automatic rectangularization is permitted.

### 5.3 Product input and acoustic participation

The current SceneDocument has a single RoomPrism; the existing editor does not already author arbitrary connected air volumes. R110 must define a persisted, versioned acoustic configuration linked to the exact SceneRevision, plus authoring of material assignments, source/receiver/environment properties, adjacent-region geometry and portal/termination choices. R120 must compile this configuration and retain surface-to-Scene IDs for diagnostics/selection. Save/reopen, Undo/Redo, stale invalidation and old-scene loading are acceptance cases. Old scenes open with unresolved acoustic inputs; they do not acquire invented materials or adjacent rooms.

The first supported product geometry is an explicit subset: concave polygon prisms, supported object surfaces/volumes and connected prism regions or declared terminations. Sloped/curved ceilings and other general 3D shapes remain unsupported until separately specified, authored and verified; a backend's mesh capability alone does not establish an editor feature. The umbrella goal remains broader than the first release.

Separate visibility from acoustic participation. Hiding a sofa or locking a cabinet does not remove its acoustic boundary. Source and receiver markers are not automatically solid obstacles. For each physical entity record whether/how its volume or thin surface participates, including any deliberate omission.

When a loudspeaker cabinet participates as an obstacle, its movement/rotation changes the acoustic domain. Define emitter/baffle coupling or a verified equivalent model; a point source trapped inside a sealed rigid cabinet is invalid. Free-field directivity data that already include cabinet radiation must not receive the same cabinet effect twice without a validated coupling model. Unsupported combinations fail closed.

### 5.4 Thin objects

Rugs, curtains and thin panels should not be forced into thick furniture volumes.

Support a surface/boundary representation with explicit thickness/model metadata when the solver needs it. If a thin object cannot be represented at the selected grid resolution, the solver must either use an equivalent boundary model with provenance or report it as unresolved.

## 6. Material model

Two different physical domains are required.

### Geometrical acoustics

Use banded energy coefficients such as:

- absorption;
- specular/diffuse scattering split;
- optional transmission when implemented.

Octave or one-third-octave data are appropriate inputs for this layer.

### Wave acoustics

Use phase-bearing boundary models such as:

- complex surface impedance/admittance;
- rigid/pressure-release special cases;
- frequency-dependent impedance filters for time-domain execution;
- parameterized porous models where justified.

Potential porous models to evaluate include Delany–Bazley/Miki and Johnson–Champoux–Allard-type families. The chosen model and parameters must be explicit.

A scalar absorption coefficient alone is insufficient to reconstruct unique low-frequency phase/impedance behavior. HTDT therefore stores the original measurement/preset type and does not silently convert an energy coefficient into a unique complex impedance.

Material presets must store source, version, applicable frequency range and uncertainty/assumption status. User-measured/custom materials are separate records.

Wave-domain material capability must be explicit. At minimum distinguish:

- `measured_complex_impedance`;
- `parametric_impedance_model`;
- `rigid_assumption`;
- `geometric_energy_only`;
- `unknown`.

A material that only has absorption/scattering data may still participate in geometrical acoustics, but it is not automatically valid for a phase-bearing low-frequency wave solve. Choosing a rigid or other equivalent approximation is an explicit model assumption with provenance, not an implicit default.

## 7. Source / receiver / environment authority

Internal source authority should support:

- source acoustic reference point;
- physical cabinet orientation;
- acoustic aim independent of body orientation;
- source channel/role;
- excitation/level/phase reference needed by the selected solver;
- frequency-dependent magnitude/phase/directivity dataset;
- directivity coordinate frame;
- dataset/version/provenance.

Do not hard-code a particular commercial loudspeaker format into the domain model. Define an internal DirectivityDataset, then add import adapters where licensing/specification allows.

Receiver authority is separate from the source and should support:

- receiver acoustic point / microphone capsule position;
- orientation when the measurement or receiver model requires it;
- receiver response/calibration profile identity;
- absolute/relative level reference;
- timing reference and phase-validity state;
- provenance linking to the existing MicrophoneProfile/AcquisitionContext authority when comparing against REW measurements.

Environment authority must record the state/model used by the prediction, including temperature and the resulting sound-speed model at minimum; humidity/pressure/air attenuation are added when the selected valid band/model uses them. Measurement validation compares predictions against the environment known or assumed for that campaign rather than silently using a universal 343 m/s constant.

SOFA is a useful general spatial-acoustics interchange candidate. Generic polar CSV/import is also needed because loudspeaker manufacturer data vary. CLF/GLL and other proprietary ecosystem formats require separate format/license review before implementation.

For very low frequencies, an omnidirectional/monopole approximation can be an explicit source model when its validity is documented; it must not silently replace a supplied directional model outside its valid band.

## 8. Hybrid result contract

The hybrid output is not one solver pretending to be exact everywhere.

Store per-band provenance:

- wave-valid band;
- geometric-valid band;
- overlap band;
- crossover/stitch algorithm and version.

Initial result types are intentionally distinct:

- `CoherentTransfer` / coherent IR from a solver that carries phase;
- `DeterministicPathSet` for direct/early geometric paths;
- `LateEnergyDecay` for stochastic/diffuse energy that does not carry defensible coherent phase.

Initial hybrid design:

1. produce low-band coherent pressure/IR from the wave solver;
2. produce direct/early specular paths from the geometric solver;
3. produce stochastic/diffuse late energy only as an energy-domain result unless the algorithm explicitly defines phase;
4. identify which direct/early physical components are represented by both domains;
5. time-align and crossfade/combine without double-counting those shared components;
6. apply complementary crossover windows only to compatible quantities over a finite overlap band;
7. validate amplitude/energy continuity and impulse timing at the stitch.

A `LateEnergyDecay` is not converted into a complex FR merely to make the API uniform. Metrics are enabled only when their underlying result type and time/energy semantics support them.

Crossover is not hard-coded globally to exactly 300 Hz. The default target can start near the wave-solver upper band, but the final crossover must respect:

- selected wave-grid/mesh convergence limit;
- room transition/Schroeder-frequency context;
- geometric solver validity;
- source/material data validity.

If a metric is not valid for a band/result type, the UI disables it instead of extrapolating.

A usable overlap is not guaranteed. If wave convergence ends below the geometric method's validated lower limit (including occlusion/diffraction applicability), preserve separate band-limited outputs and mark the gap unsupported. R160 may proceed only after extending verified wave coverage, adding a verified bridging method, or explicitly narrowing the requested output. Smoothing across a gap or quoting a Schroeder estimate is not evidence of valid overlap. Add both valid-overlap and no-overlap fixtures.

Deterministic path geometry alone does not authorize coherent pressure: path-to-transfer conversion also needs compatible source normalization, complex reflection/directivity and timing. When those are absent, retain path/energy output and disable coherent summation. Any synthesized stochastic tail is a separately labeled realization with seed/model provenance, not recovered physical phase.

Decay/clarity output needs its own analysis contract: band filters, direct-arrival time origin, observation length, tail truncation/noise treatment, fit interval/quality and energy coverage. Insufficient decay or a missing tail gives unavailable/qualified output, not a misleading finite RT60 or C50/C80. Distinguish local modal decay from diffuse-field reverberation time, especially in the low-band target; [REW's RT60 documentation](https://www.roomeqwizard.com/help/help/html/graph_rt60.html) explains the small-room limitation. R160 acceptance includes a truncated tail and a non-decaying rigid reference.

## 9. Compute architecture

### 9.1 Correctness baseline

Every solver selected for shipping must have a CPU path that can execute the acceptance fixtures. GPU is optional acceleration.

Even the first CPU prototype needs bounded execution: preflight its grid/mesh, boundary/filter state, solve workspace, receiver histories and requested field output against an explicit memory/disk budget; specify duration/work limit and cancellation checkpoints. Product jobs keep the existing stale/document-switch guard from R110/R130. R140 adds automatic hardware discovery and coordinated planning, rather than introducing these basic protections for the first time.

Full space-by-time field storage is opt-in and budgeted. Probe histories, selected snapshots or frequency slices can be requested separately; requested and executed output coverage is immutable. Do not silently drop requested outputs or restart an oversized GPU job on a CPU without rechecking RAM/work limits.

### 9.2 Scheduler hierarchy

HTDT controls both levels:

- outer parallelism: candidate/source batches;
- inner parallelism: solver threads or GPU kernels.

The scheduler chooses combinations that do not oversubscribe cores.

It must estimate RAM/VRAM before execution and persist:

- backend/device;
- worker count;
- solver thread count;
- precision;
- grid/mesh size;
- actual quality/resolution;
- fallback or downgrade reason.

Silent quality downgrade is prohibited.

### 9.3 Backend policy

Do not couple the prediction schema to CUDA, HIP, SYCL or OpenCL.

Use a solver/backend capability contract with functions equivalent to:

~~~text
capabilities()
estimate_resources(snapshot, request)
compile(snapshot, quality)
execute(compiled, source_batch, receiver_batch, cancellation)
provenance()
~~~

The first implementation can optimize NVIDIA hardware if that is the best measured path, but the CPU authority remains usable and AMD support can be added without changing prediction identity semantics.

## 10. Reuse opportunities for optimization

The scheduler should exploit physics/solver structure before merely adding threads.

For fixed geometry/materials:

- reuse voxel/grid boundary compilation;
- reuse ray-tracing BVH;
- reuse FEM matrix/preconditioner/factorization where frequency/formulation allows;
- collect many receivers from one time-domain wave solve;
- use reciprocity where the exact source/receiver model allows it;
- batch sources/receivers instead of restarting setup work per candidate.

Cache identity includes semantic geometry, compiled representation, material, source excitation/directivity, receiver model/set, environment, solver/backend, numerical parameters and frequency band.

Before adding more outer workers, R170 should exploit exact reusable structure when the formulation permits it: receiver batching from one solve, source-equivalence grouping, reciprocity, reusable FEM matrices/preconditioners/factorizations and reusable grid/BVH compilation. These are optimization opportunities, never assumptions applied where source/receiver models break the required symmetry.

### Reuse and candidate-selection acceptance

Reuse depends on the actual operator, not on candidate membership in one search. Source-only or receiver-only movement can reuse fixed compilation when acoustic geometry/material/environment and discretization remain unchanged. Moving/rotating an acoustically participating cabinet, seat or other obstacle invalidates affected geometry/grid/BVH/matrix caches. Changing material, environment, boundary, frequency/formulation or numerical settings invalidates the relevant layers. A receiver sample not retained in an earlier run requires new evaluation or a solve; receiver batching does not imply an arbitrary saved full field.

Separate reusable numerical artifacts from immutable PredictionRun bindings. A cache hit for equivalent physical inputs creates an explicit result association to the requesting exact SceneRevision and candidate; it never relabels an old run as current. Verify reuse versus a fresh solve, and include cabinet rotation, material-only change, receiver-only change and view-only hide as invalidation fixtures.

Coarse fidelity is an explicitly validated model/resolution, not merely a faster setting. It must preserve portal connectivity and required thin/obstacle behavior or report unsupported. A rectangular-only predictor must not eliminate concave-room candidates. Unsupported/missing objectives are not zero, infinity or poor scores.

Screening uses hard geometric constraints for definitive feasibility rejection. Acoustic coarse screening needs documented discrepancy/uncertainty criteria against finer runs, an audit sample of discarded candidates and recovery when ranking reversals are observed. Without a validated error bound it is heuristic shortlisting, not proof that the global Pareto set was retained. Before reporting a final simulated Pareto comparison, recompute retained candidates with a common validated fidelity, band, source/reference and objective spec; mixed-fidelity scores cannot silently establish dominance. Include a coarse/fine ranking-reversal fixture. If the budget cannot support refinement, label the result preliminary and keep the production recommendation gate closed.

## 11. Validation ladder

### L0 — deterministic math/unit references

- hash/canonical snapshot;
- coordinate transform;
- material interpolation;
- directivity interpolation;
- crossover filters.

### L1 — analytical room references

Rigid rectangular room:

- modal frequencies against closed-form analytical values;
- symmetry and reciprocity cases;
- source/receiver coordinate checks.

The initial wave PoC target is <=0.5% modal-frequency error over the declared converged band for the reference box; tighter limits may be adopted after convergence study.

### L2 — numerical convergence

For each backend:

- refine grid/mesh;
- verify result convergence;
- record error versus DOF/runtime/RAM/VRAM;
- establish a backend-specific valid upper frequency.

Do not derive the valid band from a rule of thumb alone.

### L3 — cross-solver fixtures

Compare FDTD against an independent FEM/reference solver for:

- rectangular rigid room;
- impedance boundary;
- L/concave room;
- opening;
- large reflecting object.

Agreement tolerance is defined from convergence error and the quantity being compared, not one global dB threshold.

### L4 — geometric acoustics references

- direct path delay;
- first-order reflection point/path length;
- deterministic image-source cases;
- scattering seed repeatability;
- energy decay sanity cases.

### L5 — hybrid stitch

- direct-arrival timing preserved;
- no artificial level discontinuity through overlap;
- energy decay continuity;
- no unsupported high-band phase claim.

### L6 — owned room

Use the existing O60 campaign authority:

- calibration/holdout separation;
- residual trend;
- sensitivity;
- repeatability;
- candidate separation;
- applicability.

UMIK-1/REW evidence remains the final owned-room validation path.

## 12. Implementation phases

### R100 — research / bakeoff umbrella

#### R100A — benchmark authority / fixture contract

Deliver the solver-neutral fixture representation, hard pass/fail gates, quantity-specific tolerances and shared fixture corpus before comparing implementations.

Minimum fixtures are the analytical rigid box, impedance/reflection boundary, concave/L-room, explicit region-to-region portal or explicit termination, reflecting obstacle, direct/first reflection geometric cases and later overlap-stitch cases.

#### R100B — solver bakeoff / ADR

Deliver:

- this research note plus the Deep Research refinement;
- third-party version/license/redistribution/Windows-package matrix;
- common solver interface and provenance contract;
- small deterministic FDTD CPU prototype;
- one independent FEM/reference prototype;
- simple geometric-acoustics prototype/reference;
- measured CPU scaling and, when available, GPU-vs-CPU tolerance/resource evidence;
- an explicit decision record naming the selected first production stack and rejected/secondary alternatives with reasons.

Exit only after applicable hard gates pass and measured Windows/CI evidence selects the first production stack. R100 does **not** freeze the final crossover frequency, GPU vendor/backend, universal mesh density or the long-term BEM/DG/PSTD role.

### R110 — acoustic scene/material/source/receiver authority

Implement immutable AcousticSceneSnapshot, AcousticRegion/Portal/BoundaryTermination semantics, acoustic surfaces, object/surface material capability, source excitation/directivity, receiver/calibration, environment authority and prediction provenance schema.

Define semantic acoustic geometry identity separately from backend-compiled representation identity.

No high-cost solver is required to finish the data contract.

### R120 — acoustic geometry compiler

Compile exact Scene geometry and R110 region/portal semantics into:

- canonical triangulated acoustic regions/surfaces;
- explicit portal/termination representation;
- wave-grid representation;
- ray BVH input;
- optional FEM mesh input.

Persist compiler version/tolerance/approximation provenance and compiled representation identity. Add fail-closed diagnostics for non-manifold/unintended-open/degenerate/thin/unresolved geometry.

### R130 — low-band wave solver

Initial target: 20–300 Hz. Split correctness so boundary-model failures are distinguishable from the core discretization.

#### R130A — rigid-boundary core

- deterministic CPU wave solver;
- rigid rectangular analytical modes;
- concave/portal-capable geometry path as supported by the chosen stack;
- multiple receivers;
- FR/phase/IR/spatial field output subject to the numerical observable contract (lossless eigenmodes and finite-time responses are distinct);
- convergence and independent cross-solver validation.

#### R130B — simple lossy / locally reacting boundary

Add the simplest independently verifiable impedance/admittance boundary required by the selected formulation and verify reflection magnitude/phase against reference cases.

#### R130C — causal frequency-dependent boundary

Add the production frequency-dependent boundary implementation only after R130A/B are sound. For time-domain execution, stability/passivity/causality behavior is part of acceptance.

GPU acceleration follows the same physical contract after CPU correctness is established.

### R140 — hardware-aware execution

R110/R130 already establish immutable identity, stale/cancel semantics and backend provenance. R140 **enhances execution**, adding CPU/GPU capability detection, resource estimation, two-level scheduler, candidate/source/receiver batching, oversubscription control and efficient cache/resume.

A CPU-only machine remains supported. R140 must not redefine prediction identity merely to fit a scheduler.

### R150 — geometric acoustics

Implement/choose:

- direct path;
- early specular reflections;
- image-source where valid;
- general-polyhedral ray tracing;
- banded absorption/scattering;
- source directivity;
- deterministic seed/provenance;
- late/diffuse energy only with explicit semantics.

### R160 — hybrid broadband result

Implement overlap/crossover and derive only metrics supported by the combined authority:

- FR;
- IR;
- ETC;
- reflection paths;
- spatial field where meaningful;
- RT60/EDT/C50/C80 where the underlying result is valid.

### R170 — optimization integration

Connect arbitrary-room prediction to:

~~~text
SearchSpec
 -> feasible candidates
 -> multi-fidelity prediction
 -> ObjectiveVector
 -> Pareto
 -> MeasurementPlan
 -> N60 evidence
 -> O60 validation
 -> O70 adaptive planning
~~~

Use coarse screening, cache reuse and uncertainty to avoid high-resolution solves for every candidate, subject to the reuse and candidate-selection acceptance contract in §10.

### R180 — owned-room validation and production gate

Run the real target-room campaign only after numerical/reference gates pass.

The new solver does not bypass Issue #83/O60 evidence policy. A new solver/model version needs its own applicability/owned-room validation before production recommendation.

## 13. Rejected shortcuts

Do not:

- treat pyroomacoustics ray/ISM output as an exact low-frequency wave solution;
- use the room bounding rectangle as the arbitrary-room solution;
- assign one broadband absorption number to every solver band and claim phase accuracy;
- extend wave simulation to 20 kHz just because GPU compute exists;
- require NVIDIA/CUDA for correctness;
- recompute geometry/meshes/BVH for every placement candidate;
- merge predicted data into measured evidence;
- auto-calibrate materials on holdout measurements and then call the same data validation;
- hide resolution downgrade or geometry simplification.

## 14. Next implementation gate (not started)

Implementation remains not started. Resume at **R100A**, delivering the solver-neutral fixture/observable manifest, role-specific hard gates, tolerance policy and reference provenance plan in §4D. Do not start solver kernels first.

After R100A is accepted, R100B delivers one repeatable benchmark command covering the rigid modal reference, concave geometry, CPU wave PoC, independent FEM/reference, geometric direct/first reflection and runtime/memory report, with lossy/portal/obstacle cases according to the candidate's required capability. Record failed and deferred cases explicitly. This is the smallest executable bakeoff that can falsify the architecture; it is not completion of R110–R180 or an owned-room accuracy claim.

## 15. What is frozen now vs. what remains benchmark-gated

### Safe to freeze now

- arbitrary-room support uses a hybrid/multi-fidelity architecture rather than silent rectangular approximation;
- 20–300 Hz is the initial low-band wave target, not a promise that 300 Hz is the final crossover;
- FDTD is the first time-domain PoC and FEM is the primary independent reference/alternative;
- BEM/FMM, DG/high-order FEM and PSTD/k-space remain secondary/reference candidates unless R100 evidence promotes them;
- geometric direct/early paths and stochastic late energy have different semantics;
- scalar absorption, scattering and complex impedance/admittance are distinct authorities;
- CPU correctness/fallback is mandatory and GPU is optional acceleration;
- exact geometry/material/source/solver/backend/resolution provenance is immutable;
- owned-room production recommendation remains gated by O60/Issue #83-style measured validation.

### Must remain open until R100 or later

- production wave solver library/framework;
- exact spatial discretization and per-band resolution presets;
- final crossover/overlap frequency range;
- GPU API/vendor and whether a GPU backend ships in the first production release;
- exact FEM mesher/linear-solver stack;
- whether BEM, DG/high-order FEM, PSTD/k-space or reduced-order methods graduate from reference to product code;
- diffraction model and late-field synthesis method;
- third-party redistribution/version pins;
- numeric CPU/GPU acceptance tolerances and performance budgets.

This split is deliberate: architecture and evidence semantics are stable enough to implement against, while numerical-backend choices remain falsifiable by the R100 bakeoff.
