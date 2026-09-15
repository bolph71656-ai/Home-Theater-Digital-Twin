# Home Theater Digital Twin — Project Plan

> Status: **Planning / pre-implementation**  
> Target: **Windows 11, single-user, personal use**  
> Development model: GitHub repository, local-first application  
> This document is intentionally detailed so implementation can start later without reopening basic architectural decisions.

---

## 1. Project goal

Home Theater Digital Twin (HTDT) is a local application that combines four kinds of information that are usually managed separately:

1. **Physical room model** — room geometry, openings, TV/screen, speakers, listening seats.
2. **Measured acoustic data** — primarily measurements produced by REW (Room EQ Wizard).
3. **Configuration/history** — AVR state, YPAO on/off, speaker placement changes, measurement conditions and notes.
4. **Model-based predictions** — room modes, geometric reflection paths, approximate SBIR candidates and later placement optimization.

The purpose is **not** to build another measurement application. REW remains the measurement engine. HTDT provides the missing layer above it: a persistent digital representation of the actual home theater, linked to measurement history and spatial context.

The project must remain useful for systems **without a subwoofer**. Low-frequency analysis must therefore work directly with full-range/main speakers and should not assume a bass-management or multi-sub workflow.

---

## 2. Product principles

### 2.1 Reuse before build

If REW, SciPy, pyroomacoustics, Three.js or another maintained library already implements a function correctly, HTDT should integrate or reuse it instead of recreating it.

### 2.2 Measurement and simulation are different evidence

The UI and data model must never blur these categories:

- **Measured**: actual REW measurement.
- **Derived**: deterministic calculation from measured data.
- **Predicted**: room/speaker model estimate.
- **Hypothesis**: likely explanation such as SBIR or early reflection candidate.

A predicted 85 Hz null must not look equivalent to an 85 Hz null actually measured in REW.

### 2.3 Local-first and single-user

This is a Windows personal tool, not a SaaS product.

Therefore:

- no user accounts;
- no cloud database;
- no authentication layer for the local UI;
- no multi-user permission system;
- no mandatory telemetry;
- no encryption-at-rest requirement;
- no server deployment requirement.

The local application/API should bind to `127.0.0.1`, primarily to avoid accidentally exposing local controls on the LAN. That is sufficient for the intended use case.

### 2.4 Progressive fidelity

Start with measurements and simple analytical models. Do not begin with a physically complete acoustic simulator.

Priority order:

1. measured data;
2. simple analytical room-mode model;
3. image-source / geometric reflection model;
4. optimization built on validated models;
5. advanced simulation only if real use demonstrates a need.

---

## 3. Primary use cases

### UC-01 — Create a room digital twin

The user enters room dimensions and optionally irregular walls/openings, then places:

- TV/screen;
- FL / C / FR;
- SL / SR;
- height speakers such as FHL / FHR;
- listening seats / MLP;
- optional furniture/reference objects.

The initial version needs only enough geometry to support acoustic reasoning. It is not a CAD package.

### UC-02 — Import REW measurements

Import measurements from REW and associate each measurement with:

- speaker/channel;
- listening position;
- date/time;
- YPAO state/profile;
- master volume / measurement level if known;
- speaker placement revision;
- microphone/calibration metadata;
- notes/tags.

### UC-03 — Compare speakers and configurations

Examples:

- FL vs FR;
- C vs FL/FR;
- YPAO OFF vs ON;
- speaker position A vs B;
- MLP vs left/right seat;
- before vs after furniture/curtain changes.

### UC-04 — Explain low-frequency problems spatially

Correlate measured peaks/dips with:

- analytical room modes;
- distances to nearby boundaries;
- estimated SBIR cancellation frequencies;
- speaker/listener positions.

The output should be phrased as candidate explanations, not absolute diagnoses.

### UC-05 — Inspect impulse / reflection behavior

Visualize IR/ETC and associate strong arrivals with predicted wall/ceiling/floor paths where geometrically plausible.

### UC-06 — Maintain measurement history

The application should answer questions such as:

