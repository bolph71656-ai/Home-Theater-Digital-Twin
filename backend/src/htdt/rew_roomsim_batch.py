from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping, Protocol
from urllib.parse import quote
from urllib.request import Request

from .rew_api import (
    ROOMSIM_ADAPTER_VERSION,
    RewApiClient,
    RewApiError,
    RewApiUnavailable,
    RewRoomSimFrequencyResponse,
    RewRoomSimSnapshot,
    htdt_position_to_roomsim,
)


ROOMSIM_BATCH_ADAPTER_VERSION = 'rew-roomsim-position-batch-1'
ROOMSIM_MODEL_ID = 'rew-room-simulator'


class RewRoomSimBatchError(RuntimeError):
    pass


class RewRoomSimConcurrentChange(RewRoomSimBatchError):
    pass


class RewRoomSimRestoreError(RewRoomSimBatchError):
    pass


@dataclass(frozen=True)
class RewRoomSimPositionBatchRequest:
    candidate_id: str
    head_position_htdt: Mapping[str, float]
    source_positions_htdt: Mapping[str, Mapping[str, float]]
    mic_position: str = 'Main'
    source_name: str | None = None


@dataclass(frozen=True)
class RewRoomSimPositionBatchResult:
    candidate_id: str
    model_id: str
    model_version: str
    adapter_version: str
    pre_state_sha256: str
    applied_state_sha256: str
    restored_state_sha256: str
    response: RewRoomSimFrequencyResponse


class RoomSimPositionControl(Protocol):
    def get_roomsim_snapshot(self) -> RewRoomSimSnapshot: ...
    def get_roomsim_frequency_response(
        self,
        *,
        mic_position: str = 'Main',
        source_name: str | None = None,
    ) -> RewRoomSimFrequencyResponse: ...
    def set_roomsim_head_position(self, position_rew: Mapping[str, Any]) -> None: ...
    def set_roomsim_source_position(self, source_name: str, position_rew: Mapping[str, Any]) -> None: ...


