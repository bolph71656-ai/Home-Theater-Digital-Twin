from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .cad_measurement_repository import CadMeasurementRepository
from .cad_search import generate_cad_candidates
from .cad_search_repository import CadSearchRepository
from .cad_validation_campaign import CadValidationCampaign


class CadValidationCampaignRepository:
    """Immutable owned-room O60 preregistration storage."""

    def __init__(
        self,
        search_repository: CadSearchRepository,
        measurement_repository: CadMeasurementRepository,
    ) -> None:
        self.search_repository = search_repository
        self.measurement_repository = measurement_repository
        self.path = Path(search_repository.path)
        if Path(measurement_repository.path) != self.path:
            raise ValueError('campaign repositories must share one native CAD database')
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS cad_validation_campaigns (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    search_spec_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    candidate_set_sha256 TEXT NOT NULL,
                    campaign_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(search_spec_id) REFERENCES cad_search_specs(search_spec_id)
                );
                CREATE INDEX IF NOT EXISTS idx_validation_campaign_search_seq
                    ON cad_validation_campaigns(search_spec_id, seq ASC);
                '''
            )

    def _regenerated_candidate_ids(
        self,
        campaign: CadValidationCampaign,
    ) -> frozenset[str]:
        spec = self.search_repository.get(campaign.search_spec_id)
        if spec is None:
            raise ValueError('validation campaign SearchSpec does not exist')
        if spec.document_id != campaign.document_id:
            raise ValueError('validation campaign SearchSpec belongs to another document')
        if spec.search_spec_sha256 != campaign.search_spec_sha256:
            raise ValueError('validation campaign SearchSpec hash mismatch')

        ids: set[str] = set()
        offset = 0
        page_limit = min(1000, spec.candidate_limit)
        expected_set_sha: str | None = None
        while True:
            page = generate_cad_candidates(
                self.search_repository.scene_repository,
                spec,
                offset=offset,
                limit=page_limit,
            )
            if expected_set_sha is None:
                expected_set_sha = page.candidate_set_sha256
            elif page.candidate_set_sha256 != expected_set_sha:
                raise ValueError('regenerated candidate-set identity changed between pages')
            ids.update(candidate.candidate_id for candidate in page.candidates)
            offset += len(page.candidates)
            if not page.candidates or offset >= page.feasible_candidate_count:
                break

        if expected_set_sha is None or expected_set_sha != campaign.candidate_set_sha256:
            raise ValueError('validation campaign candidate-set hash mismatch')
        return frozenset(ids)

    def save(self, campaign: CadValidationCampaign) -> None:
        if not isinstance(campaign, CadValidationCampaign):
            raise TypeError('campaign must be CadValidationCampaign')
        campaign = CadValidationCampaign.model_validate(campaign.model_dump(mode='python'))

        candidate_ids = self._regenerated_candidate_ids(campaign)
        requested = {item.candidate_id for item in campaign.candidates}
        missing = requested - candidate_ids
        if missing:
            raise ValueError(
                f'validation campaign references candidates outside SearchSpec: {sorted(missing)}'
            )

        measured_plans = {
            plan.candidate_id
            for plan in self.measurement_repository.latest_measurement_plans(
                campaign.search_spec_id
            )
            if plan.status == 'measured'
        }
        already_measured = sorted(requested & measured_plans)
        if already_measured:
            raise ValueError(
                'validation campaign must be preregistered before candidate measurement: '
                f'{already_measured}'
            )

        with closing(self._connect()) as connection, connection:
            connection.execute(
                '''INSERT INTO cad_validation_campaigns(
                    campaign_id, document_id, search_spec_id, model_id, model_version,
                    candidate_set_sha256, campaign_sha256, payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    campaign.campaign_id,
                    campaign.document_id,
                    campaign.search_spec_id,
                    campaign.model_id,
                    campaign.model_version,
                    campaign.candidate_set_sha256,
                    campaign.campaign_sha256,
                    campaign.model_dump_json(),
                    campaign.created_at_utc,
                ),
            )

    def get(self, campaign_id: str) -> CadValidationCampaign | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_validation_campaigns WHERE campaign_id=?',
                (campaign_id,),
            ).fetchone()
        return None if row is None else CadValidationCampaign.model_validate_json(
            row['payload_json']
        )

    def find_by_sha(
        self,
        search_spec_id: str,
        campaign_sha256: str,
    ) -> CadValidationCampaign | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_validation_campaigns '
                'WHERE search_spec_id=? AND campaign_sha256=? ORDER BY seq DESC LIMIT 1',
                (search_spec_id, campaign_sha256),
            ).fetchone()
        return None if row is None else CadValidationCampaign.model_validate_json(
            row['payload_json']
        )

    def list_for_search_spec(
        self,
        search_spec_id: str,
    ) -> tuple[CadValidationCampaign, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_validation_campaigns '
                'WHERE search_spec_id=? ORDER BY seq ASC',
                (search_spec_id,),
            ).fetchall()
        return tuple(
            CadValidationCampaign.model_validate_json(row['payload_json'])
            for row in rows
        )
