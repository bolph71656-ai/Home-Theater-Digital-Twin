from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
import sqlite3

from .cad_amplifier_headroom_repository import CadAmplifierHeadroomRepository
from .cad_coverage_repository import CadCoverageRepository
from .cad_direct_level_repository import CadDirectLevelRepository
from .cad_repository import SceneRepository
from .cad_schema import ensure_native_schema
from .cad_standards_repository import CadStandardsRepository
from .cad_system_variant_repository import CadSystemVariantRepository
from .cad_topology_comparison import (
    ExactAuthorityRef,
    SystemTopologyComparisonSpec,
    TopologyComparisonEvaluation,
    TopologyComparisonSelection,
    VariantEvaluationBundle,
    amplifier_headroom_evaluation_ref,
    build_topology_comparison_selection,
    coverage_evaluation_ref,
    direct_level_evaluation_ref,
    evaluate_topology_comparison,
    standards_evaluation_ref,
)


AuthorityResolver = Callable[[str], ExactAuthorityRef | None]


class CadTopologyComparisonRepository:
    """Append-only named topology comparison persistence.

    This repository resolves exact authority hashes on every save/reopen. It has
    no method that applies a SystemVariant or changes installed/measured state.
    """

    def __init__(
        self,
        *,
        scene_repository: SceneRepository,
        system_variant_repository: CadSystemVariantRepository,
        standards_repository: CadStandardsRepository,
        coverage_repository: CadCoverageRepository | None = None,
        direct_level_repository: CadDirectLevelRepository | None = None,
        amplifier_headroom_repository: CadAmplifierHeadroomRepository | None = None,
        external_resolvers: Mapping[str, AuthorityResolver] | None = None,
    ) -> None:
        self.scene_repository = scene_repository
        self.system_variant_repository = system_variant_repository
        self.standards_repository = standards_repository
        self.coverage_repository = coverage_repository
        self.direct_level_repository = direct_level_repository
        self.amplifier_headroom_repository = amplifier_headroom_repository
        self.external_resolvers = dict(external_resolvers or {})
        self.path = Path(scene_repository.path)

        repositories = (
            ('SystemVariant', system_variant_repository),
            ('Standards', standards_repository),
            ('Coverage', coverage_repository),
            ('DirectLevel', direct_level_repository),
            ('AmplifierHeadroom', amplifier_headroom_repository),
        )
        for label, repository in repositories:
            if repository is None:
                continue
            if Path(repository.path) != self.path:
                raise ValueError(
                    f'topology comparison and {label} repositories must share '
                    'one native CAD database'
                )

        ensure_native_schema(self.path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        ensure_native_schema(self.path)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cad_topology_comparison_specs (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    comparison_id TEXT NOT NULL UNIQUE,
                    semantic_sha256 TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    scene_revision_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(scene_revision_id)
                        REFERENCES scene_revisions(revision_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topology_comparison_spec_document_seq
                    ON cad_topology_comparison_specs(document_id, seq ASC);

                CREATE TABLE IF NOT EXISTS cad_topology_comparison_bundles (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    bundle_id TEXT NOT NULL UNIQUE,
                    bundle_sha256 TEXT NOT NULL UNIQUE,
                    comparison_id TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    variant_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(comparison_id)
                        REFERENCES cad_topology_comparison_specs(comparison_id),
                    FOREIGN KEY(variant_id)
                        REFERENCES cad_system_variants(variant_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topology_comparison_bundle_spec_seq
                    ON cad_topology_comparison_bundles(comparison_id, seq ASC);

                CREATE TABLE IF NOT EXISTS cad_topology_comparison_evaluations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluation_id TEXT NOT NULL UNIQUE,
                    evaluation_sha256 TEXT NOT NULL UNIQUE,
                    comparison_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(comparison_id)
                        REFERENCES cad_topology_comparison_specs(comparison_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topology_comparison_evaluation_spec_seq
                    ON cad_topology_comparison_evaluations(comparison_id, seq ASC);

                CREATE TABLE IF NOT EXISTS cad_topology_comparison_selections (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    selection_id TEXT NOT NULL UNIQUE,
                    selection_sha256 TEXT NOT NULL UNIQUE,
                    comparison_evaluation_id TEXT NOT NULL,
                    selected_variant_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    selected_at_utc TEXT NOT NULL,
                    FOREIGN KEY(comparison_evaluation_id)
                        REFERENCES cad_topology_comparison_evaluations(evaluation_id),
                    FOREIGN KEY(selected_variant_id)
                        REFERENCES cad_system_variants(variant_id)
                );
                CREATE INDEX IF NOT EXISTS idx_topology_comparison_selection_eval_seq
                    ON cad_topology_comparison_selections(
                        comparison_evaluation_id,
                        seq ASC
                    );
                """
            )

    @staticmethod
    def _same_exact_ref(
        expected: ExactAuthorityRef,
        actual: ExactAuthorityRef,
    ) -> bool:
        return expected == actual

    def _resolve_external_ref(self, ref: ExactAuthorityRef) -> None:
        resolver = self.external_resolvers.get(ref.authority_kind)
        if resolver is None:
            raise ValueError(
                'no exact authority resolver configured for '
                f'{ref.authority_kind}'
            )
        resolved = resolver(ref.authority_id)
        if resolved is None:
            raise ValueError(
                f'{ref.authority_kind} authority does not exist: {ref.authority_id}'
            )
        if not self._same_exact_ref(ref, resolved):
            raise ValueError(
                f'{ref.authority_kind} exact authority identity/hash/version mismatch'
            )

    def _validate_spec_authorities(
        self,
        spec: SystemTopologyComparisonSpec,
    ) -> None:
        revision = self.scene_repository.get(spec.baseline_scene_revision_id)
        if revision is None:
            raise ValueError('topology comparison baseline SceneRevision does not exist')
        if (
            revision.document_id != spec.document_id
            or revision.content_hash != spec.baseline_scene_content_hash
        ):
            raise ValueError('topology comparison baseline SceneRevision hash mismatch')

        profile = self.standards_repository.get_profile(
            spec.standards_profile.profile_id,
            spec.standards_profile.profile_version,
        )
        if profile is None:
            raise ValueError('topology comparison StandardsProfile does not exist')
        if (
            profile.profile_semantic_hash
            != spec.standards_profile.profile_semantic_hash
        ):
            raise ValueError('topology comparison StandardsProfile hash mismatch')

        for candidate in spec.candidate_variants:
            variant = self.system_variant_repository.get_variant(candidate.variant_id)
            if variant is None:
                raise ValueError(
                    f'topology comparison SystemVariant does not exist: '
                    f'{candidate.variant_id}'
                )
            if variant.variant_sha256 != candidate.variant_sha256:
                raise ValueError('topology comparison SystemVariant hash mismatch')
            if (
                variant.document_id != spec.document_id
                or variant.baseline_revision_id != spec.baseline_scene_revision_id
                or variant.baseline_content_hash
                != spec.baseline_scene_content_hash
            ):
                raise ValueError(
                    'topology comparison SystemVariant baseline authority mismatch'
                )

    def save_spec(
        self,
        spec: SystemTopologyComparisonSpec,
    ) -> SystemTopologyComparisonSpec:
        spec = SystemTopologyComparisonSpec.model_validate(
            spec.model_dump(mode='python')
        )
        self._validate_spec_authorities(spec)
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_specs
                WHERE comparison_id=?
                """,
                (spec.comparison_id,),
            ).fetchone()
            if existing is not None:
                persisted = SystemTopologyComparisonSpec.model_validate_json(
                    existing['payload_json']
                )
                if persisted != spec:
                    raise ValueError(
                        'SystemTopologyComparisonSpec ID already exists with '
                        'different semantics'
                    )
                return persisted
            connection.execute(
                """
                INSERT INTO cad_topology_comparison_specs(
                    comparison_id, semantic_sha256, document_id,
                    scene_revision_id, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    spec.comparison_id,
                    spec.semantic_sha256,
                    spec.document_id,
                    spec.baseline_scene_revision_id,
                    spec.model_dump_json(),
                ),
            )
        return spec

    def get_spec(
        self,
        comparison_id: str,
    ) -> SystemTopologyComparisonSpec | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_specs
                WHERE comparison_id=?
                """,
                (comparison_id,),
            ).fetchone()
        if row is None:
            return None
        spec = SystemTopologyComparisonSpec.model_validate_json(row['payload_json'])
        self._validate_spec_authorities(spec)
        return spec

    def _resolve_bundle_ref(
        self,
        ref: ExactAuthorityRef,
        *,
        bundle: VariantEvaluationBundle,
        spec: SystemTopologyComparisonSpec,
    ) -> None:
        if ref.authority_kind == 'coverage_evaluation':
            if self.coverage_repository is None:
                self._resolve_external_ref(ref)
                return
            evaluation = self.coverage_repository.get_evaluation(ref.authority_id)
            if evaluation is None:
                raise ValueError('bundle CoverageEvaluation does not exist')
            resolved = coverage_evaluation_ref(evaluation)
            if resolved != ref:
                raise ValueError('bundle CoverageEvaluation exact authority mismatch')
            if (
                evaluation.variant_id != bundle.variant_id
                or evaluation.variant_sha256 != bundle.variant_sha256
                or evaluation.scene_revision_id != spec.baseline_scene_revision_id
                or evaluation.scene_content_hash != spec.baseline_scene_content_hash
            ):
                raise ValueError('bundle CoverageEvaluation variant/baseline mismatch')
            return

        if ref.authority_kind == 'direct_level_evaluation':
            if self.direct_level_repository is None:
                self._resolve_external_ref(ref)
                return
            evaluation = self.direct_level_repository.get_evaluation(ref.authority_id)
            if evaluation is None:
                raise ValueError('bundle DirectLevelEvaluation does not exist')
            resolved = direct_level_evaluation_ref(evaluation)
            if resolved != ref:
                raise ValueError('bundle DirectLevelEvaluation exact authority mismatch')
            if (
                evaluation.variant_id != bundle.variant_id
                or evaluation.variant_sha256 != bundle.variant_sha256
                or evaluation.scene_revision_id != spec.baseline_scene_revision_id
                or evaluation.scene_content_hash != spec.baseline_scene_content_hash
            ):
                raise ValueError('bundle DirectLevelEvaluation variant/baseline mismatch')
            return

        if ref.authority_kind == 'amplifier_headroom_evaluation':
            if self.amplifier_headroom_repository is None:
                self._resolve_external_ref(ref)
                return
            evaluation = self.amplifier_headroom_repository.get_evaluation(
                ref.authority_id
            )
            if evaluation is None:
                raise ValueError('bundle PlaybackChainEvaluation does not exist')
            resolved = amplifier_headroom_evaluation_ref(evaluation)
            if resolved != ref:
                raise ValueError(
                    'bundle PlaybackChainEvaluation exact authority mismatch'
                )
            scenario = evaluation.scenario
            if (
                scenario.document_id != spec.document_id
                or scenario.scene_revision_id != spec.baseline_scene_revision_id
                or scenario.scene_content_hash != spec.baseline_scene_content_hash
                or scenario.variant_id != bundle.variant_id
                or scenario.variant_sha256 != bundle.variant_sha256
            ):
                raise ValueError(
                    'bundle PlaybackChainEvaluation variant/baseline mismatch'
                )
            return

        if ref.authority_kind == 'standards_evaluation':
            evaluation = self.standards_repository.get_evaluation(ref.authority_id)
            if evaluation is None:
                raise ValueError('bundle StandardsEvaluation does not exist')
            resolved = standards_evaluation_ref(evaluation)
            if resolved != ref:
                raise ValueError('bundle StandardsEvaluation exact authority mismatch')
            if (
                evaluation.profile_id != spec.standards_profile.profile_id
                or evaluation.profile_version
                != spec.standards_profile.profile_version
                or evaluation.profile_semantic_hash
                != spec.standards_profile.profile_semantic_hash
            ):
                raise ValueError('bundle StandardsEvaluation profile mismatch')
            target = evaluation.target
            if (
                target.document_id != spec.document_id
                or target.scene_revision_id != spec.baseline_scene_revision_id
                or target.scene_content_hash != spec.baseline_scene_content_hash
                or target.system_variant_id != bundle.variant_id
                or target.system_variant_sha256 != bundle.variant_sha256
            ):
                raise ValueError('bundle StandardsEvaluation variant/baseline mismatch')
            return

        self._resolve_external_ref(ref)

    def _validate_bundle_authorities(
        self,
        bundle: VariantEvaluationBundle,
    ) -> SystemTopologyComparisonSpec:
        spec = self.get_spec(bundle.comparison_id)
        if spec is None:
            raise ValueError(
                'VariantEvaluationBundle references unpersisted comparison spec'
            )
        if bundle.comparison_semantic_sha256 != spec.semantic_sha256:
            raise ValueError('VariantEvaluationBundle comparison hash mismatch')

        candidate = spec.candidate(bundle.variant_id)
        if candidate.variant_sha256 != bundle.variant_sha256:
            raise ValueError('VariantEvaluationBundle SystemVariant hash mismatch')
        variant = self.system_variant_repository.get_variant(bundle.variant_id)
        if variant is None:
            raise ValueError('VariantEvaluationBundle SystemVariant does not exist')
        if variant.variant_sha256 != bundle.variant_sha256:
            raise ValueError('VariantEvaluationBundle persisted variant hash mismatch')

        for ref in bundle.all_evaluation_refs():
            self._resolve_bundle_ref(ref, bundle=bundle, spec=spec)
        return spec

    def save_bundle(
        self,
        bundle: VariantEvaluationBundle,
    ) -> VariantEvaluationBundle:
        bundle = VariantEvaluationBundle.model_validate(
            bundle.model_dump(mode='python')
        )
        self._validate_bundle_authorities(bundle)
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_bundles
                WHERE bundle_id=?
                """,
                (bundle.bundle_id,),
            ).fetchone()
            if existing is not None:
                persisted = VariantEvaluationBundle.model_validate_json(
                    existing['payload_json']
                )
                if persisted != bundle:
                    raise ValueError(
                        'VariantEvaluationBundle ID already exists with '
                        'different semantics'
                    )
                return persisted
            collision = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_bundles
                WHERE comparison_id=? AND variant_id=?
                """,
                (bundle.comparison_id, bundle.variant_id),
            ).fetchone()
            if collision is not None:
                raise ValueError(
                    'comparison already has a different bundle for SystemVariant'
                )
            connection.execute(
                """
                INSERT INTO cad_topology_comparison_bundles(
                    bundle_id, bundle_sha256, comparison_id,
                    variant_id, variant_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle.bundle_id,
                    bundle.bundle_sha256,
                    bundle.comparison_id,
                    bundle.variant_id,
                    bundle.variant_sha256,
                    bundle.model_dump_json(),
                ),
            )
        return bundle

    def get_bundle(
        self,
        bundle_id: str,
    ) -> VariantEvaluationBundle | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_bundles
                WHERE bundle_id=?
                """,
                (bundle_id,),
            ).fetchone()
        if row is None:
            return None
        bundle = VariantEvaluationBundle.model_validate_json(row['payload_json'])
        self._validate_bundle_authorities(bundle)
        return bundle

    def list_bundles(
        self,
        comparison_id: str,
    ) -> tuple[VariantEvaluationBundle, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_bundles
                WHERE comparison_id=?
                ORDER BY seq ASC
                """,
                (comparison_id,),
            ).fetchall()
        bundles = tuple(
            VariantEvaluationBundle.model_validate_json(row['payload_json'])
            for row in rows
        )
        for bundle in bundles:
            self._validate_bundle_authorities(bundle)
        return bundles

    def save_evaluation(
        self,
        evaluation: TopologyComparisonEvaluation,
    ) -> TopologyComparisonEvaluation:
        evaluation = TopologyComparisonEvaluation.model_validate(
            evaluation.model_dump(mode='python')
        )
        spec = self.get_spec(evaluation.comparison_id)
        if spec is None:
            raise ValueError(
                'TopologyComparisonEvaluation references unpersisted comparison spec'
            )
        if evaluation.comparison_semantic_sha256 != spec.semantic_sha256:
            raise ValueError('TopologyComparisonEvaluation comparison hash mismatch')

        bundles: list[VariantEvaluationBundle] = []
        for ref in evaluation.bundles:
            bundle = self.get_bundle(ref.bundle_id)
            if bundle is None:
                raise ValueError(
                    'TopologyComparisonEvaluation references unpersisted bundle'
                )
            if (
                bundle.bundle_sha256 != ref.bundle_sha256
                or bundle.variant_id != ref.variant_id
                or bundle.variant_sha256 != ref.variant_sha256
            ):
                raise ValueError('TopologyComparisonEvaluation bundle ref mismatch')
            bundles.append(bundle)

        regenerated = evaluate_topology_comparison(
            spec=spec,
            bundles=tuple(bundles),
            created_at_utc=evaluation.created_at_utc,
        )
        if regenerated != evaluation:
            raise ValueError(
                'TopologyComparisonEvaluation does not match comparison authority'
            )

        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_evaluations
                WHERE evaluation_id=?
                """,
                (evaluation.evaluation_id,),
            ).fetchone()
            if existing is not None:
                persisted = TopologyComparisonEvaluation.model_validate_json(
                    existing['payload_json']
                )
                if persisted != evaluation:
                    raise ValueError(
                        'TopologyComparisonEvaluation ID already exists with '
                        'different semantics'
                    )
                return persisted
            connection.execute(
                """
                INSERT INTO cad_topology_comparison_evaluations(
                    evaluation_id, evaluation_sha256, comparison_id,
                    payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    evaluation.evaluation_id,
                    evaluation.evaluation_sha256,
                    evaluation.comparison_id,
                    evaluation.model_dump_json(),
                    evaluation.created_at_utc,
                ),
            )
        return evaluation

    def get_evaluation(
        self,
        evaluation_id: str,
    ) -> TopologyComparisonEvaluation | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_evaluations
                WHERE evaluation_id=?
                """,
                (evaluation_id,),
            ).fetchone()
        if row is None:
            return None
        evaluation = TopologyComparisonEvaluation.model_validate_json(
            row['payload_json']
        )
        spec = self.get_spec(evaluation.comparison_id)
        if spec is None:
            raise ValueError('comparison evaluation spec disappeared')
        bundles = tuple(
            self.get_bundle(ref.bundle_id)
            for ref in evaluation.bundles
        )
        if any(item is None for item in bundles):
            raise ValueError('comparison evaluation bundle disappeared')
        regenerated = evaluate_topology_comparison(
            spec=spec,
            bundles=tuple(item for item in bundles if item is not None),
            created_at_utc=evaluation.created_at_utc,
        )
        if regenerated != evaluation:
            raise ValueError('persisted comparison evaluation no longer resolves exactly')
        return evaluation

    def save_selection(
        self,
        selection: TopologyComparisonSelection,
    ) -> TopologyComparisonSelection:
        selection = TopologyComparisonSelection.model_validate(
            selection.model_dump(mode='python')
        )
        evaluation = self.get_evaluation(selection.comparison_evaluation_id)
        if evaluation is None:
            raise ValueError(
                'TopologyComparisonSelection references unpersisted evaluation'
            )
        if evaluation.evaluation_sha256 != selection.comparison_evaluation_sha256:
            raise ValueError('TopologyComparisonSelection evaluation hash mismatch')
        spec = self.get_spec(evaluation.comparison_id)
        if spec is None:
            raise ValueError('TopologyComparisonSelection comparison spec disappeared')
        regenerated = build_topology_comparison_selection(
            spec=spec,
            evaluation=evaluation,
            selected_variant_id=selection.selected_variant_id,
            selected_by=selection.selected_by,
            selected_at_utc=selection.selected_at_utc,
            rationale=selection.rationale,
        )
        if regenerated != selection:
            raise ValueError(
                'TopologyComparisonSelection does not match selection authority'
            )

        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_selections
                WHERE selection_id=?
                """,
                (selection.selection_id,),
            ).fetchone()
            if existing is not None:
                persisted = TopologyComparisonSelection.model_validate_json(
                    existing['payload_json']
                )
                if persisted != selection:
                    raise ValueError(
                        'TopologyComparisonSelection ID already exists with '
                        'different semantics'
                    )
                return persisted
            connection.execute(
                """
                INSERT INTO cad_topology_comparison_selections(
                    selection_id, selection_sha256,
                    comparison_evaluation_id, selected_variant_id,
                    payload_json, selected_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    selection.selection_id,
                    selection.selection_sha256,
                    selection.comparison_evaluation_id,
                    selection.selected_variant_id,
                    selection.model_dump_json(),
                    selection.selected_at_utc,
                ),
            )
        return selection

    def get_selection(
        self,
        selection_id: str,
    ) -> TopologyComparisonSelection | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_topology_comparison_selections
                WHERE selection_id=?
                """,
                (selection_id,),
            ).fetchone()
        if row is None:
            return None
        selection = TopologyComparisonSelection.model_validate_json(
            row['payload_json']
        )
        evaluation = self.get_evaluation(selection.comparison_evaluation_id)
        if evaluation is None:
            raise ValueError('comparison selection evaluation disappeared')
        spec = self.get_spec(evaluation.comparison_id)
        if spec is None:
            raise ValueError('comparison selection spec disappeared')
        regenerated = build_topology_comparison_selection(
            spec=spec,
            evaluation=evaluation,
            selected_variant_id=selection.selected_variant_id,
            selected_by=selection.selected_by,
            selected_at_utc=selection.selected_at_utc,
            rationale=selection.rationale,
        )
        if regenerated != selection:
            raise ValueError('persisted topology selection no longer resolves exactly')
        return selection