- “Which FL position produced the smoothest 60–200 Hz response?”
- “What changed after the sofa moved 20 cm?”
- “Was this measurement taken with YPAO Flat or Through?”

### UC-07 — Later: evaluate alternative positions

Given practical movement bounds for speaker/listener positions, search candidate placements and compare model-based objective functions before physically moving equipment.

---

## 4. Explicit non-goals

The following are intentionally **not** part of the early implementation.

### Do not build at all unless requirements change

- A replacement for REW measurement sweeps.
- A full audio interface / ASIO / WASAPI measurement engine.
- A Dirac/YPAO/Audyssey-like proprietary room-correction system.
- Reverse engineering of Yamaha firmware or private YPAO algorithms.
- A professional CAD/BIM package.
- Cloud accounts, login, permissions or remote access infrastructure.
- A general home-automation platform.

### Defer for a long time

- Direct parsing of undocumented REW `.mdat` internals.
- Full FEM/BEM/FDTD wave simulation.
- Real-time ray tracing.
- Automatic PEQ generation intended to replace REW EQ tools.
- Multi-sub optimization as a core feature.
- LLM/AI interpretation.
- Mobile application.
- macOS/Linux packaging.

---

## 5. Existing software: Build / Reuse / Integrate / Defer

| Capability | Decision | Technology / product | Rationale |
|---|---|---|---|
| Acoustic measurement sweeps | **Integrate** | REW | Mature, trusted, already solves measurement I/O and calibration. |
| Frequency/phase/IR source data | **Integrate** | REW API / REW export | Avoid duplicating measurement computation. |
| `.mdat` binary parsing | **Defer** | REW native format | Undocumented binary dependency creates unnecessary maintenance risk. |
| Numerical arrays / FFT support | **Reuse** | NumPy / SciPy | Mature scientific stack. |
| Signal processing helpers | **Reuse** | SciPy; evaluate pyfar/acoustic-toolbox when a concrete need appears | Do not introduce dependencies before use cases require them. |
| Room-mode calculation | **Build small** | simple analytical formulas | Very small, transparent domain logic; easy to test. |
| Image-source simulation | **Reuse later** | pyroomacoustics | Existing implementation is preferable to writing a geometric acoustics engine. |
| 3D scene rendering | **Reuse** | Three.js via React Three Fiber | Good fit for interactive room/speaker visualization. |
| 2D engineering plots | **Reuse** | Plotly.js or ECharts; decide by prototype | Need zoom, cursor, overlays and logarithmic frequency axes. |
| Optimization | **Reuse later** | `scipy.optimize`; consider pymoo only if multi-objective needs justify it | Start with common algorithms already in SciPy. |
| Persistence | **Reuse** | SQLite | Single-user local application; zero server administration. |
| Desktop shell | **Defer** | Tauri | A native shell is not needed to validate the application architecture. |
| AVR control | **Integrate later** | adapter layer; Yamaha first | Keep optional and vendor-specific. |
| Yamaha YPAO internal coefficients | **Do not build** | — | Treat before/after measurements as authoritative evidence. |

---

## 6. REW integration strategy

REW is an external first-class dependency, not an implementation detail.

### 6.1 Canonical integration path

Preferred order:

1. **REW localhost API** for measurements already open in REW.
2. **Text/CSV/IR export import** as portable fallback.
3. Manual metadata entry when an external format does not encode room/session context.

REW exposes a localhost HTTP API (default `127.0.0.1:4735`) and supports data retrieval when the API is enabled. Automated sweep control has different licensing constraints, so HTDT should not depend on automatic measurement execution for its core operation.

### 6.2 Do not make `.mdat` the canonical format

Reasons:

- it is REW-specific;
- binary structure may change;
- HTDT only needs a subset of REW's data;
- the REW API/export paths are clearer integration boundaries.

If a stable third-party parser later becomes trustworthy and useful, it can be added as an optional importer.

### 6.3 HTDT canonical measurement representation

Internally, normalize imported data into a versioned structure independent of REW:

