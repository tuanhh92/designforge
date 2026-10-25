"""Geometry stage: PartGraph → files.

Always produced (Linux, milliseconds): model.glb (web viewer), part_graph.json, parts.csv.
With GEOMETRY_ENGINE=sketchup_mcp: SketchUp builds the model through the DesignForge MCP server
→ model.skp, scene PNGs, OBJ, STL.
"""
from __future__ import annotations

import csv
import io
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from df_domain.part_graph import PartGraph
from df_geometry.engine import BuildRequest
from df_geometry.gltf import part_graph_to_glb
from df_geometry.mcp_client import McpServerConfig, SketchUpMcpError
from df_geometry.sketchup_engine import SketchUpMcpEngine

from .catalog import DefaultCatalog
from .config import Settings

MIME = {"glb": "model/gltf-binary", "skp": "application/vnd.sketchup.skp", "obj": "model/obj",
        "stl": "model/stl", "png": "image/png", "json": "application/json", "csv": "text/csv", "dxf": "image/vnd.dxf"}


@dataclass(frozen=True)
class OutputFile:
    kind: str
    name: str
    data: bytes
    mime: str
    producer: str


def web_outputs(graph: PartGraph) -> list[OutputFile]:
    catalog = DefaultCatalog()
    return [
        OutputFile("glb", "model.glb", part_graph_to_glb(graph, catalog), MIME["glb"], "df_geometry.gltf@1"),
        OutputFile("part_graph", "part_graph.json", graph.model_dump_json(indent=2).encode(), MIME["json"], graph.generator_version),
        OutputFile("parts_csv", "parts.csv", parts_csv(graph), MIME["csv"], graph.generator_version),
    ]


def parts_csv(graph: PartGraph) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["key", "label", "role", "material", "length_mm", "width_mm", "thickness_mm",
                "cut_length_mm", "cut_width_mm", "grain", "band_L1", "band_L2", "band_W1", "band_W2", "operations"])
    for p in graph.parts:
        eb = p.edge_band
        w.writerow([p.key, p.label, p.role, p.material_code, p.length, p.width, p.thickness, p.cut_length, p.cut_width,
                    p.grain, eb.get("L1") or "", eb.get("L2") or "", eb.get("W1") or "", eb.get("W2") or "", len(p.operations)])
    return out.getvalue().encode()


def mcp_config(settings: Settings) -> McpServerConfig:
    command = settings.sketchup_mcp_command
    if command in ("python", "python3"):
        command = sys.executable  # the server runs in the same venv as the worker (needs `mcp`)
    port, token, _ = settings.bridge()
    return McpServerConfig(
        command=command,
        args=tuple(shlex.split(settings.sketchup_mcp_args)),
        env={"DF_BRIDGE_PORT": str(port), "DF_BRIDGE_TOKEN": token, "DF_ALLOW_EVAL": "0"},
        call_timeout_s=180,
    )


async def sketchup_outputs(graph: PartGraph, settings: Settings, job_id: str,
                           on_phase: Callable[[str, str, dict], None]) -> list[OutputFile]:
    """on_phase(english_message, code, params) reports progress."""
    _, token, job_root = settings.bridge()
    if not token:
        raise SketchUpMcpError("config", f"no bridge token: run `make bridge-setup` ({settings.df_bridge_config})",
                               retryable=False)
    out_dir = job_root / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = SketchUpMcpEngine(mcp_config(settings), DefaultCatalog(), version="sketchup-mcp")
    on_phase("Connecting to SketchUp via MCP", "sketchup.connecting", {})
    result = await engine.build(graph, BuildRequest(job_id=job_id, exports=["skp", "png", "obj", "stl"],
                                                    scenes=[], out_dir=out_dir))
    bbox = " × ".join(str(v) for v in result.bbox_mm)
    on_phase(f"SketchUp built {result.part_count} parts, bbox {bbox} mm", "sketchup.built",
             {"parts": result.part_count, "bbox": bbox})
    files: list[OutputFile] = []
    producer = f"sketchup-bridge/{result.stats.get('bridge_version', '?')}"
    for key, path in result.files.items():
        p = Path(path)
        kind = key.split(":", 1)[0]
        name = p.name if kind != "png" else f"scene-{p.stem}.png"
        files.append(OutputFile(kind, name, p.read_bytes(), MIME.get(kind, "application/octet-stream"), producer))
    return files
