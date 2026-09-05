"""SuperMCP MCP Server — FastMCP, port 9877 separate from Free 9876."""

import argparse
import importlib
import os
import pkgutil

import yaml
from mcp.server.fastmcp import FastMCP

_USE_HTTP = True
_TRANSPORTS = ("stdio", *(("http",) if _USE_HTTP else ()))


def main() -> int:
    parser = argparse.ArgumentParser(description="SuperMCP server for Blender (port 9877, Free is 9876).")
    parser.add_argument("--transport", "-t", choices=_TRANSPORTS, default="stdio", help="Transport (default: stdio)")
    if _USE_HTTP:
        parser.add_argument("--host", default="127.0.0.1", help="Host for http")
        parser.add_argument("--port", "-p", type=int, default=8001, help="Port for http (default 8001, Free uses 8000)")

    args = parser.parse_args()

    # Load prompts if exists
    prompts_path = os.path.join(os.path.dirname(__file__), "..", "data", "prompts.yml")
    instructions = "SuperMCP for Blender — Advanced mesh curing + Godot pipeline on port 9877."
    if os.path.exists(prompts_path):
        try:
            import yaml as _yaml
            with open(prompts_path, encoding="utf-8") as fh:
                p = _yaml.safe_load(fh)
                if p and isinstance(p, dict) and "initial_instructions" in p:
                    instructions = str(p["initial_instructions"])
        except:
            pass

    mcp = FastMCP("super-mcp", instructions=instructions)

    # Auto-discover tools
    import server.tools as tools_pkg

    for _, modname, _ispkg in pkgutil.iter_modules(tools_pkg.__path__):
        if modname.startswith("_") or modname.endswith("_toolcode"):
            continue
        # skip subpackages without register
        try:
            mod = importlib.import_module(f"server.tools.{modname}")
            if hasattr(mod, "register"):
                mod.register(mcp)
        except Exception as e:
            print(f"SuperMCP: failed to load tool {modname}: {e}")

    # Also load subpackages (e.g. tools/cure)
    for sub in os.listdir(tools_pkg.__path__[0]):
        subpath = os.path.join(tools_pkg.__path__[0], sub)
        if os.path.isdir(subpath) and not sub.startswith("_") and not sub.startswith("__"):
            for _, modname, _ispkg in pkgutil.iter_modules([subpath]):
                if modname.startswith("_"):
                    continue
                try:
                    mod = importlib.import_module(f"server.tools.{sub}.{modname}")
                    if hasattr(mod, "register"):
                        mod.register(mcp)
                except Exception as e:
                    print(f"SuperMCP: failed to load tool {sub}.{modname}: {e}")

    transport = args.transport
    if _USE_HTTP and transport == "http":
        from mcp.server.fastmcp.server import TransportSecuritySettings
        from starlette.applications import Starlette
        from starlette.middleware.cors import CORSMiddleware

        transport = "streamable-http"
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = "/"
        mcp.settings.stateless_http = True
        mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

        orig = mcp.streamable_http_app

        def _app_with_cors() -> Starlette:
            app = orig()
            app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
            return app

        mcp.streamable_http_app = _app_with_cors

    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
