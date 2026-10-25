"""DesignForge SketchUp MCP server (mcp SDK v2.x; based on the community sketchup-mcp design) — DesignForge tool surface.

Runs on the geometry node, launched by sketchup-agent over stdio. Forwards each tool call as one
NDJSON request to the bridge extension on 127.0.0.1. `eval_ruby` is only registered when
DF_ALLOW_EVAL=1 (local debugging); production nodes never expose it.
"""
from __future__ import annotations

import itertools
import json
import os
import socket
from typing import Any

from mcp.server.mcpserver import MCPServer

PORT = int(os.environ.get("DF_BRIDGE_PORT", "9877"))
TOKEN = os.environ["DF_BRIDGE_TOKEN"]
TIMEOUT = float(os.environ.get("DF_BRIDGE_TIMEOUT", "120"))

mcp = MCPServer("designforge-sketchup")
_ids = itertools.count(1)


def _bridge(method: str, params: dict[str, Any]) -> dict:
    req = {"id": next(_ids), "token": TOKEN, "method": method, "params": params}
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=TIMEOUT) as s:
            s.sendall((json.dumps(req) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(1 << 20)
                if not chunk:
                    return {"ok": False, "error": "bridge closed connection", "retryable": True}
                buf += chunk
    except ConnectionRefusedError:
        return {"ok": False, "retryable": True,
                "error": f"SketchUp bridge not reachable on 127.0.0.1:{PORT}. Is SketchUp running with the DesignForge Bridge extension?"}
    except TimeoutError:
        return {"ok": False, "error": f"SketchUp did not answer {method} within {TIMEOUT:.0f}s", "retryable": True}
    return json.loads(buf)


@mcp.tool()
def df_ping() -> dict:
    """Bridge and SketchUp versions. Used as handshake."""
    return _bridge("ping", {})


@mcp.tool()
def df_new_model(template: str = "designforge_mm") -> dict:
    """Reset the active model to an empty millimetre model."""
    return _bridge("new_model", {"template": template})


@mcp.tool()
def df_execute_batch(job_id: str, commands: list[dict]) -> dict:
    """Execute geometry commands (ensure_material, ensure_tag, define_panel, define_proxy, group,
    place, paint) atomically in one undo operation. Units: mm."""
    return _bridge("execute_batch", {"job_id": job_id, "commands": commands})


@mcp.tool()
def df_add_scenes(scenes: list[dict]) -> dict:
    """Create scenes (pages) with camera presets or explicit cameras and hidden tags."""
    return _bridge("add_scenes", {"scenes": scenes})


@mcp.tool()
def df_export(format: str, path: str, options: dict | None = None, scene: str | None = None) -> dict:
    """Export the model (obj, stl, dxf) or a scene image (png) to a path inside the job directory."""
    return _bridge("export", {"format": format, "path": path, "options": options or {}, "scene": scene})


@mcp.tool()
def df_save(path: str, format: str = "skp", options: dict | None = None, scene: str | None = None) -> dict:
    """Save the model as .skp inside the job directory."""
    return _bridge("save", {"path": path})


@mcp.tool()
def df_model_stats() -> dict:
    """Bounding box (mm, X/Y/Z), instance and definition counts — used to verify a build."""
    return _bridge("model_stats", {})


if os.environ.get("DF_ALLOW_EVAL") == "1":
    @mcp.tool()
    def eval_ruby(code: str) -> dict:
        """DEBUG ONLY. Never enabled on production geometry nodes."""
        return _bridge("eval", {"code": code})


if __name__ == "__main__":
    mcp.run(transport="stdio")
