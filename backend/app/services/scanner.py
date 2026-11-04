"""Malware scanning (PRD section 8). Production uses ClamAV's clamd over TCP (INSTREAM).

The ``builtin`` scanner only recognises the EICAR test signature; it exists so tests and the
test copy can run without a ClamAV container. It must not be used in production.
"""

from __future__ import annotations

import socket
import struct

from app.config import get_settings

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class ScannerUnavailable(RuntimeError):
    pass


def _clamd(data: bytes, host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=30) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 64 * 1024):
                chunk = data[i : i + 64 * 1024]
                sock.sendall(struct.pack(">I", len(chunk)) + chunk)
            sock.sendall(struct.pack(">I", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = sock.recv(4096)
                if not part:
                    break
                reply += part
    except OSError as exc:
        raise ScannerUnavailable(str(exc)) from exc
    text = reply.decode(errors="replace").strip("\0").strip()
    if text.endswith("OK"):
        return True
    if "FOUND" in text:
        return False
    raise ScannerUnavailable(text)


def is_clean(data: bytes) -> bool:
    settings = get_settings()
    if settings.scanner == "builtin":
        if settings.env == "production":
            raise ScannerUnavailable("builtin scanner is not allowed in production")
        return EICAR not in data
    return _clamd(data, settings.clamd_host, settings.clamd_port)
