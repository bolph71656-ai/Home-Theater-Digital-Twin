from __future__ import annotations

import argparse
from hashlib import sha256
import json
from typing import Any

from htdt.rew_api import DEFAULT_REW_API_URL, RewApiClient
from htdt.rew_roomsim_transaction import (
    RewRoomSimMutation,
    RewRoomSimTransaction,
    roomsim_snapshot_sha256,
)


def canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return sha256(raw).hexdigest()


def roomsim_openapi_subset(document: dict[str, Any]) -> dict[str, Any]:
    paths = document.get('paths')
    if not isinstance(paths, dict):
        raise ValueError('OpenAPI document does not contain paths')
    selected = {path: value for path, value in paths.items() if isinstance(path, str) and path.startswith('/roomsim')}
    if not selected:
        raise ValueError('OpenAPI document contains no /roomsim paths')
    return {
        'openapi': document.get('openapi'),
        'info': document.get('info'),
        'roomsim_paths': selected,
        'components': document.get('components') if isinstance(document.get('components'), dict) else {},
    }


def method_summary(subset: dict[str, Any]) -> dict[str, list[str]]:
    return {
        path: sorted(key.upper() for key in item if key.lower() in {'get', 'put', 'post', 'delete', 'patch'})
        for path, item in subset['roomsim_paths'].items()
        if isinstance(item, dict)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default=DEFAULT_REW_API_URL)
    parser.add_argument('--transaction', action='store_true')
    args = parser.parse_args()

    client = RewApiClient(args.base_url, timeout_s=3.0)
    version = client._get_json('/version')
    document = client._get_json('/doc.json')
    if not isinstance(version, dict) or not isinstance(document, dict):
        raise RuntimeError('Unexpected REW metadata response')

    subset = roomsim_openapi_subset(document)
    methods = method_summary(subset)
    print('S01_REW_VERSION', version.get('message'), flush=True)
    print('S01_OPENAPI_VERSION', subset.get('openapi'), flush=True)
    print('S01_OPENAPI_ROOMSIM_SHA256', canonical_sha(subset), flush=True)
    print('S01_ROOMSIM_PATH_COUNT', len(methods), flush=True)
    for path in sorted(methods):
        print('S01_ROOMSIM_PATH', path, ','.join(methods[path]), flush=True)

    snapshot = client.get_roomsim_snapshot()
    print('S01_BASELINE_STATE_SHA256', roomsim_snapshot_sha256(snapshot), flush=True)
    print('S01_ACTIVE_SOURCES', ','.join(snapshot.active_sources), flush=True)
    if not args.transaction:
        print('S01_PROBE_RESULT PASS', flush=True)
        return 0

    width = float(snapshot.room_size['width'])
    head = dict(snapshot.head_position_htdt)
    head['x_m'] = float(head['x_m']) + (0.01 if float(head['x_m']) + 0.01 < width else -0.01)
    result = RewRoomSimTransaction(client).run(
        RewRoomSimMutation(head_position_htdt={
            'x_m': float(head['x_m']), 'y_m': float(head['y_m']), 'z_m': float(head['z_m'])
        })
    )
    print('S01_TRANSACTION_BASELINE_SHA256', result.baseline_sha256, flush=True)
    print('S01_TRANSACTION_APPLIED_SHA256', result.applied_sha256, flush=True)
    print('S01_TRANSACTION_RESTORED_SHA256', result.restored_sha256, flush=True)
    print('S01_TRANSACTION_FR_POINTS', len(result.response.frequency_hz), flush=True)
    matched = result.restored_sha256 == result.baseline_sha256
    print('S01_TRANSACTION_RESTORE_MATCH', matched, flush=True)
    passed = matched and len(result.response.frequency_hz) > 0
    print('S01_PROBE_RESULT', 'PASS' if passed else 'FAIL', flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
