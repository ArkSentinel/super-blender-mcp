"""SuperMCP connection — port 9877, auto-retry, separate from Free 9876."""

import json
import os
import socket
import time

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9877
_TIMEOUT = 30.0
_RECV_BUFFER = 65536
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 0.2  # seconds, exponential


def get_connection_params():
    host = os.environ.get("SUPER_MCP_HOST", os.environ.get("BLENDER_MCP_HOST", DEFAULT_HOST))
    port = int(os.environ.get("SUPER_MCP_PORT", str(DEFAULT_PORT)))
    return host, port


def send_to_supermcp(command: dict, timeout=_TIMEOUT) -> dict:
    """Send JSON command to SuperMCP addon on port 9877 with auto-retry."""
    host, port = get_connection_params()
    payload = json.dumps(command) + "\0"
    last_err = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((host, port))
                sock.sendall(payload.encode("utf-8"))
                buf = bytearray()
                while True:
                    chunk = sock.recv(_RECV_BUFFER)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    if b"\0" in buf:
                        break
                if not buf:
                    raise ConnectionError("Empty response from SuperMCP")
                line, _, _ = buf.partition(b"\0")
                response = json.loads(line.decode("utf-8"))
                return response
        except (ConnectionRefusedError, socket.timeout, OSError, ConnectionError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
                continue
            break
    raise ConnectionError(
        f"Cannot connect to SuperMCP at {host}:{port} after {_RETRY_ATTEMPTS} attempts (Free is 9876, Super is 9877). "
        f"Ensure Blender is running with SuperMCP addon enabled and server started (N-panel > SuperMCP > Start). Last error: {last_err}"
    )


def send_code(code: str, strict_json: bool = False) -> dict:
    """Send execute_code style command (compat with blmcp framing)."""
    return send_to_supermcp({"type": "execute", "code": code, "strict_json": strict_json})


# Backwards alias used by tools
def send_command(cmd_type: str, params: dict | None = None) -> dict:
    return send_to_supermcp({"type": cmd_type, "params": params or {}})
