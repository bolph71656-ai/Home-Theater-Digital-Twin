import copy
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request

import pytest

from htdt.rew_api import RewApiClient, RewApiUnavailable
from htdt.rew_roomsim_transaction import (
    RewRoomSimCancelled,
    RewRoomSimMutation,
    RewRoomSimRestoreError,
    RewRoomSimTransaction,
    roomsim_snapshot_sha256,
)

FIXTURES = Path(__file__).parent / 'fixtures'
STATE_FIXTURE = FIXTURES / 'rew_5_40_beta135_roomsim_state.json'
FR_FIXTURE = FIXTURES / 'rew_5_40_beta135_roomsim_frequency_response.json'


class FakeResponse:
    def __init__(self, payload: object | None) -> None:
        self.raw = b'' if payload is None else json.dumps(payload).encode('utf-8')
    def __enter__(self) -> 'FakeResponse':
        return self
    def __exit__(self, *args: object) -> None:
        return None
    def read(self) -> bytes:
        return self.raw


class StatefulRoomSim:
    def __init__(self, *, fail_response: bool = False, break_restore: bool = False) -> None:
        self.state = json.loads(STATE_FIXTURE.read_text(encoding='utf-8'))
        self.original = copy.deepcopy(self.state)
        self.frequency_response = json.loads(FR_FIXTURE.read_text(encoding='utf-8'))
        self.calls: list[tuple[str, str, object | None]] = []
        self.fail_response = fail_response
        self.break_restore = break_restore
        self.head_put_count = 0

    def opener(self, request: Request, timeout: float) -> FakeResponse:
        parsed = urlparse(request.full_url)
        path, method = parsed.path, request.get_method()
        body = json.loads(request.data.decode('utf-8')) if request.data else None
        self.calls.append((method, path, body))
        if method == 'PUT':
            if path == '/roomsim/room-size':
                self.state['room_size'] = copy.deepcopy(body)
                return FakeResponse(None)
            if path == '/roomsim/sources':
                self.state['sources']['active'] = list(body['sources'])
                return FakeResponse(None)
            if path == '/roomsim/head-position':
                self.head_put_count += 1
                if not (self.break_restore and self.head_put_count >= 2):
                    self.state['head_position'] = copy.deepcopy(body)
                return FakeResponse(None)
            if path.startswith('/roomsim/') and path.endswith('/position'):
                source = unquote(path.split('/')[2])
                self.state['sources']['details'][source]['position'] = copy.deepcopy(body)
                return FakeResponse(None)
            raise AssertionError((method, path, body))

        assert method == 'GET'
        query = parse_qs(parsed.query)
        if path == '/version':
            return FakeResponse(self.state['version'])
        if path == '/roomsim/room-size':
            assert query.get('unit') == ['metres']
            return FakeResponse(self.state['room_size'])
        if path == '/roomsim/room-is-sealed':
            return FakeResponse(self.state['room_is_sealed'])
        if path == '/roomsim/absorptions':
            return FakeResponse(self.state['absorptions'])
        if path == '/roomsim/options':
            return FakeResponse(self.state['options'])
        if path == '/roomsim/head-position':
            assert query.get('unit') == ['metres']
            return FakeResponse(self.state['head_position'])
        if path == '/roomsim/mic-posn-offsets':
            return FakeResponse(self.state['mic_posn_offsets'])
        if path == '/roomsim/sources':
            return FakeResponse({'sources': self.state['sources']['active']})
        if path == '/roomsim/source-names':
            return FakeResponse(self.state['sources']['recognized'])
        if path == '/roomsim/mic-positions':
            return FakeResponse(self.state['mic_positions'])
        if path == '/roomsim/frequency-response':
            if self.fail_response:
                raise URLError('simulated Room Simulator response failure')
            assert query.get('micposition') == ['Main']
            return FakeResponse(self.frequency_response)
        if path.startswith('/roomsim/') and path.endswith('/frequency-response'):
            if self.fail_response:
                raise URLError('simulated Room Simulator response failure')
            return FakeResponse(self.frequency_response)
        if path.startswith('/roomsim/') and path.endswith('/position'):
            source = unquote(path.split('/')[2])
            assert query.get('unit') == ['metres']
            return FakeResponse(self.state['sources']['details'][source]['position'])
        if path.startswith('/roomsim/') and path.endswith('/configuration'):
            source = unquote(path.split('/')[2])
            return FakeResponse(self.state['sources']['details'][source]['configuration'])
        raise AssertionError((method, path, query))

    def is_original(self) -> bool:
        return self.state == self.original


