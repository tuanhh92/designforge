"""Stage 1 output. Deliberately contains ratios and cues, not absolute millimetres."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .spec import FurnitureCategory

Confidence = float  # 0..1


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scored(_M):
    confidence: Confidence = Field(ge=0, le=1)
    evidence: str = Field(description="what in the image supports this, ≤ 25 words")


class CategoryGuess(Scored):
    value: FurnitureCategory


class CountGuess(Scored):
    value: int = Field(ge=0)


class RatioGuess(Scored):
    value: float = Field(gt=0, description="e.g. width/height of the front elevation")


class FrontRect(_M):
    """Normalised rectangle in FRONT-ELEVATION space (0..1, origin bottom-left)."""
    x0: float
    y0: float
    x1: float
    y1: float
    kind: Literal["door", "sliding_door", "drawer_front", "open", "fixed_panel", "glass_door", "appliance"]
    handle_side: Literal["left", "right", "top", "bottom", "none"] = "none"


class ScaleCue(_M):
    kind: Literal["worktop", "socket_outlet", "door_frame", "ceiling", "person", "floor_tile",
                  "skirting", "handle", "printed_dimension", "other"]
    description: str
    implied_dimension: Literal["width", "height", "depth", "section_width", "door_height"]
    implied_value_mm: int | None = None
    confidence: Confidence


class MaterialGuess(Scored):
    surface: Literal["melamine", "laminate", "veneer", "lacquer", "solid_wood", "glass", "metal", "fabric", "other"]
    colour_name: str
    colour_hex: str | None = None
    applies_to: Literal["carcass", "fronts", "top", "all"]


class ImageObservation(_M):
    view: Literal["front", "three_quarter", "side", "top", "detail", "unknown"]
    image_kind: Literal["photo", "render", "sketch", "product_page", "other"]
    category: CategoryGuess
    width_to_height: RatioGuess
    depth_to_width: RatioGuess | None = None
    section_count: CountGuess
    section_width_shares: list[float] = Field(description="left→right, sums to 1")
    fronts: list[FrontRect]
    door_count: CountGuess
    drawer_count: CountGuess
    visible_shelf_count: CountGuess
    base_type: Literal["plinth", "legs", "none", "unknown"]
    handle_type: Literal["handle", "knob", "push_to_open", "gola_profile", "integrated_groove", "none", "unknown"]
    materials: list[MaterialGuess]
    scale_cues: list[ScaleCue]
    printed_text: list[str] = Field(default_factory=list, description="verbatim OCR of dimension text")
    style_tags: list[str]
    construction_hints: list[str] = Field(default_factory=list, description="e.g. 'top sits on sides', 'visible 32mm holes'")
    review_hints: list[str] = Field(default_factory=list)
