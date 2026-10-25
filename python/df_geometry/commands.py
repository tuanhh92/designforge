"""Wire commands for the SketchUp bridge (`df_execute_batch`). Units: mm. Validated on both sides."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

Transform = list[float]  # 16, column-major


class _C(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EnsureMaterial(_C):
    op: Literal["ensure_material"] = "ensure_material"
    code: str
    name: str
    color: str                         # "#RRGGBB"
    texture_url: str | None = None     # downloaded by agent into job dir; bridge gets local path
    texture_size_mm: tuple[int, int] | None = None
    grain_deg: int = 0


class EnsureTag(_C):
    op: Literal["ensure_tag"] = "ensure_tag"
    name: str
    visible: bool = True


class Hole(_C):
    face: Literal["top", "bottom", "front", "back", "left", "right"]
    x: int
    y: int
    d: int


class DefinePanel(_C):
    """A rectangular solid in part-local frame: length → X, width → Y, thickness → Z."""
    op: Literal["define_panel"] = "define_panel"
    def_key: str
    name: str
    length: int
    width: int
    thickness: int
    material: str
    holes: list[Hole] = Field(default_factory=list)   # drawn as circles (visual only, no booleans)
    attrs: dict = Field(default_factory=dict)         # written to AttributeDictionary "designforge"


class DefineProxy(_C):
    """Simple box proxy for hardware (hinge, slide, handle, leg) until real components are licensed."""
    op: Literal["define_proxy"] = "define_proxy"
    def_key: str
    name: str
    size: tuple[int, int, int]
    color: str
    attrs: dict = Field(default_factory=dict)


class Group(_C):
    op: Literal["group"] = "group"
    key: str
    name: str
    parent: str | None = None
    tag: str | None = None


class Place(_C):
    op: Literal["place"] = "place"
    def_key: str
    instance_key: str
    parent: str | None = None
    transform: Transform
    tag: str | None = None


class Paint(_C):
    op: Literal["paint"] = "paint"
    instance_key: str
    material: str


Command = Annotated[
    Union[EnsureMaterial, EnsureTag, DefinePanel, DefineProxy, Group, Place, Paint], Field(discriminator="op")
]


class Batch(_C):
    job_id: str
    commands: list[Command]


class Camera(_C):
    eye: tuple[int, int, int]
    target: tuple[int, int, int]
    up: tuple[int, int, int] = (0, 0, 1)
    perspective: bool = True
    fov_deg: int = 35


class SceneCmd(_C):
    name: str
    camera: Camera | Literal["front", "iso", "left", "top"]
    hidden_tags: list[str] = Field(default_factory=list)
    style: Literal["shaded_textures", "hidden_line", "xray"] = "shaded_textures"
    exploded: bool = False             # bridge offsets assemblies along their own axes for this scene


class ExportCmd(_C):
    format: Literal["skp", "obj", "stl", "dxf", "png"]
    path: str                          # inside job dir only; bridge enforces
    options: dict = Field(default_factory=dict)
    scene: str | None = None           # png only