```text
Measurement
  id
  source = rew_api | rew_export | wav_ir | other
  source_version
  channel_role
  listening_position_id
  captured_at
  sample_rate
  frequency_hz[]
  spl_db[]
  phase_deg[]? 
  impulse_time_s[]?
  impulse_value[]?
  metadata
  provenance
```

The exact storage layout may differ, but the domain model should not expose REW API response shapes directly to the UI.

### 6.4 REW functions HTDT must not recreate

- sweep signal generation;
- microphone/audio interface selection;
- SPL calibration workflow;
- timing reference handling;
- base measurement acquisition;
- REW's mature EQ/filter-generation workflow;
- all REW graphs merely for parity.

HTDT should only implement plots when they are needed for **cross-measurement / spatial / historical** workflows that REW does not naturally provide.

---

## 7. Measurement microphone handling

The Digital Twin does not calibrate microphones itself.

Calibration belongs primarily to REW. HTDT stores provenance metadata so a historical measurement remains interpretable.

Suggested metadata:

```text
MicrophoneProfile
  manufacturer
  model
  serial_number?
  calibration_file_name?
  calibration_orientation = 0deg | 90deg | unknown
  calibration_file_hash?
  notes
```

For products such as UMIK-1/2 or Dayton UMM-6/iMM-6C, individual calibration files may exist. HTDT only records which profile was used; it should not duplicate REW's calibration compensation pipeline.

---

## 8. AVR integration strategy

### 8.1 MVP

No automatic AVR control.

Store a manual snapshot:

```text
AVRConfiguration
  vendor
  model
  profile_name
  room_correction = off | ypao_flat | ypao_natural | ypao_front | other
  speaker_size/settings
  crossover_hz?
  distances?
  levels?
  notes
```

This is enough to compare REW measurements under different AVR states.

### 8.2 Yamaha later

Add an adapter boundary rather than putting Yamaha calls into domain code:

```text
AVRAdapter
  discover()
  read_basic_state()
  read_volume()
  read_input()
  read_sound_program()
  read_available_public_settings()
```

Target Yamaha RX-A4A generation first.

Important rule: **AVR control support does not imply access to YPAO's internal correction data.** HTDT should assume YPAO internals are unavailable unless a documented public interface proves otherwise.

### 8.3 Other vendors

Future adapters may include Denon/Marantz or Onkyo/Pioneer, but vendor support must remain optional plug-in-like infrastructure.

---

## 9. Acoustic analysis boundaries

### 9.1 Phase A — deterministic, low-risk calculations

Implement directly:

- logarithmic interpolation/resampling;
- smoothing utilities when needed for comparison views;
- difference curves;
- mean / RMS deviation across selected bands;
- peak/dip candidate detection;
- left/right difference metrics;
- analytical rectangular-room modes;
- boundary-distance-based SBIR frequency candidates;
- geometry angles/distances between seats and speakers.

### 9.2 Phase B — impulse-derived analysis

Use SciPy/NumPy and validate against REW where possible:

- time-of-flight alignment helpers;
- ETC generation from imported IR;
- direct-arrival detection;
- reflection candidate timing;
- windowed frequency response comparison.

Do not duplicate every REW metric. Add only analyses that are spatially useful in the Digital Twin.

### 9.3 Phase C — geometric prediction

Use pyroomacoustics or another validated library for:

- image-source paths;
- approximate room IR;
- reflection-order exploration.

These predictions must be visually labeled **Simulation**.

### 9.4 Low-frequency warning

Geometric acoustics is not a reliable universal model at low frequencies. For bass-region decisions, measured REW data and analytical modal reasoning take priority over ray-style visuals.

---

## 10. Speaker-role ontology

Internally use vendor-neutral speaker roles rather than tying the schema to a specific immersive format.

Initial roles:

```text
front_left
front_center
front_right
surround_left
surround_right
surround_back_left
surround_back_right
height_front_left
height_front_right
height_middle_left
height_middle_right
height_rear_left
height_rear_right
subwoofer_1 ... subwoofer_n
```

A separate rules layer may later validate layouts against publicly documented Dolby/DTS/Auro guidance.

The application should present those checks as guidance/ranges, not as proprietary certification.

---

## 11. Coordinate system

