from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Callable

from .rew_api import (
    RewApiClient,
    RewRoomSimFrequencyResponse,
    RewRoomSimSnapshot,
    htdt_position_to_roomsim,
)


ROOMSIM_MODEL_ID = 'rew-room-simulator-rectangular-v1'
ROOMSIM_TRANSACTION_VERSION = 'rew-roomsim-transaction-1'


class RewRoomSimTransactionError(RuntimeError):
    pass


class RewRoomSimCancelled(RewRoomSimTransactionError):
    pass


class RewRoomSimRestoreError(RewRoomSimTransactionError):
    pass


@dataclass(frozen=True)
class RewRoomSimMutation:
    room_size_htdt: dict[str, float] | None = None
    active_sources: tuple[str, ...] | None = None
    head_position_htdt: dict[str, float] | None = None
    source_positions_htdt: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class RewRoomSimTransactionResult:
    model_id: str
    transaction_version: str
    baseline_snapshot: RewRoomSimSnapshot
    applied_snapshot: RewRoomSimSnapshot
    response: RewRoomSimFrequencyResponse
    baseline_sha256: str
    applied_sha256: str
    restored_sha256: str


def roomsim_snapshot_payload(snapshot: RewRoomSimSnapshot) -> dict[str, object]:
    return RewApiClient.roomsim_snapshot_payload(snapshot)


def canonical_roomsim_snapshot(snapshot: RewRoomSimSnapshot) -> str:
    return json.dumps(
        roomsim_snapshot_payload(snapshot),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )


def roomsim_snapshot_sha256(snapshot: RewRoomSimSnapshot) -> str:
    return sha256(canonical_roomsim_snapshot(snapshot).encode('utf-8')).hexdigest()


def _finite_position(position: dict[str, float], *, label: str) -> None:
    expected = {'x_m', 'y_m', 'z_m'}
    if set(position) != expected:
        raise ValueError(f'{label} must contain exactly x_m, y_m and z_m')
    if any(not isinstance(position[name], (int, float)) or not math.isfinite(float(position[name])) for name in expected):
        raise ValueError(f'{label} contains a non-finite coordinate')


def _room_size_payload(room_size_htdt: dict[str, float]) -> dict[str, float | str]:
    expected = {'width_m', 'depth_m', 'height_m'}
    if set(room_size_htdt) != expected:
        raise ValueError('room_size_htdt must contain exactly width_m, depth_m and height_m')
    values = {key: float(room_size_htdt[key]) for key in expected}
    if any(not math.isfinite(value) or value <= 0 for value in values.values()):
        raise ValueError('room_size_htdt dimensions must be finite and positive')
    return {
        'unit': 'metres',
        'length': values['depth_m'],
        'width': values['width_m'],
        'height': values['height_m'],
    }


def _same_position(actual: dict[str, float], expected: dict[str, float], *, tolerance: float = 1e-9) -> bool:
    return all(abs(float(actual[name]) - float(expected[name])) <= tolerance for name in ('x_m', 'y_m', 'z_m'))


