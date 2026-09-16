from __future__ import annotations

import socket

import pytest

from htdt.__main__ import DEFAULT_PORT, HOST, build_parser, local_url, reserve_listening_socket


def test_local_url_is_loopback_only() -> None:
    assert local_url(8765) == 'http://127.0.0.1:8765/'


def test_preferred_port_is_reserved_when_free() -> None:
    listener, port = reserve_listening_socket(preferred_port=DEFAULT_PORT)
    try:
        assert port == DEFAULT_PORT
        assert listener.getsockname()[0] == HOST
    finally:
        listener.close()


def test_busy_preferred_port_falls_back_to_another_loopback_port() -> None:
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind((HOST, 0))
    occupied.listen(1)
    busy_port = int(occupied.getsockname()[1])
    listener = None
    try:
        listener, selected = reserve_listening_socket(preferred_port=busy_port)
        assert selected != busy_port
        assert 1 <= selected <= 65535
        assert listener.getsockname()[0] == HOST
    finally:
        if listener is not None:
            listener.close()
        occupied.close()


def test_invalid_preferred_port_is_rejected() -> None:
    with pytest.raises(ValueError, match='port'):
        reserve_listening_socket(preferred_port=0)


def test_cli_no_browser_and_port_are_parsed() -> None:
    args = build_parser().parse_args(['--port', '9000', '--no-browser'])
    assert args.port == 9000
    assert args.no_browser is True