class RewRoomSimControlClient(RewApiClient):
    """Explicit write-capable Room Simulator client.

    The regular RewApiClient remains GET-only by convention. This subclass is
    used only by the transactional O20 batch driver below.
    """

    def _post_json(self, path: str, payload: Any) -> Any:
        raw_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
        request = Request(
            f'{self.base_url}{path}',
            data=raw_payload,
            headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with self._opener(request, timeout=self.timeout_s) as response:
                raw = response.read()
        except (OSError, TimeoutError) as exc:
            raise RewApiUnavailable(str(exc)) from exc
        if not raw:
            return None
        try:
            return json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RewApiError('REW returned invalid JSON after Room Simulator update') from exc

    def set_roomsim_head_position(self, position_rew: Mapping[str, Any]) -> None:
        self._post_json('/roomsim/head-position', dict(position_rew))

    def set_roomsim_source_position(self, source_name: str, position_rew: Mapping[str, Any]) -> None:
        self._post_json(
            f'/roomsim/{quote(source_name, safe="")}/position',
            dict(position_rew),
        )


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def roomsim_state_payload(snapshot: RewRoomSimSnapshot) -> dict[str, Any]:
    return asdict(snapshot)


def roomsim_state_sha256(snapshot: RewRoomSimSnapshot) -> str:
    return sha256(_canonical_json(roomsim_state_payload(snapshot)).encode('utf-8')).hexdigest()


def _position(position: Mapping[str, Any]) -> dict[str, float]:
    try:
        result = {
            'x_m': float(position['x_m']),
            'y_m': float(position['y_m']),
            'z_m': float(position['z_m']),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise RewRoomSimBatchError('HTDT position requires numeric x_m/y_m/z_m') from exc
    if not all(isfinite(value) for value in result.values()):
        raise RewRoomSimBatchError('HTDT position must be finite')
    return result


def _expected_applied_snapshot(
    before: RewRoomSimSnapshot,
    request: RewRoomSimPositionBatchRequest,
) -> RewRoomSimSnapshot:
    payload = deepcopy(roomsim_state_payload(before))
    room_depth = float(before.room_size['length'])
    head_htdt = _position(request.head_position_htdt)
    payload['head_position_htdt'] = head_htdt
    payload['head_position_rew'] = htdt_position_to_roomsim(room_depth, head_htdt)

    for source_name, position in request.source_positions_htdt.items():
        if source_name not in before.active_sources:
            raise RewRoomSimBatchError(f'Room Simulator source is not active: {source_name}')
        source_htdt = _position(position)
        payload['sources'][source_name]['position_htdt'] = source_htdt
        payload['sources'][source_name]['position_rew'] = htdt_position_to_roomsim(
            room_depth,
            source_htdt,
        )
    return RewRoomSimSnapshot(**payload)


def _same_position(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _canonical_json(dict(left)) == _canonical_json(dict(right))


def _safe_restore(
    control: RoomSimPositionControl,
    before: RewRoomSimSnapshot,
    owned: RewRoomSimSnapshot,
) -> None:
    """Restore only fields still equal to the last state observed after our writes.

    This also restores source-position side effects (for example paired movement)
    while refusing to overwrite a field that changed again after our observation.
    """

    current = control.get_roomsim_snapshot()
    conflicts: list[str] = []

    source_names = tuple(sorted(set(before.active_sources) | set(owned.active_sources)))
    for source_name in source_names:
        if source_name not in before.sources or source_name not in owned.sources or source_name not in current.sources:
            conflicts.append(f'source-set:{source_name}')
            continue
        before_position = before.sources[source_name]['position_rew']
        owned_position = owned.sources[source_name]['position_rew']
        current_position = current.sources[source_name]['position_rew']
        if _same_position(owned_position, before_position):
            if not _same_position(current_position, before_position):
                conflicts.append(f'source:{source_name}')
            continue
        if _same_position(current_position, owned_position):
            control.set_roomsim_source_position(source_name, before_position)
        elif not _same_position(current_position, before_position):
            conflicts.append(f'source:{source_name}')
        current = control.get_roomsim_snapshot()

    if not _same_position(owned.head_position_rew, before.head_position_rew):
        if _same_position(current.head_position_rew, owned.head_position_rew):
            control.set_roomsim_head_position(before.head_position_rew)
        elif not _same_position(current.head_position_rew, before.head_position_rew):
            conflicts.append('head')
    elif not _same_position(current.head_position_rew, before.head_position_rew):
        conflicts.append('head')

    final = control.get_roomsim_snapshot()
    if conflicts:
        raise RewRoomSimConcurrentChange(
            'Room Simulator state changed externally during transaction: ' + ', '.join(conflicts)
        )
    if roomsim_state_sha256(final) != roomsim_state_sha256(before):
        raise RewRoomSimConcurrentChange(
            'Room Simulator non-position state changed during transaction; '
            'position changes were restored without overwriting that external state'
        )

def run_roomsim_position_batch(
    control: RoomSimPositionControl,
    request: RewRoomSimPositionBatchRequest,
) -> RewRoomSimPositionBatchResult:
    if not request.candidate_id:
        raise RewRoomSimBatchError('candidate_id must not be empty')

    before = control.get_roomsim_snapshot()
    pre_hash = roomsim_state_sha256(before)
    intended = _expected_applied_snapshot(before, request)
    intended_hash = roomsim_state_sha256(intended)

    # A second full snapshot immediately before the first write catches ordinary
    # user edits between preparation and transaction entry. REW has no CAS API,
    # so every later phase also verifies the complete state.
    if roomsim_state_sha256(control.get_roomsim_snapshot()) != pre_hash:
        raise RewRoomSimConcurrentChange('Room Simulator state changed before candidate apply')

    room_depth = float(before.room_size['length'])
    owned = before
    response: RewRoomSimFrequencyResponse | None = None
    transaction_error: BaseException | None = None

    try:
        for source_name in sorted(request.source_positions_htdt):
            if roomsim_state_sha256(control.get_roomsim_snapshot()) != roomsim_state_sha256(owned):
                raise RewRoomSimConcurrentChange(
                    'Room Simulator state changed before a source position update'
                )
            control.set_roomsim_source_position(
                source_name,
                htdt_position_to_roomsim(
                    room_depth,
                    _position(request.source_positions_htdt[source_name]),
                ),
            )
            owned = control.get_roomsim_snapshot()

        if roomsim_state_sha256(control.get_roomsim_snapshot()) != roomsim_state_sha256(owned):
            raise RewRoomSimConcurrentChange(
                'Room Simulator state changed before the head position update'
            )
        control.set_roomsim_head_position(
            htdt_position_to_roomsim(room_depth, _position(request.head_position_htdt))
        )
        owned = control.get_roomsim_snapshot()

        if roomsim_state_sha256(owned) != intended_hash:
            raise RewRoomSimConcurrentChange(
                'Room Simulator state does not match the exact candidate state after apply'
            )

        response = control.get_roomsim_frequency_response(
            mic_position=request.mic_position,
            source_name=request.source_name,
        )

        if roomsim_state_sha256(control.get_roomsim_snapshot()) != roomsim_state_sha256(owned):
            raise RewRoomSimConcurrentChange(
                'Room Simulator state changed while candidate response was being read'
            )
    except BaseException as exc:
        transaction_error = exc

    restore_error: BaseException | None = None
    try:
        _safe_restore(
            control,
            before,
            owned,
        )
    except BaseException as exc:
        restore_error = exc

    if restore_error is not None:
        if transaction_error is not None:
            raise RewRoomSimRestoreError(
                f'Room Simulator transaction failed and restore was not clean: '
                f'{transaction_error}; restore={restore_error}'
            ) from restore_error
        raise restore_error
    if transaction_error is not None:
        raise transaction_error
    if response is None:
        raise RewRoomSimBatchError('Room Simulator transaction completed without a response')

    restored = control.get_roomsim_snapshot()
    restored_hash = roomsim_state_sha256(restored)
    if restored_hash != pre_hash:
        raise RewRoomSimRestoreError('Room Simulator final state hash differs from the pre-state hash')

    return RewRoomSimPositionBatchResult(
        candidate_id=request.candidate_id,
        model_id=ROOMSIM_MODEL_ID,
        model_version=before.rew_version,
        adapter_version=ROOMSIM_BATCH_ADAPTER_VERSION,
        pre_state_sha256=pre_hash,
        applied_state_sha256=intended_hash,
        restored_state_sha256=restored_hash,
        response=response,
    )
