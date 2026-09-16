from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import time
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_ID = 'home-theater-digital-twin'
ERROR_ALREADY_EXISTS = 183


def default_data_dir() -> Path:
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        return Path(local_app_data) / 'HomeTheaterDigitalTwin'
    return Path.home() / '.home-theater-digital-twin'


def _instance_key(root: Path) -> str:
    normalized = str(root.expanduser().resolve()).casefold().encode('utf-8')
    return hashlib.sha256(normalized).hexdigest()[:20]


class SingleInstanceGuard:
    """OS-level lock scoped to one HTDT data directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._handle: int | None = None
        self._file: BinaryIO | None = None
        self._acquired = False

    def acquire(self) -> bool:
        if self._acquired:
            return True
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            create_mutex = kernel32.CreateMutexW
            create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            create_mutex.restype = wintypes.HANDLE
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL

            ctypes.set_last_error(0)
            handle = create_mutex(None, False, f'Local\\HTDT-{_instance_key(self.root)}')
            if not handle:
                raise OSError(ctypes.get_last_error(), 'CreateMutexW failed')
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                close_handle(handle)
                return False
            self._handle = int(handle)
            self._acquired = True
            return True

        import fcntl

        lock_path = self.root / '.instance.lock'
        file = lock_path.open('a+b')
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            return False
        self._file = file
        self._acquired = True
        return True

    def release(self) -> None:
        if not self._acquired:
            return
        if os.name == 'nt' and self._handle is not None:
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            close_handle(wintypes.HANDLE(self._handle))
            self._handle = None
        elif self._file is not None:
            import fcntl

            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None
        self._acquired = False

    def __enter__(self) -> 'SingleInstanceGuard':
        if not self.acquire():
            raise RuntimeError('HTDT data directory is already locked by another process')
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


@dataclass(frozen=True)
class RuntimeInfo:
    pid: int
    port: int
    url: str


RUNTIME_FILENAME = 'runtime.json'


def write_runtime_info(root: Path, info: RuntimeInfo) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / RUNTIME_FILENAME
    temp = root / f'.{RUNTIME_FILENAME}.{os.getpid()}.tmp'
    temp.write_text(json.dumps({'app_id': APP_ID, 'pid': info.pid, 'port': info.port, 'url': info.url}, sort_keys=True), encoding='utf-8')
    os.replace(temp, path)


def read_runtime_info(root: Path) -> RuntimeInfo | None:
    path = root / RUNTIME_FILENAME
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if payload.get('app_id') != APP_ID:
        return None
    pid = payload.get('pid')
    port = payload.get('port')
    url = payload.get('url')
    if not isinstance(pid, int) or not isinstance(port, int) or not isinstance(url, str):
        return None
    if not (1 <= port <= 65535) or url != f'http://127.0.0.1:{port}/':
        return None
    return RuntimeInfo(pid=pid, port=port, url=url)


def clear_runtime_info(root: Path, pid: int) -> None:
    info = read_runtime_info(root)
    if info is not None and info.pid == pid:
        (root / RUNTIME_FILENAME).unlink(missing_ok=True)


def probe_runtime(info: RuntimeInfo, timeout_s: float = 0.5) -> bool:
    request = Request(f'{info.url}api/health', headers={'Accept': 'application/json'}, method='GET')
    try:
        with urlopen(request, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get('app_id') == APP_ID and payload.get('status') == 'ok'


def wait_for_runtime(root: Path, timeout_s: float = 10.0) -> RuntimeInfo | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        info = read_runtime_info(root)
        if info is not None and probe_runtime(info):
            return info
        time.sleep(0.1)
    return None
