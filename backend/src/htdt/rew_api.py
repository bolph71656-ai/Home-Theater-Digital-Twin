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

    def get_audio_preflight(self) -> dict[str, Any]:
        audio_status = self._get_json('/audio/status')
        driver_payload = self._get_json('/audio/driver')
        sample_rate = self._get_json('/audio/samplerate')
        if not isinstance(audio_status, dict) or not isinstance(driver_payload, dict) or not isinstance(sample_rate, dict):
            raise RewApiError('Unexpected REW audio status response shape')

        driver = driver_payload.get('driver')
        if not isinstance(driver, str) or not driver:
            raise RewApiError('REW audio driver response is invalid')
        result: dict[str, Any] = {
            'read_only': True,
            'audio_enabled': audio_status.get('enabled') if isinstance(audio_status.get('enabled'), bool) else None,
            'audio_ready': audio_status.get('ready') if isinstance(audio_status.get('ready'), bool) else None,
            'driver': driver,
            'sample_rate_hz': float(sample_rate['value']) if isinstance(sample_rate.get('value'), (int, float)) else None,
            'sample_rate_unit': sample_rate.get('unit') if isinstance(sample_rate.get('unit'), str) else None,
            'java': None,
            'warnings': [],
        }
        if driver != 'Java':
            result['warnings'].append('Java multichannel preflight is not applicable while REW is using another driver.')
            return result

        input_device = self._get_json('/audio/java/input-device')
        input_devices = self._get_json('/audio/java/input-devices')
        input_hw_channels = self._get_json('/audio/java/num-input-device-channels')
        input_selection = self._get_json('/audio/java/input')
        input_choices = self._get_json('/audio/java/inputs')
        input_channel = self._get_json('/audio/java/input-channel')
        input_channels = self._get_json('/audio/java/num-input-channels')
        input_cal = self._get_json('/audio/input-cal')
        output_device = self._get_json('/audio/java/output-device')
        output_devices = self._get_json('/audio/java/output-devices')
        channel_count = self._get_json('/audio/java/num-output-device-channels')
        output_channels = self._get_json('/audio/java/output-channels')
        mapping = self._get_json('/audio/java/output-channel-mapping')
        stereo_only = self._get_json('/audio/java/stereo-only')
        if not isinstance(input_device, dict) or not isinstance(input_devices, list):
            raise RewApiError('Unexpected REW Java input-device response shape')
        if not isinstance(input_hw_channels, int) or input_hw_channels < 0 or not isinstance(input_selection, dict) or not isinstance(input_choices, list):
            raise RewApiError('Unexpected REW Java input response shape')
        if not isinstance(input_channel, dict) or not isinstance(input_channels, int) or input_channels < 0 or not isinstance(input_cal, dict):
            raise RewApiError('Unexpected REW Java input-channel response shape')
        if not isinstance(output_device, dict) or not isinstance(output_devices, list):
            raise RewApiError('Unexpected REW Java output-device response shape')
        if not isinstance(channel_count, int) or channel_count < 0 or not isinstance(output_channels, list):
            raise RewApiError('Unexpected REW Java output-channel response shape')
        if not isinstance(mapping, dict) or not isinstance(mapping.get('mapping'), list) or not isinstance(stereo_only, dict):
            raise RewApiError('Unexpected REW Java output mapping response shape')

        current_input = input_device.get('device') if isinstance(input_device.get('device'), str) else None
        current_input_selection = input_selection.get('input') if isinstance(input_selection.get('input'), str) else None
        selected_input_channel = input_channel.get('channel') if isinstance(input_channel.get('channel'), int) else None
        input_endpoint_ready = bool(result['audio_ready'] and current_input and input_channels > 0 and selected_input_channel is not None)
        current = output_device.get('device') if isinstance(output_device.get('device'), str) else None
        choices = [item for item in output_devices if isinstance(item, str)]
        channel_choices = [item for item in output_channels if isinstance(item, str)]
        exclusive = [item for item in choices if item.startswith('EXCL:')]
        stereo_flag = stereo_only.get('enable') if isinstance(stereo_only.get('enable'), bool) else None
        current_is_exclusive = bool(current and current.startswith('EXCL:'))
        multichannel_ready = bool(result['audio_ready'] and current_is_exclusive and channel_count > 2 and stereo_flag is not True)
        cal_all = input_cal.get('calDataAllInputs') if isinstance(input_cal.get('calDataAllInputs'), dict) else {}
        cal_path = cal_all.get('calFilePath') if isinstance(cal_all.get('calFilePath'), str) else None
        result['java'] = {
            'input_device': current_input,
            'input_devices': [item for item in input_devices if isinstance(item, str)],
            'hardware_input_channels': input_hw_channels,
            'input': current_input_selection,
            'inputs': [item for item in input_choices if isinstance(item, str)],
            'input_channel': selected_input_channel,
            'input_channels': input_channels,
            'input_endpoint_ready': input_endpoint_ready,
            'input_cal_selection': input_cal.get('currentInputSelection') if isinstance(input_cal.get('currentInputSelection'), str) else None,
            'input_cal_file': cal_path,
            'input_cal_file_present': bool(cal_path),
            'output_device': current,
            'output_devices': choices,
            'hardware_output_channels': channel_count,
            'output_channels': channel_choices,
            'output_channel_mapping': mapping['mapping'],
            'stereo_only': stereo_flag,
            'exclusive_output_candidates': exclusive,
            'current_output_is_exclusive': current_is_exclusive,
            'multichannel_ready': multichannel_ready,
        }
        if not input_endpoint_ready:
            result['warnings'].append('Current REW input endpoint is not ready for capture.')
        if not cal_path:
            result['warnings'].append('No REW input calibration file is selected; measurement microphone calibration is not verified.')
        if not exclusive:
            result['warnings'].append('No WASAPI-exclusive (EXCL:) output device is visible to REW.')
        elif not current_is_exclusive:
            result['warnings'].append('Current Java output is not a WASAPI-exclusive (EXCL:) device.')
        elif channel_count <= 2:
            result['warnings'].append('Current REW output exposes only mono/stereo hardware channels.')
        if stereo_flag is True:
            result['warnings'].append('REW Java driver is restricted to stereo-only mode.')
        return result


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