def mutation() -> RewRoomSimMutation:
    return RewRoomSimMutation(
        room_size_htdt={'width_m': 4.1, 'depth_m': 5.2, 'height_m': 2.4},
        active_sources=('Left', 'Right'),
        head_position_htdt={'x_m': 2.1, 'y_m': 3.0, 'z_m': 1.0},
        source_positions_htdt={
            'Left': {'x_m': 1.1, 'y_m': 1.2, 'z_m': 1.0},
            'Right': {'x_m': 3.0, 'y_m': 1.2, 'z_m': 1.0},
        },
    )


def test_transaction_mutates_reads_response_and_restores() -> None:
    server = StatefulRoomSim()
    client = RewApiClient(opener=server.opener)
    baseline = client.get_roomsim_snapshot()
    result = RewRoomSimTransaction(client).run(mutation())
    assert result.baseline_sha256 == roomsim_snapshot_sha256(baseline)
    assert result.restored_sha256 == result.baseline_sha256
    assert result.applied_sha256 != result.baseline_sha256
    assert len(result.response.frequency_hz) == 751
    assert server.is_original()
    puts = [(path, body) for method, path, body in server.calls if method == 'PUT']
    assert ('/roomsim/room-size', {'unit': 'metres', 'length': 5.2, 'width': 4.1, 'height': 2.4}) in puts
    assert ('/roomsim/sources', {'sources': ['Left', 'Right']}) in puts


def test_prediction_failure_still_restores() -> None:
    server = StatefulRoomSim(fail_response=True)
    with pytest.raises(RewApiUnavailable):
        RewRoomSimTransaction(RewApiClient(opener=server.opener)).run(mutation())
    assert server.is_original()
    assert server.head_put_count == 2


def test_cancel_after_mutation_restores_without_response_read() -> None:
    server = StatefulRoomSim()
    checks = iter((False, True))
    with pytest.raises(RewRoomSimCancelled):
        RewRoomSimTransaction(RewApiClient(opener=server.opener)).run(
            mutation(), cancelled=lambda: next(checks)
        )
    assert server.is_original()
    assert not any(path.endswith('/frequency-response') for method, path, _ in server.calls if method == 'GET')


def test_restore_mismatch_rejects_prediction() -> None:
    server = StatefulRoomSim(break_restore=True)
    with pytest.raises(RewRoomSimRestoreError, match='restore verification failed'):
        RewRoomSimTransaction(RewApiClient(opener=server.opener)).run(mutation())
    assert not server.is_original()


def test_transaction_rejects_unsnapshotted_source_activation() -> None:
    server = StatefulRoomSim()
    with pytest.raises(ValueError, match='subset of sources active'):
        RewRoomSimTransaction(RewApiClient(opener=server.opener)).run(
            RewRoomSimMutation(active_sources=('Left', 'Sub2'))
        )
    assert not any(method == 'PUT' for method, _, _ in server.calls)
    assert server.is_original()


def test_client_rejects_arbitrary_method_and_url() -> None:
    server = StatefulRoomSim()
    client = RewApiClient(opener=server.opener)
    with pytest.raises(ValueError, match='Unsupported'):
        client._request_json('DELETE', '/roomsim/room-size')
    with pytest.raises(ValueError, match='local API path'):
        client._request_json('PUT', 'https://example.com/roomsim', payload={})
    assert server.calls == []
