from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser

import uvicorn


HOST = '127.0.0.1'
DEFAULT_PORT = 8765


def reserve_listening_socket(host: str = HOST, preferred_port: int = DEFAULT_PORT) -> tuple[socket.socket, int]:
    """Reserve the preferred loopback port, or an OS-selected free port when it is busy."""
    if not (1 <= preferred_port <= 65535):
        raise ValueError('port must be between 1 and 65535')

    preferred = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        preferred.bind((host, preferred_port))
        preferred.listen(2048)
        return preferred, int(preferred.getsockname()[1])
    except OSError:
        preferred.close()

    fallback = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        fallback.bind((host, 0))
        fallback.listen(2048)
        return fallback, int(fallback.getsockname()[1])
    except Exception:
        fallback.close()
        raise


def local_url(port: int) -> str:
    return f'http://{HOST}:{port}/'


def open_browser_when_ready(port: int, *, timeout_s: float = 10.0) -> None:
    """Open the local UI after the reserved socket starts accepting connections."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.25):
                webbrowser.open(local_url(port), new=2)
                return
        except OSError:
            time.sleep(0.1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run Home Theater Digital Twin on localhost.')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'preferred localhost port (default: {DEFAULT_PORT})')
    parser.add_argument('--no-browser', action='store_true', help='do not open the default browser automatically')
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    listener, port = reserve_listening_socket(preferred_port=args.port)
    url = local_url(port)
    print(f'Home Theater Digital Twin: {url}')
    if port != args.port:
        print(f'Preferred port {args.port} was busy; using {port} instead.')

    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()

    config = uvicorn.Config(
        'htdt.main:app',
        host=HOST,
        port=port,
        reload=False,
        log_level='info',
    )
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()


if __name__ == '__main__':
    main()
