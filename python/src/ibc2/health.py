"""Checking that the TWS/Gateway API is genuinely alive, not merely that the port is open."""

from __future__ import annotations

import socket
import struct
import time


def api_handshake(host: str, port: int, timeout: float = 5.0) -> bool:
    """Perform the first step of the IB API handshake and wait for the server's reply.

    A frozen Gateway can keep its port open without answering; requiring a real
    reply catches that. We send the version range and disconnect without starting
    an API session, so no client slot or order state is touched.
    """
    payload = b"v100..176"
    message = b"API\0" + struct.pack(">I", len(payload)) + payload
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(message)
            header = _recv_exact(s, 4)
            if header is None:
                return False
            (length,) = struct.unpack(">I", header)
            if not 0 < length < 4096:
                return False
            body = _recv_exact(s, length)
            return body is not None and body.split(b"\0", 1)[0].isdigit()
    except OSError:
        return False


def _recv_exact(s: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def send_command(port: int, command: str, host: str = "127.0.0.1", timeout: float = 5.0) -> str:
    """Send a command (STOP, RESTART, ...) to IBC's command server and return its reply."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(command.encode() + b"\n")
        # IBC may send greeting/info lines and a prompt before the verdict, which is a
        # line starting "OK" or "ERROR"
        buf, reply = "", ""
        deadline = time.monotonic() + timeout
        while not reply and time.monotonic() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk.decode(errors="replace")
            for line in buf.splitlines():
                line = line.strip().lstrip(">").strip()
                if line.startswith(("OK", "ERROR")):
                    reply = line
                    break
        try:
            s.sendall(b"EXIT\n")
        except OSError:
            pass
        return reply