Use a single documented room-local coordinate system everywhere.

Recommended convention:

- units: **meters**;
- origin: front-left-floor corner of the room reference bounding box;
- +X: right when facing the front screen;
- +Y: toward the rear of the room;
- +Z: upward;
- angles stored in degrees at UI boundaries, radians internally where libraries expect them.

Every object should have a stable ID and transform independent of rendering technology.

```text
Transform
  position: { x, y, z }
  orientation: { yaw, pitch, roll }
```

Do not store Three.js objects directly in persistent data.

---

## 12. Core domain model

### Project

Top-level digital twin.

```text
Project
  id
  name
  schema_version
  room_id
  active_layout_revision
  created_at
  updated_at
```

### Room

```text
Room
  id
  name
  geometry_type = rectangular | polygonal
  dimensions?
  vertices?
  height
  surfaces[]
  openings[]
```

Start with rectangular rooms plus limited polygonal support. Complex curved geometry is not required.

### Speaker

```text
Speaker
  id
  role
  label
  transform
  model?
  notes?
```

### ListeningPosition

```text
ListeningPosition
  id
  label
  transform
  kind = mlp | seat | measurement_point
```

### LayoutRevision

A placement/configuration snapshot.

```text
LayoutRevision
  id
  name
  created_at
  speaker_transforms
  listening_position_transforms
  notes
```

This is important: comparison across physical changes should not mutate history.

### MeasurementSession

```text
MeasurementSession
  id
  name
  captured_at
  layout_revision_id
  avr_configuration_id
  microphone_profile_id
  notes
```

### Measurement

One channel at one listening position under one session.

### AnalysisResult

Versioned derived result:

```text
AnalysisResult
  id
  measurement_ids[]
  analysis_type
  algorithm_version
  parameters
  result
  generated_at
```

Versioning derived analyses avoids silent changes when algorithms improve.

---

## 13. Storage design

### Application state

Use **SQLite** for metadata, relationships and derived analysis summaries.

### Large numerical arrays

For the MVP, avoid prematurely introducing Parquet/Zarr/HDF5.

Use one of these simple options after prototyping:

- compressed NumPy `.npz` files referenced by SQLite; or
- compact binary blobs in SQLite for modest datasets.

Prefer separate `.npz` files if measurement arrays become large because they are easier to inspect and replace independently.

### Raw imports

Preserve the original imported files unchanged when practical:

```text
project-data/
  project.sqlite3
  raw/
    rew-export-2026-09-xx.txt
    impulse-....wav
  arrays/
    <measurement-id>.npz
```

Raw files provide provenance and make importer bugs recoverable.

### Source repository vs user project data

Do not store personal room measurements in the application source repository by default.

Recommended user-data location on Windows:

```text
%USERPROFILE%\Documents\Home Theater Digital Twin\Projects\...
```

---

## 14. Proposed technology stack

### Selected architecture for the first implementation

**Backend / analysis**

- Python 3.12+
- FastAPI
- Pydantic
- NumPy
- SciPy
- SQLAlchemy or SQLModel
- SQLite
- pytest

**Frontend**

- TypeScript
- React
- Vite
- Three.js via `@react-three/fiber`
- Plotly.js or Apache ECharts after a focused graph prototype
- Vitest

**Application execution**

During MVP:

```text
python -m htdt
  -> starts FastAPI on 127.0.0.1:<port>
  -> serves/launches frontend
  -> communicates with REW localhost API
```

The user sees a browser-based local UI, but no external server exists.

### Why not Tauri immediately?

Tauri remains a good packaging option, but it introduces Rust/toolchain/sidecar packaging decisions before core workflows are validated. A local Python + browser application is simpler for an individual Windows project.

Once the UI and analysis model are stable, Tauri can wrap the existing frontend and launch the Python analysis process as a sidecar if a native installer is desirable.

### Why not Electron?

Electron is viable but adds a full Chromium/Node runtime while the scientific stack still needs Python. It provides little benefit during the early validation phase.

### Why not pure .NET/WPF?

