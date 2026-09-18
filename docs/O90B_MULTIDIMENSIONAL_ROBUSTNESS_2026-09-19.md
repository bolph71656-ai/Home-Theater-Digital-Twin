# O90B — Multidimensional robustness / robust Pareto implementation

Date: 2026-09-19  
Tracking: #140, #146

## Implemented scope

O90B extends the merged O90A authority without introducing a parallel robustness truth source.

Implemented:

- deterministic multidimensional bounded perturbation sampling;
- fixed spec + seed -> reproducible sample identity and ordering;
- bounded multi-axis combinations with explicit negative/positive corner anchors plus deterministic interior design points;
- explicit linked perturbation groups using a shared normalized coordinate and per-axis multipliers;
- complete feasible / infeasible / failed sample retention;
- G10 and O80 hard-constraint reevaluation for every multidimensional sample;
- per-objective finite sampled envelope;
- feasible fraction;
- explicit `sampled_worst` semantics;
- O40-compatible Pareto vectors that keep nominal objectives and robustness sampled-worst objectives as separate dimensions;
- exact SceneRevision / SearchSpec / candidate / O30 objective / model / sampling provenance;
- persistence through the existing `CadRobustnessRepository`;
- replay from the same spec / seed.

## Authority boundaries

O90A remains the base authority for:

- `RobustnessSpec`;
- `UncertaintyAxis`;
- `PerturbationSample`;
- `RobustnessEvaluation`;
- candidate / SceneRevision / O30 provenance;
- SQLite append-only robustness persistence.

O90B extends those models in a backward-compatible way. O90A semantic hashes do not include O90B-only fields, so existing O90A persisted evidence keeps its identity.

O90B does not replace:

- O30 objective vectors;
- O40 Pareto dominance;
- G10 geometric hard constraints;
- O80 orientation / physical-yaw rejection authority;
- O70 residual/model uncertainty semantics.

The robust Pareto helper creates explicit dimensions named `nominal::<objective>` and `robust.sampled_worst::<objective>`, then delegates dominance to the existing O40 `pareto_front()`. No aggregate robustness score is introduced.

## Sampling semantics

The implemented O90B sampler is a finite deterministic bounded design.

Important semantics:

- `± tolerance` remains a bounded interval, not an inferred probability distribution;
- a linked group means axes share one deterministic normalized design coordinate with explicit multipliers;
- linked groups do not assert a statistical correlation coefficient or probability model;
- bounded-only sampling does not produce percentiles or probabilities;
- finite extrema are reported as `sampled_worst`, `sampled_min`, and `sampled_max`; they are not called true worst-case;
- infeasible samples remain stored as evidence and do not receive objective scores;
- feasible fraction counts hard-constraint feasibility over the exact finite design;
- objective envelopes use only scored feasible samples while the full sample set, infeasible IDs, and failed IDs remain attached to the evaluation.

## Provenance

A multidimensional `RobustnessSpec` carries:

- exact O90A parent spec ID/hash;
- exact SceneRevision and scene content hash;
- SearchSpec ID/hash and candidate-set hash;
- exact candidate payload/hash;
- nominal O30 evaluation ID/hash and evaluation-spec hash;
- model ID/version, prediction provider, fidelity;
- bounded axes;
- sampling strategy / algorithm version;
- seed and sample count;
- linked-group definition;
- software version.

Each sample additionally stores its exact parameter deltas, perturbed scene hash, G10 results, O80 rejection IDs, domain rejection IDs, prediction ref when scored, and objective vector when scored.

Each multidimensional evaluation stores a sampling-provenance hash that includes the exact ordered sample IDs and model/objective/sampling authority.

## Validation added

Focused tests cover:

- deterministic replay for identical spec / seed;
- deterministic linked-axis behavior;
- multi-axis sample construction;
- G10 and O80 reevaluation for every sample;
- retention of infeasible evidence;
- sampled envelope and feasible fraction;
- absence of fabricated bounded-interval percentiles;
- existing SQLite persistence round-trip;
- nominal vs sampled-worst Pareto dimensions through O40.

No GUI, UX shell, O100, or RDC work is included.

## Remaining work

Not implemented in this slice:

- explicit probabilistic/distribution uncertainty models and probability/percentile outputs;
- empirical/discrete uncertainty authorities beyond bounded O90B sampling;
- O90C multi-fidelity screening/refinement and scheduler/cache acceleration;
- O90D UX / 3D overlays;
- O90E owned-room robustness validation.

Any future probabilistic output must be gated by an explicit probabilistic uncertainty model and must not be inferred from bounded tolerance alone.
