"""Shared helpers for SuperMCP tools."""

def unwrap_response(resp: dict) -> dict:
    """Unwrap addon envelope {status: success/ok, result: ...}. Passthrough on error."""
    if resp.get("status") in ("success", "ok"):
        return resp.get("result", resp)
    return resp

def parse_param_value(value: str):
    """Coerce string param to int/float/bool if possible."""
    if not isinstance(value, str):
        return value
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return value