Windows integration would be good, but scientific/audio-acoustics libraries and exploratory numerical development are stronger in Python. Using React/Three.js also keeps the 3D interface portable.

---

## 15. Planned repository structure

Do **not** create all of these directories until implementation starts. This is the target shape.

```text
Home-Theater-Digital-Twin/
  README.md
  docs/
    PROJECT_PLAN.md
    architecture/
      ADR-0001-local-web-architecture.md
      ADR-0002-rew-as-measurement-engine.md
      ADR-0003-canonical-coordinate-system.md
    data-model.md
    rew-integration.md
  backend/
    pyproject.toml
    src/htdt/
      domain/
      storage/
      importers/
      integrations/
        rew/
        avr/
      analysis/
      simulation/
      api/
    tests/
      unit/
      integration/
      fixtures/
  frontend/
    package.json
    src/
      app/
      components/
      features/
      scene3d/
      plots/
      api/
    tests/
  sample-data/
    synthetic/
  .github/
    workflows/
```

---

## 16. UI concept

The application should feel closer to an engineering workspace than a consumer AVR setup wizard.

### Main workspace

```text
+-------------------------------------------------------------+
| Project | Session | Compare | Simulation | Settings          |
+-------------+-----------------------------------------------+
|             |                                               |
| Room tree   |              3D Room                          |
| - Speakers  |                                               |
| - Seats     |                                               |
| - Sessions  |                                               |
| - Measures  |                                               |
|             +-----------------------------------------------+
|             | Frequency / IR / comparison plot              |
+-------------+-----------------------------------------------+
| Inspector / selected-object properties                      |
+-------------------------------------------------------------+
```

### Essential interaction

Selecting a speaker in 3D should filter measurements associated with that speaker. Selecting a measurement should highlight its speaker and microphone/listening position in the room.

This cross-link between **space** and **measurement history** is the central UX value of the product.

---

## 17. Analysis views planned for MVP

### Frequency response overlay

- multiple measurements;
- configurable frequency range;
- smoothing selection for viewing only;
- raw data preserved;
- difference curve;
- selected-band statistics.

### FL/FR symmetry view

For asymmetric rooms:

- FL and FR overlay;
- absolute difference vs frequency;
- band summaries such as 20–80, 80–200, 200–500, 500–2000 Hz;
- associated speaker/wall distances.

### Before/after view

Designed specifically for cases such as YPAO OFF vs ON.

The application must not imply that a flatter graph is automatically better; it simply presents measured differences and selected metrics.

### Room-mode overlay

Show calculated axial/tangential/oblique mode candidates over the measured graph with enable/disable toggles.

### SBIR candidate overlay

From current speaker/listener boundary distances, calculate candidate cancellation frequencies and show them as hypotheses.

---

## 18. Simulation design

Simulation must be separated into model levels.

### Model L0 — geometry only

- distances;
- angles;
- speaker aiming;
- seating angles.

### Model L1 — analytical acoustics

- rectangular-room modes;
- boundary-distance SBIR candidates.

### Model L2 — geometric room acoustics

- image-source reflections;
- path lengths / arrival times;
- approximate early reflection mapping.

Use pyroomacoustics if it meets the concrete requirement when this phase begins.

### Model L3 — optimization

Search speaker/listener candidate coordinates using L1/L2 metrics and, where useful, measured-data-derived objectives.

### Not planned — wave solver

FEM/BEM/FDTD is not appropriate for an initial personal Windows tool because meshing, boundary conditions and compute requirements are far beyond the value needed for this use case.

---

## 19. Optimization approach

Do not optimize until the basic models have been validated against actual room measurements.

Potential variables:

- FL/FR distance from front wall;
- distance from side walls;
- MLP front/back movement;
- speaker toe-in;
- surround/height positions within installation constraints.

Potential objectives:

- reduce modeled low-frequency variance in a selected band;
- reduce left/right asymmetry;
- avoid predicted SBIR nulls in important bands;
- satisfy speaker-angle guidance;
- minimize movement from the current practical layout.

Start with `scipy.optimize` or grid/random search. A sophisticated evolutionary optimizer is unnecessary until objectives and constraints are proven useful.