class RewRoomSimTransaction:
    def __init__(self, client: RewApiClient) -> None:
        self.client = client

    def _validate_mutation(self, baseline: RewRoomSimSnapshot, mutation: RewRoomSimMutation) -> None:
        target_sources = mutation.active_sources if mutation.active_sources is not None else baseline.active_sources
        if not target_sources:
            raise ValueError('Room Simulator transaction requires at least one active source')
        if mutation.active_sources is not None:
            if len(target_sources) != len(set(target_sources)):
                raise ValueError('active_sources must be unique')
            introduced = set(target_sources) - set(baseline.active_sources)
            if introduced:
                raise ValueError(
                    'Initial S01 transaction may only select a subset of sources active in the baseline: '
                    + ', '.join(sorted(introduced))
                )
        if mutation.head_position_htdt is not None:
            _finite_position(mutation.head_position_htdt, label='head_position_htdt')
        for source_name, position in mutation.source_positions_htdt.items():
            if source_name not in target_sources:
                raise ValueError(f'Source position mutation requires active source: {source_name}')
            if source_name not in baseline.sources:
                raise ValueError(f'Source is not restorable from the baseline snapshot: {source_name}')
            _finite_position(position, label=f'source_positions_htdt[{source_name}]')
        if mutation.room_size_htdt is not None:
            _room_size_payload(mutation.room_size_htdt)

    def _target_room_depth(self, baseline: RewRoomSimSnapshot, mutation: RewRoomSimMutation) -> float:
        if mutation.room_size_htdt is not None:
            return float(mutation.room_size_htdt['depth_m'])
        return float(baseline.room_size['length'])

    def _apply(self, baseline: RewRoomSimSnapshot, mutation: RewRoomSimMutation) -> None:
        if mutation.room_size_htdt is not None:
            self.client.set_roomsim_room_size(_room_size_payload(mutation.room_size_htdt))
        if mutation.active_sources is not None:
            self.client.set_roomsim_sources(mutation.active_sources)
        target_depth = self._target_room_depth(baseline, mutation)
        if mutation.head_position_htdt is not None:
            self.client.set_roomsim_head_position(
                htdt_position_to_roomsim(target_depth, mutation.head_position_htdt)
            )
        for source_name in sorted(mutation.source_positions_htdt):
            self.client.set_roomsim_source_position(
                source_name,
                htdt_position_to_roomsim(target_depth, mutation.source_positions_htdt[source_name]),
            )

    def _verify_applied(
        self,
        baseline: RewRoomSimSnapshot,
        applied: RewRoomSimSnapshot,
        mutation: RewRoomSimMutation,
    ) -> None:
        if mutation.room_size_htdt is not None:
            expected = _room_size_payload(mutation.room_size_htdt)
            if any(abs(float(applied.room_size[name]) - float(expected[name])) > 1e-9 for name in ('length', 'width', 'height')):
                raise RewRoomSimTransactionError('REW Room Simulator room size did not match the requested mutation')
        if mutation.active_sources is not None and tuple(applied.active_sources) != tuple(mutation.active_sources):
            raise RewRoomSimTransactionError('REW Room Simulator active sources did not match the requested mutation')
        if mutation.head_position_htdt is not None and not _same_position(applied.head_position_htdt, mutation.head_position_htdt):
            raise RewRoomSimTransactionError('REW Room Simulator head position did not match the requested mutation')
        for source_name, expected in mutation.source_positions_htdt.items():
            actual = applied.sources.get(source_name, {}).get('position_htdt')
            if not isinstance(actual, dict) or not _same_position(actual, expected):
                raise RewRoomSimTransactionError(f'REW Room Simulator source position did not match: {source_name}')

    def _restore(self, baseline: RewRoomSimSnapshot) -> RewRoomSimSnapshot:
        self.client.set_roomsim_room_size(dict(baseline.room_size))
        self.client.set_roomsim_sources(baseline.active_sources)
        room_depth = float(baseline.room_size['length'])
        self.client.set_roomsim_head_position(
            htdt_position_to_roomsim(room_depth, baseline.head_position_htdt)
        )
        for source_name in baseline.active_sources:
            source = baseline.sources[source_name]
            position = source.get('position_htdt')
            if not isinstance(position, dict):
                raise RewRoomSimRestoreError(f'Baseline source position is unavailable: {source_name}')
            self.client.set_roomsim_source_position(
                source_name,
                htdt_position_to_roomsim(room_depth, position),
            )
        return self.client.get_roomsim_snapshot()

    def run(
        self,
        mutation: RewRoomSimMutation,
        *,
        mic_position: str = 'Main',
        source_name: str | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> RewRoomSimTransactionResult:
        baseline = self.client.get_roomsim_snapshot()
        self._validate_mutation(baseline, mutation)
        baseline_hash = roomsim_snapshot_sha256(baseline)

        primary_error: BaseException | None = None
        applied: RewRoomSimSnapshot | None = None
        response: RewRoomSimFrequencyResponse | None = None
        try:
            if cancelled is not None and cancelled():
                raise RewRoomSimCancelled('Room Simulator transaction cancelled before mutation')
            self._apply(baseline, mutation)
            applied = self.client.get_roomsim_snapshot()
            self._verify_applied(baseline, applied, mutation)
            if cancelled is not None and cancelled():
                raise RewRoomSimCancelled('Room Simulator transaction cancelled after mutation')
            response = self.client.get_roomsim_frequency_response(
                mic_position=mic_position,
                source_name=source_name,
            )
        except BaseException as exc:
            primary_error = exc

        try:
            restored = self._restore(baseline)
            restored_hash = roomsim_snapshot_sha256(restored)
            if restored_hash != baseline_hash:
                raise RewRoomSimRestoreError(
                    f'Room Simulator restore verification failed: expected {baseline_hash}, got {restored_hash}'
                )
        except BaseException as restore_exc:
            if isinstance(restore_exc, RewRoomSimRestoreError):
                raise restore_exc from primary_error
            raise RewRoomSimRestoreError('Room Simulator restore failed') from restore_exc

        if primary_error is not None:
            raise primary_error
        if applied is None or response is None:
            raise RewRoomSimTransactionError('Room Simulator transaction did not produce a response')

        return RewRoomSimTransactionResult(
            model_id=ROOMSIM_MODEL_ID,
            transaction_version=ROOMSIM_TRANSACTION_VERSION,
            baseline_snapshot=baseline,
            applied_snapshot=applied,
            response=response,
            baseline_sha256=baseline_hash,
            applied_sha256=roomsim_snapshot_sha256(applied),
            restored_sha256=restored_hash,
        )
