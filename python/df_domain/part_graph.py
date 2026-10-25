"""PartGraph — manufacturable model. Mirrors packages/contracts/src/part-graph.ts.

Axes: X width (left→right), Y depth (front→back), Z height (up). Origin front-left-floor. Units: mm.
Part-local: length → X, width → Y, thickness → Z, origin at min corner.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Mm = int
Grain = Literal["none", "length", "width"]
Face = Literal["top", "bottom", "front", "back", "left", "right"]
Edge = Literal["L1", "L2", "W1", "W2"]
Transform = tuple[float, ...]  # 16 floats, column-major

IDENTITY: Transform = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def translate(x: Mm, y: Mm, z: Mm) -> Transform:
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Drill(_M):
    kind: Literal["drill"] = "drill"
    face: Face
    x: Mm
    y: Mm
    diameter: Mm
    depth: Mm | Literal["through"]
    tool_hint: str | None = None
    source: str


class Groove(_M):
    kind: Literal["groove"] = "groove"
    face: Face
    x1: Mm
    y1: Mm
    x2: Mm
    y2: Mm
    width: Mm
    depth: Mm
    source: str


class Rebate(_M):
    kind: Literal["rebate"] = "rebate"
    edge: Edge
    face: Face
    width: Mm
    depth: Mm
    source: str


class Pocket(_M):
    kind: Literal["pocket"] = "pocket"
    face: Face
    polygon: list[tuple[Mm, Mm]]
    depth: Mm
    source: str


class Cutout(_M):
    kind: Literal["cutout"] = "cutout"
    polygon: list[tuple[Mm, Mm]]
    source: str


class EdgeProfile(_M):
    kind: Literal["edge_profile"] = "edge_profile"
    edge: Edge
    profile: str
    source: str


Operation = Annotated[Union[Drill, Groove, Rebate, Pocket, Cutout, EdgeProfile], Field(discriminator="kind")]


class Part(_M):
    key: str
    role: str
    label: str
    material_code: str
    length: Mm
    width: Mm
    thickness: Mm
    grain: Grain
    edge_band: dict[Edge, str | None] = Field(default_factory=dict)
    cut_length: Mm
    cut_width: Mm
    transform: Transform = IDENTITY
    assembly_path: str
    operations: list[Operation] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class HardwarePlacement(_M):
    hardware_code: str
    qty: int
    attached_to: list[str]
    transform: Transform | None = None
    params: dict = Field(default_factory=dict)


class Joint(_M):
    kind: Literal["minifix_dowel", "dowel_glue", "confirmat", "groove_fit", "screw"]
    parts: tuple[str, str]
    positions: list[Mm]


class AssemblyNode(_M):
    path: str
    label: str
    children: list[str] = Field(default_factory=list)
    part_keys: list[str] = Field(default_factory=list)


class BBox(_M):
    width: Mm
    height: Mm
    depth: Mm


class RulePackRef(_M):
    id: UUID
    version: int


class PartGraph(_M):
    schema_version: Literal["1.0"] = "1.0"
    spec_hash: str
    generator_version: str
    rule_pack: RulePackRef
    bbox: BBox
    parts: list[Part]
    hardware: list[HardwarePlacement] = Field(default_factory=list)
    joints: list[Joint] = Field(default_factory=list)
    assemblies: list[AssemblyNode] = Field(default_factory=list)
    graph_hash: str = ""

    def with_hash(self) -> "PartGraph":
        body = self.model_dump(mode="json", exclude={"graph_hash"})
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.model_copy(update={"graph_hash": digest})

    def part(self, key: str) -> Part:
        return next(p for p in self.parts if p.key == key)