---

## 20. Validation and test strategy

Acoustic software can generate plausible-looking but incorrect graphs. Numerical validation is therefore more important than UI test coverage.

### Unit tests

- coordinate conversion;
- room-mode formulas;
- SBIR candidate formulas;
- interpolation/resampling;
- metric calculations;
- session/revision history rules.

### Synthetic fixtures

Create analytically controlled data:

- sine response with known peaks/dips;
- simple impulse with known reflection delays;
- rectangular room with known modal frequencies;
- identical FL/FR curves where asymmetry score must be zero.

### REW fixtures

Maintain a small set of exported REW measurements generated specifically for tests.

Tests should verify:

- importer correctness;
- no unit mistakes;
- frequency/phase arrays preserve alignment;
- metadata survives round trips.

### Cross-validation

Where HTDT computes a metric REW also exposes, compare the outputs on test fixtures with documented numerical tolerances.

### Simulation validation

For image-source simulation, compare simple shoebox cases against known analytical path lengths and/or pyroomacoustics reference behavior.

---

## 21. GitHub and development workflow

Because this is a personal project, keep process lightweight.

### Branching

- `main` should remain usable.
- short feature branches for implementation work.
- PRs are useful even for a single developer when Codex/AI-generated code needs review, but not mandatory for trivial docs.

### Issues

When implementation begins, convert roadmap items into issues. Avoid creating dozens of speculative issues during planning.

### CI

Initial GitHub Actions should eventually run:

- Python formatting/lint checks;
- Python tests on Windows;
- frontend type-check/tests;
- build smoke test.

Linux CI is optional initially. Windows is authoritative.

### Dependency automation

Dependabot or Renovate is optional and can wait until dependencies stabilize.

### Release engineering

No signing/SBOM/installer work during MVP. For personal use, a zip or local startup command is acceptable. Native installer and signing are later quality-of-life work.

---

## 22. Security scope appropriate to this project

No enterprise security program is needed.

Implement only practical basics:

- local service binds to `127.0.0.1`;
- imported file size/type sanity checks;
- never execute content from imported measurement files;
- AVR network adapter only accesses explicitly discovered/configured local devices;
- project file paths are normalized before read/write operations.

Do not spend early development time on:

- login/auth;
- encryption-at-rest;
- TLS for localhost;
- role-based access control;
- secret-management platforms;
- cloud threat models.

---

## 23. Roadmap

## Phase 0 — Planning (current)

**Goal:** freeze enough decisions to prevent architecture churn.

Deliverables:

- this project plan;
- explicit scope/non-goals;
- technology decision;
- domain model draft;
- REW integration boundary;
- repository structure proposal.

No application implementation in this phase.

**Exit criteria:**

- plan reviewed;
- first real REW sample files available;
- actual room geometry can be described in the proposed coordinate system;
- unresolved decisions for MVP are limited to small library choices.

---

## v0.1 — Measurement-linked room model

**Build**

- project/room/speaker/listener domain model;
- rectangular room editor;
- speaker/listener coordinates;
- basic 3D room view;
- REW exported-data importer;
- measurement sessions and tags;
- frequency-response overlay;
- FL/FR comparison;
- YPAO OFF/ON comparison workflow;
- SQLite persistence.

**Reuse**

- React/Three.js;
- NumPy/SciPy;
- SQLite.

**Integrate**

- REW via exported data first.

**Defer**

- live REW API;
- AVR network control;
- impulse reflection matching;
- optimization;
- native desktop packaging.

**Success criterion:** a real home-theater project can be represented, multiple REW measurements can be attached to speakers/positions, and configuration changes can be compared without manually managing files.

---

## v0.2 — Acoustic reasoning

Add:

- analytical room-mode calculation;
- SBIR candidate calculation;
- measurement peak/dip detection;
- selected-band metrics;
- IR/ETC import/display;
- layout revisions;
- multiple listening positions;
- measurement history timeline.

**Success criterion:** the application begins to explain *where measured differences may come from* while clearly distinguishing measurement from hypothesis.

---

## v0.5 — REW live integration and spatial reflection model

