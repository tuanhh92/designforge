"""GeometryEngine port and the PartGraph → command compiler (engine-independent)."""
from __future__ import annotations

import hashlib
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, Sequence

from df_domain.part_graph import Part, PartGraph
from df_domain.ports import Catalog

from .commands import (
    Command, DefinePanel, EnsureMaterial, EnsureTag, ExportCmd, Group, Hole, Place, SceneCmd,
)

ExportFormat = Literal["skp", "obj", "stl", "dxf", "png"]


@dataclass(frozen=True)
class EngineCapabilities:
    name: str
    exports: frozenset[ExportFormat]
    supports_scenes: bool
    max_parts: int
    version: str                       # e.g. "sketchup-bridge@0.2.0/SU26.0"


@dataclass(frozen=True)
class EngineHealth:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class BuildRequest:
    job_id: str
    exports: Sequence[ExportFormat]
    scenes: Sequence[SceneCmd]
    out_dir: Path


@dataclass
class BuildResult:
    files: dict[str, Path]             # "skp" → path, "png:Front" → path …
    bbox_mm: tuple[int, int, int]
    part_count: int
    stats: dict = field(default_factory=dict)


class ModelSession(Protocol):
    """Fine-grained capability surface. Higher-level macros compile down to these."""
    async def new_model(self) -> None: ...
    async def execute(self, commands: Sequence[Command]) -> dict: ...
    async def create_panel(self, cmd: DefinePanel, place: Place) -> dict: ...
    async def apply_material(self, instance_key: str, material: EnsureMaterial) -> None: ...
    async def add_scenes(self, scenes: Sequence[SceneCmd]) -> None: ...
    async def export(self, cmd: ExportCmd) -> Path: ...
    async def model_stats(self) -> dict: ...


class GeometryEngine(Protocol):
    name: str
    def capabilities(self) -> EngineCapabilities: ...
    async def health(self) -> EngineHealth: ...
    def session(self) -> AbstractAsyncContextManager[ModelSession]: ...
    async def build(self, graph: PartGraph, request: BuildRequest) -> BuildResult: ...


# ── Compiler ─────────────────────────────────────────────────────────────────

TAG_BY_ROLE = {
    "door": "DF_Fronts", "drawer_front": "DF_Fronts", "sliding_door": "DF_Fronts", "back": "DF_Back",
    "sliding_track": "DF_Hardware", "hanging_rail": "DF_Hardware",
}

DEFAULT_SCENES: list[SceneCmd] = [
    SceneCmd(name="Iso", camera="iso"),
    SceneCmd(name="Front", camera="front", style="hidden_line"),
    SceneCmd(name="Interior", camera="front", hidden_tags=["DF_Fronts"]),
    SceneCmd(name="Exploded", camera="iso", exploded=True),
]


def _def_key(p: Part) -> str:
    """Identical geometry + material + machining ⇒ shared ComponentDefinition."""
    holes = ",".join(f"{o.face}{o.x}:{o.y}:{o.diameter}" for o in p.operations if o.kind == "drill")
    digest = hashlib.sha1(holes.encode()).hexdigest()[:8]  # not hash(): randomised per process
    return f"p:{p.length}x{p.width}x{p.thickness}:{p.material_code}:{digest}"


class PartGraphCompiler:
    """PartGraph → ordered bridge commands. Deterministic; unit-tested without SketchUp."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    def compile(self, graph: PartGraph) -> list[Command]:
        cmds: list[Command] = [EnsureTag(name=t) for t in ("DF_Carcass", "DF_Fronts", "DF_Back", "DF_Hardware")]
        for code in sorted({p.material_code for p in graph.parts}):
            m = self.catalog.material(code)
            cmds.append(EnsureMaterial(code=code, name=m.sketchup_material_name, color=m.colour_hex,
                                       grain_deg=0 if m.grain != "width" else 90))
        for a in sorted(graph.assemblies, key=lambda a: a.path.count("/")):
            parent = a.path.rsplit("/", 1)[0] if "/" in a.path else None
            cmds.append(Group(key=a.path, name=a.label, parent=parent))
        defined: set[str] = set()
        for p in graph.parts:
            dk = _def_key(p)
            if dk not in defined:
                defined.add(dk)
                cmds.append(DefinePanel(
                    def_key=dk, name=p.label, length=p.length, width=p.width, thickness=p.thickness,
                    material=p.material_code,
                    holes=[Hole(face=o.face, x=o.x, y=o.y, d=o.diameter) for o in p.operations if o.kind == "drill"],
                    attrs={"role": p.role, "cut_length": p.cut_length, "cut_width": p.cut_width,
                           "grain": p.grain, "edge_band": p.edge_band}))
            cmds.append(Place(def_key=dk, instance_key=p.key, parent=p.assembly_path,
                              transform=list(orient_transform(p)), tag=TAG_BY_ROLE.get(p.role, "DF_Carcass")))
        return cmds


def orient_transform(p: Part) -> tuple[float, ...]:
    """World transform = placement (min corner) composed with the rotation implied by the orient tag.
    All are proper rotations (det = +1) — a mirror would flip face normals in SketchUp.
      xy : flat (tops, shelves)           length→X, width→Y, thickness→Z
      yz : standing on edge (gables)      length→Z, width→Y, thickness→X
      xz : vertical, length up (doors)    length→Z, width→X, thickness→Y
      xzh: vertical, length across (backs, plinths)  length→X, width→Z, thickness→Y
    The placement is the world min corner, so axes mapped to a negative direction shift by thickness."""
    tx, ty, tz = p.transform[12], p.transform[13], p.transform[14]
    t = p.thickness
    orient = next((tag.split(":", 1)[1] for tag in p.tags if tag.startswith("orient:")), "xy")
    if orient == "yz":   # cols: X→+Z, Y→+Y, Z→−X
        return (0, 0, 1, 0, 0, 1, 0, 0, -1, 0, 0, 0, tx + t, ty, tz, 1)
    if orient == "xz":   # cols: X→+Z, Y→+X, Z→+Y
        return (0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, tx, ty, tz, 1)
    if orient == "xzh":  # cols: X→+X, Y→+Z, Z→−Y
        return (1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, tx, ty + t, tz, 1)
    return tuple(p.transform)


def parts_extent(graph: PartGraph) -> tuple[int, int, int]:
    """(X, Y, Z) size in mm of the panels actually drawn. This is what a geometry engine can measure;
    it differs from graph.bbox when the overall size includes undrawn hardware such as legs."""
    boxes = [world_aabb(p) for p in graph.parts]
    return tuple(round(max(b[1][i] for b in boxes) - min(b[0][i] for b in boxes)) for i in range(3))  # type: ignore[return-value]


def world_aabb(p: Part) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    m = orient_transform(p)
    corners = [(x, y, z) for x in (0, p.length) for y in (0, p.width) for z in (0, p.thickness)]
    pts = [tuple(m[i] * x + m[4 + i] * y + m[8 + i] * z + m[12 + i] for i in range(3)) for x, y, z in corners]
    return tuple(min(c[i] for c in pts) for i in range(3)), tuple(max(c[i] for c in pts) for i in range(3))  # type: ignore[return-value]
