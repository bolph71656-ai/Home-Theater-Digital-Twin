import base64
import json
import struct
from urllib.error import URLError
from urllib.request import Request

import pytest

from htdt.rew_api import RewApiClient, RewApiError, decode_frequency_response, decode_rew_float_array, normalize_measurement_summaries, validate_rew_api_url


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.raw = json.dumps(payload).encode()

    def __enter__(self) -> 'FakeResponse':
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.raw


def encode(values: list[float]) -> str:
    return base64.b64encode(struct.pack(f'>{len(values)}f', *values)).decode()


def test_official_big_endian_decode_example() -> None:
    values = decode_rew_float_array('PgAAAD6AAAA+wAAAPwAAAA==')
    assert values == pytest.approx((0.125, 0.25, 0.375, 0.5))


def test_frequency_response_log_axis_and_provenance() -> None:
    response = decode_frequency_response('abc', {
        'unit': 'SPL',
        'smoothing': '1/48',
        'startFreq': 20.0,
        'ppo': 1,
        'magnitude': encode([70.0, 71.0, 72.0, 73.0]),
        'phase': encode([0.0, 10.0, 20.0, 30.0]),
    }, requested_unit='SPL', requested_ppo=96, requested_smoothing='1/24')
    assert response.frequency_hz == pytest.approx((20.0, 40.0, 80.0, 160.0))
    assert response.magnitude == pytest.approx((70.0, 71.0, 72.0, 73.0))
    assert response.phase_deg == pytest.approx((0.0, 10.0, 20.0, 30.0))
    assert response.requested_ppo == 96
    assert response.requested_smoothing == '1/24'
    assert response.smoothing == '1/48'


def test_frequency_response_linear_axis() -> None:
    response = decode_frequency_response('abc', {
        'startFreq': 10.0,
        'freqStep': 2.5,
        'magnitude': encode([1.0, 2.0, 3.0]),
    })
    assert response.frequency_hz == pytest.approx((10.0, 12.5, 15.0))
    assert response.phase_deg is None


def test_measurement_shapes_are_normalized() -> None:
    assert normalize_measurement_summaries([{'uuid': 'a'}]) == [{'uuid': 'a'}]
    assert normalize_measurement_summaries({'1': {'uuid': 'a'}, '2': {'uuid': 'b'}}) == [{'uuid': 'a'}, {'uuid': 'b'}]
    assert normalize_measurement_summaries({'measurements': [{'uuid': 'a'}]}) == [{'uuid': 'a'}]
    assert normalize_measurement_summaries({}) == []


def test_remote_rew_url_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_rew_api_url('http://192.168.1.10:4735')
    with pytest.raises(ValueError):
        validate_rew_api_url('https://127.0.0.1:4735')


def test_client_uses_get_only_and_preserves_query_provenance() -> None:
    calls: list[tuple[str, str]] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        calls.append((request.full_url, request.get_method()))
        if request.full_url.endswith('/measurements'):
            return FakeResponse({'1': {'uuid': 'abc', 'title': 'FL'}})
        if '/frequency-response?' in request.full_url:
            return FakeResponse({'unit': 'SPL', 'smoothing': '1/48', 'startFreq': 20.0, 'ppo': 1, 'magnitude': encode([70.0, 71.0])})
        raise AssertionError(request.full_url)

    client = RewApiClient(opener=opener)
    assert client.status()['measurement_count'] == 1
    response = client.get_frequency_response('abc', ppo=96, smoothing='1/24')
    assert response.magnitude == pytest.approx((70.0, 71.0))
    assert response.requested_ppo == 96
    assert response.requested_smoothing == '1/24'
    assert calls and all(method == 'GET' for _, method in calls)
    assert any('ppo=96' in url and 'smoothing=1%2F24' in url for url, _ in calls)


def test_status_falls_back_offline_without_raising() -> None:
    def opener(request: Request, timeout: float) -> FakeResponse:
        raise URLError('not running')

    status = RewApiClient(opener=opener).status()
    assert status['connected'] is False
    assert status['read_only'] is True
    assert status['measurement_count'] is None


def test_invalid_arrays_are_rejected() -> None:
    bad = base64.b64encode(b'123').decode()
    with pytest.raises(RewApiError):
        decode_rew_float_array(bad)
    non_finite = base64.b64encode(struct.pack('>f', float('nan'))).decode()
    with pytest.raises(RewApiError):
        decode_rew_float_array(non_finite)