Add:

- REW localhost API client;
- import measurements currently open in REW;
- optional REW launch/API connectivity helper;
- image-source based early-reflection candidate model;
- 3D reflection-path overlay;
- multi-seat visualizations;
- exportable comparison report.

Evaluate at this point:

- pyroomacoustics adoption;
- Plotly vs ECharts final choice;
- whether Tauri packaging is worth adding.

**Success criterion:** moving between REW and HTDT becomes a smooth workflow rather than manual export bookkeeping.

---

## v1.0 — Practical placement planning

Add only after model validation:

- constrained speaker/listener position search;
- objective comparison over candidate positions;
- angle/layout guidance;
- optional Yamaha basic-state adapter;
- optional Tauri Windows packaging;
- stable project-data migration system.

Potential later additions, outside v1.0 commitment:

- Denon/Marantz adapters;
- richer irregular-room simulation;
- AI-generated explanation reports;
- automated measurement orchestration if REW licensing/workflow makes it worthwhile.

---

## 24. MVP implementation order when coding is authorized

When implementation eventually begins, use this order:

1. Python package skeleton + frontend skeleton.
2. Domain schema and coordinate-system tests.
3. SQLite persistence.
4. Synthetic room/speaker/seat fixtures.
5. REW text export importer.
6. 2D frequency-response comparison plot.
7. 3D room view.
8. Link 3D objects to measurements.
9. Measurement session/history UI.
10. FL/FR and YPAO before/after workflows.
11. Only then add analytical room modes/SBIR.

Do **not** start with AVR networking, simulation or optimization.

---

## 25. Key architectural decisions to preserve

1. **REW is the measurement engine.**
2. **HTDT owns the digital-twin domain model and history.**
3. **Measured, derived and simulated data are separate types.**
4. **Canonical internal data is REW-independent.**
5. **`.mdat` parsing is not an MVP dependency.**
6. **Python owns numerical/acoustic logic.**
7. **React/Three.js owns interactive visualization.**
8. **SQLite is sufficient for single-user storage.**
9. **Local browser UI is preferred before desktop-shell packaging.**
10. **No cloud/security infrastructure beyond basic localhost safety.**

---

## 26. Open decisions before v0.1 implementation

These should be settled using small prototypes, not prolonged research:

### Graph library

Prototype one representative frequency-response view in both:

- Plotly.js;
- Apache ECharts.

Choose based on log-axis behavior, cursor UX, overlay performance and implementation simplicity.

### Measurement array storage

Benchmark:

- SQLite BLOB;
- `.npz` referenced by SQLite.

Use realistic REW exports before deciding.

### Irregular room representation

Decide whether v0.1 needs only a rectangular room or a simple floor-plan polygon extrusion. Avoid a general mesh editor.

### REW export fixture format

Collect actual exports from the intended REW version and define the first importer contract from real files, not assumptions.

---

## 27. References / external systems

Primary systems and libraries to consult during implementation:

- Room EQ Wizard: https://www.roomeqwizard.com/
- REW API documentation: https://www.roomeqwizard.com/help/help_en-GB/html/api.html
- pyroomacoustics: https://github.com/LCAV/pyroomacoustics
- NumPy: https://numpy.org/
- SciPy: https://scipy.org/
- Three.js: https://threejs.org/
- React Three Fiber: https://r3f.docs.pmnd.rs/
- FastAPI: https://fastapi.tiangolo.com/
- SQLite: https://www.sqlite.org/
- Tauri (future packaging candidate): https://tauri.app/

Vendor-specific AVR and speaker-layout documentation should be referenced only at the adapter/rules layer, not embedded into the core domain model.

---

## 28. Definition of the project's unique value

The project's value is **not** “better acoustic measurement than REW” and not “another room correction algorithm.”

Its value is the combination of:

> **physical room + speaker/listener geometry + real REW measurements + AVR/configuration state + history + model-based hypotheses in one persistent workspace.**

That is the design criterion for every future feature. If a proposed feature does not strengthen that link, it should usually remain in REW or another specialized tool instead of being rebuilt here.
