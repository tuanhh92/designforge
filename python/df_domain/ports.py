"""Ports (hexagonal architecture). The domain depends only on these Protocols.

Adapters live in df_ai, df_geometry, df_manufacturing, df_drawings, df_infra.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence
from uuid import UUID

from .observation import ImageObservation
from .part_graph import PartGraph
from .spec import FurnitureSpec, SpecIssue

# ── Catalog / rules ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MaterialInfo:
    code: str
    kind: str
    thickness: int
    grain: Literal["none", "length", "width"]
    price_per_unit_minor: int | None
    sketchup_material_name: str
    colour_hex: str


@dataclass(frozen=True)
class HardwareInfo:
    code: str
    family: str
    params: dict
    drilling: list[dict]
    price_minor: int | None


class Catalog(Protocol):
    def material(self, code: str) -> MaterialInfo: ...
    def hardware(self, code: str) -> HardwareInfo: ...
    def edge_band_for(self, material_code: str, thickness: int) -> str: ...
    def material_codes(self, kind: str | None = None) -> list[str]: ...
    def hardware_codes(self, family: str | None = None) -> list[str]: ...


class RulePack(Protocol):
    id: UUID
    version: int
    def get(self, key: str, default=None): ...  # e.g. rules.get("system32.front_setback", 37)


# ── Domain services ──────────────────────────────────────────────────────────

class SpecValidator(Protocol):
    def validate(self, spec: FurnitureSpec, rules: RulePack, catalog: Catalog) -> list[SpecIssue]: ...


class ParametricGenerator(Protocol):
    """Pure function. MUST be deterministic: same inputs ⇒ identical graph_hash."""
    version: str
    def generate(self, spec: FurnitureSpec, rules: RulePack, catalog: Catalog) -> PartGraph: ...


# ── AI ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ImageInput:
    image_id: UUID
    url: str              # short-lived signed URL, or data URL
    role: str
    user_notes: str | None = None
    focus_point: tuple[float, float] | None = None


class PerceptionService(Protocol):
    async def observe(self, images: Sequence[ImageInput], hint_category: str | None) -> ImageObservation: ...


class SpecDrafter(Protocol):
    async def draft(
        self, observation: ImageObservation, anchors: list[dict], rules: RulePack, catalog: Catalog
    ) -> tuple[FurnitureSpec, dict[str, dict]]:  # (spec, field_confidence)
        ...


# ── Geometry (see df_geometry.engine for the full GeometryEngine port) ───────

class GeometryEngineRef(Protocol):
    name: str
    async def build(self, graph: PartGraph, exports: Sequence[str]) -> dict[str, bytes]: ...


# ── Manufacturing & documentation ────────────────────────────────────────────

class Nester(Protocol):
    algorithm: str
    def nest(self, items: list[dict], sheet: dict, kerf: int, allow_rotate_grain: bool) -> list[dict]: ...


class CncPostProcessor(Protocol):
    dialect: Literal["dxf_generic", "homag_mpr", "biesse_bpp", "scm_xxl"]
    def program_for_part(self, part_key: str, graph: PartGraph) -> tuple[str, bytes]: ...  # (filename, content)


class DrawingRenderer(Protocol):
    def render(self, graph: PartGraph, spec: FurnitureSpec, template: str) -> list[tuple[str, bytes]]: ...


# ── Infrastructure ───────────────────────────────────────────────────────────

class BlobStore(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> str: ...
    def signed_url(self, path: str, ttl_s: int = 300) -> str: ...
    def signed_upload_url(self, path: str, ttl_s: int = 900) -> str: ...


class EventPublisher(Protocol):
    """Writes to the outbox inside the caller's DB transaction."""
    def emit(self, type: str, aggregate_id: UUID, payload: dict) -> None: ...
