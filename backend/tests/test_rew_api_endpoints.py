import base64
import json
from pathlib import Path
import struct
from urllib.request import Request

from fastapi.testclient import TestClient

from htdt.main import create_app
from htdt.rew_api import RewApiClient


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


def test_rew_read_only_endpoints(tmp_path: Path) -> None:
    methods: list[str] = []

    def opener(request: Request, timeout: float) -> FakeResponse:
        methods.append(request.get_method())
        if request.full_url.endswith('/measurements'):
            return FakeResponse({'1': {'uuid': 'abc', 'title': 'FL', 'startFreq': 20, 'endFreq': 20000}})
        if '/measurements/abc/frequency-response?' in request.full_url:
            return FakeResponse({'unit': 'SPL', 'smoothing': '1/48', 'startFreq': 20.0, 'ppo': 1, 'magnitude': encode([70.0, 71.0, 72.0])})
        raise AssertionError(request.full_url)

    rew = RewApiClient(opener=opener)
    client = TestClient(create_app(tmp_path, rew_client=rew))

    status = client.get('/api/rew/status')
    assert status.status_code == 200
    assert status.json()['connected'] is True
    assert status.json()['read_only'] is True

    measurements = client.get('/api/rew/measurements')
    assert measurements.status_code == 200
    assert measurements.json()[0]['uuid'] == 'abc'

    response = client.get('/api/rew/measurements/abc/frequency-response?ppo=96')
    assert response.status_code == 200
    assert response.json()['magnitude'] == [70.0, 71.0, 72.0]
    assert methods and set(methods) == {'GET'}
