from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import json
import math
import struct
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_REW_API_URL = 'http://127.0.0.1:4735'


class RewApiError(RuntimeError):
    pass


class RewApiUnavailable(RewApiError):
    pass


@dataclass(frozen=True)
class RewFrequencyResponse:
    measurement_id: str
    unit: str | None
    smoothing: str | None
    start_frequency_hz: float
    points_per_octave: float | None
    frequency_step_hz: float | None
    frequency_hz: tuple[float, ...]
    magnitude: tuple[float, ...]
    phase_deg: tuple[float, ...] | None
    requested_unit: str
    requested_ppo: int | None
    requested_smoothing: str | None


def validate_rew_api_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != 'http':
        raise ValueError('REW API URL must use http')
    if parsed.hostname not in {'127.0.0.1', 'localhost'}:
        raise ValueError('REW API is restricted to localhost')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('REW API URL must not contain credentials, query or fragment')
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Invalid REW API port') from exc
    if port is not None and not (1024 <= port <= 65535):
        raise ValueError('REW API port must be between 1024 and 65535')
    if parsed.path.rstrip('/'):
        raise ValueError('REW API URL must not contain a path')
    return f'http://{parsed.hostname}:{port or 4735}'


def decode_rew_float_array(encoded: str) -> tuple[float, ...]:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise RewApiError('Invalid Base64 array from REW') from exc
    if len(raw) % 4 != 0:
        raise RewApiError('REW float array byte length is not divisible by four')
    if not raw:
        return ()
    values = tuple(struct.unpack(f'>{len(raw) // 4}f', raw))
    if any(not math.isfinite(value) for value in values):
        raise RewApiError('REW float array contains non-finite values')
    return values


def _field(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return None


def decode_frequency_response(
    measurement_id: str,
    payload: dict[str, Any],
    *,
    requested_unit: str = 'SPL',
    requested_ppo: int | None = None,
    requested_smoothing: str | None = None,
) -> RewFrequencyResponse:
    magnitude_encoded = _field(payload, 'magnitude', 'magnitudes')
    if not isinstance(magnitude_encoded, str):
        raise RewApiError('REW frequency response does not contain magnitude data')
    magnitude = decode_rew_float_array(magnitude_encoded)
    if not magnitude:
        raise RewApiError('REW frequency response magnitude array is empty')

    start_frequency = _field(payload, 'startFreq', 'startFrequency')
    if not isinstance(start_frequency, (int, float)) or not math.isfinite(float(start_frequency)) or start_frequency <= 0:
        raise RewApiError('REW frequency response has an invalid start frequency')

    ppo_raw = _field(payload, 'ppo', 'pointsPerOctave')
    step_raw = _field(payload, 'freqStep', 'frequencyStep')
    ppo = float(ppo_raw) if isinstance(ppo_raw, (int, float)) and math.isfinite(float(ppo_raw)) and ppo_raw > 0 else None
    step = float(step_raw) if isinstance(step_raw, (int, float)) and math.isfinite(float(step_raw)) and step_raw > 0 else None
    if ppo is None and step is None:
        raise RewApiError('REW frequency response has neither ppo nor freqStep')

    if ppo is not None:
        frequency = tuple(float(start_frequency) * math.exp(index * math.log(2.0) / ppo) for index in range(len(magnitude)))
    else:
        assert step is not None
        frequency = tuple(float(start_frequency) + index * step for index in range(len(magnitude)))
    if any(not math.isfinite(value) or value <= 0 for value in frequency):
        raise RewApiError('REW frequency axis is invalid')

    phase_encoded = _field(payload, 'phase', 'phases')
    phase = decode_rew_float_array(phase_encoded) if isinstance(phase_encoded, str) and phase_encoded else None
    if phase is not None and len(phase) != len(magnitude):
        raise RewApiError('REW magnitude and phase array lengths differ')

    unit = payload.get('unit') if isinstance(payload.get('unit'), str) else None
    smoothing = payload.get('smoothing') if isinstance(payload.get('smoothing'), str) else None
    return RewFrequencyResponse(
        measurement_id=measurement_id,
        unit=unit,
        smoothing=smoothing,
        start_frequency_hz=float(start_frequency),
        points_per_octave=ppo,
        frequency_step_hz=step,
        frequency_hz=frequency,
        magnitude=magnitude,
        phase_deg=phase,
        requested_unit=requested_unit,
        requested_ppo=requested_ppo,
        requested_smoothing=requested_smoothing,
    )


def normalize_measurement_summaries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get('measurements'), list):
            return [item for item in payload['measurements'] if isinstance(item, dict)]
        values = [item for item in payload.values() if isinstance(item, dict)]
        if values and all('uuid' in item or 'title' in item for item in values):
            return values
        if payload == {}:
            return []
    raise RewApiError('Unexpected REW measurements response shape')


class RewApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_REW_API_URL,
        *,
        timeout_s: float = 1.5,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = validate_rew_api_url(base_url)
        self.timeout_s = timeout_s
        self._opener = opener

    def _get_json(self, path: str, query: dict[str, str | int | float | bool] | None = None) -> Any:
        url = f'{self.base_url}{path}'
        if query:
            url = f'{url}?{urlencode(query)}'
        request = Request(url, headers={'Accept': 'application/json'}, method='GET')
        try:
            with self._opener(request, timeout=self.timeout_s) as response:
                raw = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RewApiUnavailable(str(exc)) from exc
        try:
            return json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RewApiError('REW returned invalid JSON') from exc

    def list_measurements(self) -> list[dict[str, Any]]:
        return normalize_measurement_summaries(self._get_json('/measurements'))

    def get_measurement(self, measurement_id: str) -> dict[str, Any]:
        payload = self._get_json(f'/measurements/{quote(measurement_id, safe="")}')
        if not isinstance(payload, dict):
            raise RewApiError('Unexpected REW measurement response shape')
        return payload

    def get_frequency_response(
        self,
        measurement_id: str,
        *,
        ppo: int | None = 96,
        unit: str = 'SPL',
        smoothing: str | None = None,
    ) -> RewFrequencyResponse:
        if ppo is not None and not (1 <= ppo <= 384):
            raise ValueError('ppo must be between 1 and 384')
        query: dict[str, str | int] = {'unit': unit}
        if ppo is not None:
            query['ppo'] = ppo
        if smoothing:
            query['smoothing'] = smoothing
        payload = self._get_json(f'/measurements/{quote(measurement_id, safe="")}/frequency-response', query)
        if not isinstance(payload, dict):
            raise RewApiError('Unexpected REW frequency-response response shape')
        return decode_frequency_response(
            measurement_id,
            payload,
            requested_unit=unit,
            requested_ppo=ppo,
            requested_smoothing=smoothing,
        )

    def status(self) -> dict[str, Any]:
        try:
            measurements = self.list_measurements()
        except RewApiError as exc:
            return {
                'connected': False,
                'read_only': True,
                'base_url': self.base_url,
                'measurement_count': None,
                'error': str(exc),
            }
        return {
            'connected': True,
            'read_only': True,
            'base_url': self.base_url,
            'measurement_count': len(measurements),
            'error': None,
        }

    @staticmethod
    def response_payload(response: RewFrequencyResponse) -> dict[str, Any]:
        return asdict(response)
