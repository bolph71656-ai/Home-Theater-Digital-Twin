from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .optimization_robustness import (
    PerturbationSample,
    RobustnessEvaluation,
    RobustnessSpec,
)


class CadRobustnessRepository:
    """Append-only SQLite persistence for O90A authority and evidence."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cad_robustness_specs (
                    robustness_spec_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    scene_revision_id TEXT NOT NULL,
                    scene_content_hash TEXT NOT NULL,
                    search_spec_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    nominal_objective_evaluation_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    robustness_spec_sha256 TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cad_robustness_specs_candidate
                    ON cad_robustness_specs(
                        document_id,
                        scene_revision_id,
                        candidate_id,
                        created_at_utc
                    );

                CREATE TABLE IF NOT EXISTS cad_perturbation_samples (
                    sample_id TEXT PRIMARY KEY,
                    robustness_spec_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    sample_index INTEGER NOT NULL,
                    feasible INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    sample_sha256 TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(robustness_spec_id, sample_index),
                    FOREIGN KEY(robustness_spec_id)
                        REFERENCES cad_robustness_specs(robustness_spec_id)
                        ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_cad_perturbation_samples_spec
                    ON cad_perturbation_samples(
                        robustness_spec_id,
                        sample_index
                    );

                CREATE TABLE IF NOT EXISTS cad_robustness_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    robustness_spec_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    objective_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evaluation_sha256 TEXT NOT NULL UNIQUE,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(robustness_spec_id, objective_id),
                    FOREIGN KEY(robustness_spec_id)
                        REFERENCES cad_robustness_specs(robustness_spec_id)
                        ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_cad_robustness_evaluations_spec
                    ON cad_robustness_evaluations(
                        robustness_spec_id,
                        objective_id
                    );
                """
            )

    @staticmethod
    def _payload(model: Any) -> str:
        return json.dumps(
            model.model_dump(mode='json'),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        )

    @staticmethod
    def _same_payload(existing: str, incoming: str, *, label: str) -> None:
        if existing != incoming:
            raise ValueError(f'{label} immutable identity conflict')

    def save_spec(self, spec: RobustnessSpec) -> RobustnessSpec:
        payload = self._payload(spec)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_robustness_specs
                WHERE robustness_spec_id = ?
                """,
                (spec.robustness_spec_id,),
            ).fetchone()
            if row is not None:
                existing = RobustnessSpec.model_validate_json(
                    str(row['payload_json'])
                )
                if (
                    existing.robustness_spec_sha256
                    != spec.robustness_spec_sha256
                ):
                    raise ValueError('RobustnessSpec immutable identity conflict')
                return existing
            connection.execute(
                """
                INSERT INTO cad_robustness_specs (
                    robustness_spec_id,
                    document_id,
                    scene_revision_id,
                    scene_content_hash,
                    search_spec_id,
                    candidate_id,
                    nominal_objective_evaluation_id,
                    model_id,
                    model_version,
                    payload_json,
                    robustness_spec_sha256,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec.robustness_spec_id,
                    spec.document_id,
                    spec.scene_revision_id,
                    spec.scene_content_hash,
                    spec.search_spec_id,
                    spec.candidate_id,
                    spec.nominal_objective_evaluation_id,
                    spec.model_id,
                    spec.model_version,
                    payload,
                    spec.robustness_spec_sha256,
                    spec.created_at_utc,
                ),
            )
        return spec

    def get_spec(self, robustness_spec_id: str) -> RobustnessSpec:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_robustness_specs
                WHERE robustness_spec_id = ?
                """,
                (robustness_spec_id,),
            ).fetchone()
        if row is None:
            raise KeyError(robustness_spec_id)
        return RobustnessSpec.model_validate_json(str(row['payload_json']))

    def save_sample(self, sample: PerturbationSample) -> PerturbationSample:
        self.get_spec(sample.robustness_spec_id)
        payload = self._payload(sample)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_perturbation_samples
                WHERE sample_id = ?
                """,
                (sample.sample_id,),
            ).fetchone()
            if row is not None:
                existing = PerturbationSample.model_validate_json(
                    str(row['payload_json'])
                )
                if existing.sample_sha256 != sample.sample_sha256:
                    raise ValueError('PerturbationSample immutable identity conflict')
                return existing
            connection.execute(
                """
                INSERT INTO cad_perturbation_samples (
                    sample_id,
                    robustness_spec_id,
                    candidate_id,
                    sample_index,
                    feasible,
                    payload_json,
                    sample_sha256,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample.sample_id,
                    sample.robustness_spec_id,
                    sample.candidate_id,
                    sample.sample_index,
                    int(sample.feasible),
                    payload,
                    sample.sample_sha256,
                    sample.created_at_utc,
                ),
            )
        return sample

    def save_samples(
        self,
        samples: tuple[PerturbationSample, ...],
    ) -> tuple[PerturbationSample, ...]:
        for sample in samples:
            self.save_sample(sample)
        return samples

    def list_samples(
        self,
        robustness_spec_id: str,
    ) -> tuple[PerturbationSample, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM cad_perturbation_samples
                WHERE robustness_spec_id = ?
                ORDER BY sample_index ASC
                """,
                (robustness_spec_id,),
            ).fetchall()
        return tuple(
            PerturbationSample.model_validate_json(str(row['payload_json']))
            for row in rows
        )

    def list_reusable_samples(
        self,
        spec: RobustnessSpec,
    ) -> tuple[PerturbationSample, ...]:
        """Return cache evidence only for the exact immutable O90 spec."""

        persisted = self.get_spec(spec.robustness_spec_id)
        if persisted.robustness_spec_sha256 != spec.robustness_spec_sha256:
            raise ValueError('robustness cache spec identity mismatch')
        samples = self.list_samples(spec.robustness_spec_id)
        if any(
            sample.robustness_spec_sha256 != spec.robustness_spec_sha256
            or sample.candidate_id != spec.candidate_id
            or sample.model_id != spec.model_id
            or sample.model_version != spec.model_version
            or sample.prediction_provider_id != spec.prediction_provider_id
            or sample.objective_evaluation_spec_sha256
            != spec.objective_evaluation_spec_sha256
            for sample in samples
        ):
            raise ValueError('robustness cache contains stale sample evidence')
        return samples

    def save_evaluation(
        self,
        evaluation: RobustnessEvaluation,
    ) -> RobustnessEvaluation:
        self.get_spec(evaluation.robustness_spec_id)
        payload = self._payload(evaluation)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_robustness_evaluations
                WHERE evaluation_id = ?
                """,
                (evaluation.evaluation_id,),
            ).fetchone()
            if row is not None:
                existing = RobustnessEvaluation.model_validate_json(
                    str(row['payload_json'])
                )
                if existing.evaluation_sha256 != evaluation.evaluation_sha256:
                    raise ValueError('RobustnessEvaluation immutable identity conflict')
                return existing
            connection.execute(
                """
                INSERT INTO cad_robustness_evaluations (
                    evaluation_id,
                    robustness_spec_id,
                    candidate_id,
                    objective_id,
                    payload_json,
                    evaluation_sha256,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.evaluation_id,
                    evaluation.robustness_spec_id,
                    evaluation.candidate_id,
                    evaluation.objective_id,
                    payload,
                    evaluation.evaluation_sha256,
                    evaluation.created_at_utc,
                ),
            )
        return evaluation

    def save_evaluations(
        self,
        evaluations: tuple[RobustnessEvaluation, ...],
    ) -> tuple[RobustnessEvaluation, ...]:
        for evaluation in evaluations:
            self.save_evaluation(evaluation)
        return evaluations

    def list_evaluations(
        self,
        robustness_spec_id: str,
    ) -> tuple[RobustnessEvaluation, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM cad_robustness_evaluations
                WHERE robustness_spec_id = ?
                ORDER BY objective_id ASC
                """,
                (robustness_spec_id,),
            ).fetchall()
        return tuple(
            RobustnessEvaluation.model_validate_json(str(row['payload_json']))
            for row in rows
        )

    def list_specs_for_candidate(
        self,
        *,
        document_id: str,
        scene_revision_id: str,
        candidate_id: str,
    ) -> tuple[RobustnessSpec, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM cad_robustness_specs
                WHERE document_id = ?
                  AND scene_revision_id = ?
                  AND candidate_id = ?
                ORDER BY created_at_utc ASC, robustness_spec_id ASC
                """,
                (document_id, scene_revision_id, candidate_id),
            ).fetchall()
        return tuple(
            RobustnessSpec.model_validate_json(str(row['payload_json']))
            for row in rows
        )
