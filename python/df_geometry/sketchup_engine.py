"""SketchUpMcpEngine — GeometryEngine adapter that drives SketchUp through the forked MCP server."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Sequence

from df_domain.part_graph import PartGraph
from df_domain.ports import Catalog

from .commands import Command, DefinePanel, EnsureMaterial, ExportCmd, Paint, Place, SceneCmd
from .engine import (
    DEFAULT_SCENES, BuildRequest, BuildResult, EngineCapabilities, EngineHealth, PartGraphCompiler, parts_extent,
)
from .mcp_client import McpServerConfig, McpSketchUpClient, SketchUpMcpError

CHUNK = 400  # commands per df_execute_batch call
REQUIRED_EXPORTS = {"skp", "png"}  # OBJ/STL/DXF depend on exporters a SketchUp edition may not ship


class _Session:
    """ModelSession over an open MCP client."""

    def __init__(self, client: McpSketchUpClient, job_id: str):
        self.c, self.job_id = client, job_id

    async def new_model(self) -> None:
        await self.c.call("df_new_model", {"template": "designforge_mm"})

    async def execute(self, commands: Sequence[Command]) -> dict:
        stats: dict = {"created": 0}
        for i in range(0, len(commands), CHUNK):
            chunk = [c.model_dump(mode="json") for c in commands[i:i + CHUNK]]
            res = await self.c.call("df_execute_batch", {"job_id": self.job_id, "commands": chunk})
            stats["created"] += res.get("created", 0)
        return stats

    async def create_panel(self, cmd: DefinePanel, place: Place) -> dict:
        return await self.execute([cmd, place])

    async def apply_material(self, instance_key: str, material: EnsureMaterial) -> None:
        await self.execute([material, Paint(instance_key=instance_key, material=material.code)])

    async def add_scenes(self, scenes: Sequence[SceneCmd]) -> None:
        await self.c.call("df_add_scenes", {"scenes": [s.model_dump(mode="json") for s in scenes]})

    async def export(self, cmd: ExportCmd) -> Path:
        tool = "df_save" if cmd.format == "skp" else "df_export"
        res = await self.c.call(tool, cmd.model_dump(mode="json"))
        return Path(res["path"])

    async def model_stats(self) -> dict:
        return await self.c.call("df_model_stats", {})


class SketchUpMcpEngine:
    name = "sketchup_mcp"

    def __init__(self, cfg: McpServerConfig, catalog: Catalog, version: str):
        self.cfg, self.catalog, self._version = cfg, catalog, version

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(self.name, frozenset({"skp", "obj", "stl", "dxf", "png"}),
                                  supports_scenes=True, max_parts=5000, version=self._version)

    async def health(self) -> EngineHealth:
        try:
            async with McpSketchUpClient(self.cfg) as c:
                return EngineHealth(True, f"bridge {c.bridge_info.get('bridge_version')} / SU {c.bridge_info.get('sketchup_version')}")
        except Exception as e:  # noqa: BLE001 — health must never raise
            return EngineHealth(False, repr(e))

    @asynccontextmanager
    async def session(self, job_id: str = "interactive"):
        async with McpSketchUpClient(self.cfg) as client:
            yield _Session(client, job_id)

    async def build(self, graph: PartGraph, request: BuildRequest) -> BuildResult:
        commands = PartGraphCompiler(self.catalog).compile(graph)
        files: dict[str, Path] = {}
        async with self.session(request.job_id) as s:
            await s.new_model()
            await s.execute(commands)
            await s.add_scenes(request.scenes or DEFAULT_SCENES)
            stats = await s.model_stats()
            bbox = tuple(stats["bbox_mm"])
            expected = parts_extent(graph)  # not graph.bbox: legs and other hardware are not drawn
            if any(abs(a - b) > 1 for a, b in zip(bbox, expected)):
                raise SketchUpMcpError("verify", f"bbox {bbox} != parts extent {expected}", retryable=False)
            if stats["instance_count"] != len(graph.parts):
                raise SketchUpMcpError("verify", f"{stats['instance_count']} instances != {len(graph.parts)} parts", retryable=False)
            out = request.out_dir
            # Save first: if a later exporter crashes SketchUp, the .skp is already on disk.
            skipped: dict[str, str] = {}
            for fmt in sorted(request.exports, key=["skp", "png", "obj", "stl", "dxf"].index):
                try:
                    if fmt == "png":
                        for scene in request.scenes or DEFAULT_SCENES:
                            files[f"png:{scene.name}"] = await s.export(ExportCmd(
                                format="png", path=str(out / f"{scene.name}.png"), scene=scene.name,
                                options={"width": 1920, "height": 1080, "antialias": True}))
                    else:
                        files[fmt] = await s.export(ExportCmd(format=fmt, path=str(out / f"model.{fmt}")))
                except SketchUpMcpError as e:
                    if fmt in REQUIRED_EXPORTS:
                        raise
                    skipped[fmt] = str(e)
            stats = {**stats, "skipped_exports": skipped}
        return BuildResult(files=files, bbox_mm=bbox, part_count=len(graph.parts), stats=stats)  # type: ignore[arg-type]
