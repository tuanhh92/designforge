"""FurnitureSpec — design intent. Mirrors packages/contracts/src/furniture-spec.ts.

This module is the source of truth: `just schemas` exports these models to JSON Schema,
which generates the TS types and is reused as the LLM structured-output schema.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

Mm = Annotated[int, Field(ge=0, le=20_000, description="integer millimetres")]
AutoOrMm = Union[Mm, Literal["auto"]]

FurnitureCategory = Literal[
    "wardrobe", "base_cabinet", "wall_cabinet", "tall_cabinet", "kitchen_run", "tv_unit",
    "bookcase", "sideboard", "chest_of_drawers", "desk", "bed_frame", "shoe_cabinet", "vanity", "other",
]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MaterialRef(Frozen):
    code: str


class HardwareRef(Frozen):
    code: str


class Overall(Frozen):
    width: Mm
    height: Mm
    depth: Mm


class PlinthBase(Frozen):
    kind: Literal["plinth"] = "plinth"
    height: Mm
    setback: Mm
    material: MaterialRef


class LegsBase(Frozen):
    kind: Literal["legs"] = "legs"
    height: Mm
    leg: HardwareRef
    kickboard: bool


class NoBase(Frozen):
    kind: Literal["none"] = "none"


Base = Annotated[Union[PlinthBase, LegsBase, NoBase], Field(discriminator="kind")]


class BackPanel(Frozen):
    style: Literal["inset_groove", "rebated", "applied", "full_thickness", "none"]
    material: MaterialRef
    thickness: Mm
    groove_inset: Mm | None = None


class Overhang(Frozen):
    front: Mm = 0
    left: Mm = 0
    right: Mm = 0


class Scribe(Frozen):
    left: Mm = 0
    right: Mm = 0
    top: Mm = 0


class Construction(Frozen):
    carcass_material: MaterialRef
    carcass_thickness: Mm = 18
    joinery: Literal["top_over_gables", "gables_over_top"] = "gables_over_top"
    connector: Literal["minifix_dowel", "dowel_glue", "confirmat", "lamello_clamex"] = "minifix_dowel"
    back: BackPanel
    base: Base
    top_overhang: Overhang | None = None
    scribe_allowance: Scribe | None = None


class HandleHardware(Frozen):
    kind: Literal["handle"] = "handle"
    hardware: HardwareRef
    position: Literal["top", "middle", "bottom", "auto"] = "auto"


class PushToOpen(Frozen):
    kind: Literal["push_to_open"] = "push_to_open"
    hardware: HardwareRef


class GolaProfile(Frozen):
    kind: Literal["gola_profile"] = "gola_profile"
    hardware: HardwareRef


class IntegratedGroove(Frozen):
    kind: Literal["integrated_groove"] = "integrated_groove"
    depth: Mm


class NoHandle(Frozen):
    kind: Literal["none"] = "none"


Handle = Annotated[
    Union[HandleHardware, PushToOpen, GolaProfile, IntegratedGroove, NoHandle], Field(discriminator="kind")
]


class SlidingFronts(Frozen):
    """Sliding doors across the whole carcass width, on a double track inside the front of the carcass."""
    leaves: Literal[2, 3]
    track: HardwareRef
    overlap: Mm = 40  # how far neighbouring leaves overlap when closed


class Fronts(Frozen):
    # "sliding" = one set of sliding doors for the whole piece (see `sliding`); otherwise doors are per section
    style: Literal["overlay_full", "overlay_half", "inset", "sliding", "none"]
    material: MaterialRef
    thickness: Mm = 18
    reveal: Mm = 3
    handle: Handle
    hinge: HardwareRef | None = None
    sliding: SlidingFronts | None = None


class ShelvesCompartment(Frozen):
    kind: Literal["shelves"] = "shelves"
    height: AutoOrMm
    adjustable_shelves: NonNegativeInt
    fixed_top_shelf: bool = False


class HangingCompartment(Frozen):
    kind: Literal["hanging"] = "hanging"
    height: AutoOrMm
    rail: HardwareRef


class DrawersCompartment(Frozen):
    kind: Literal["drawers"] = "drawers"
    height: AutoOrMm
    count: PositiveInt
    slide: HardwareRef
    internal: bool = False
    front_heights: list[Mm] | None = None


class OpenCompartment(Frozen):
    kind: Literal["open"] = "open"
    height: AutoOrMm


class ApplianceCompartment(Frozen):
    kind: Literal["appliance"] = "appliance"
    height: AutoOrMm
    appliance: Literal["oven", "microwave", "dishwasher", "fridge", "sink"]


Compartment = Annotated[
    Union[ShelvesCompartment, HangingCompartment, DrawersCompartment, OpenCompartment, ApplianceCompartment],
    Field(discriminator="kind"),
]


class NoDoors(Frozen):
    kind: Literal["none"] = "none"


class HingedDoors(Frozen):
    kind: Literal["hinged"] = "hinged"
    leaves: Literal[1, 2]
    hinge_side: Literal["left", "right"] | None = None
    spans: tuple[NonNegativeInt, NonNegativeInt]


class SlidingDoors(Frozen):
    kind: Literal["sliding"] = "sliding"
    leaves: Literal[2, 3]
    track: HardwareRef
    spans: tuple[NonNegativeInt, NonNegativeInt]


class LiftUpDoor(Frozen):
    kind: Literal["lift_up"] = "lift_up"
    mechanism: HardwareRef
    spans: tuple[NonNegativeInt, NonNegativeInt]


DoorConfig = Annotated[Union[NoDoors, HingedDoors, SlidingDoors, LiftUpDoor], Field(discriminator="kind")]


class Section(Frozen):
    width: AutoOrMm
    compartments: list[Compartment] = Field(min_length=1, description="bottom → top")
    doors: list[DoorConfig] = Field(default_factory=list)


class StyleInfo(Frozen):
    tags: list[str] = Field(default_factory=list)
    finish: str = ""
    colour_hex: str | None = None


class RulePackRef(Frozen):
    id: UUID
    version: PositiveInt


class FurnitureSpec(Frozen):
    schema_version: Literal["1.0"] = "1.0"
    category: FurnitureCategory
    name: str
    overall: Overall
    construction: Construction
    fronts: Fronts
    sections: list[Section] = Field(min_length=1, description="left → right")
    style: StyleInfo = StyleInfo()
    rule_pack: RulePackRef
    notes: list[str] = Field(default_factory=list)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def spec_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class SpecIssue(Frozen):
    rule_code: str
    severity: Literal["info", "warning", "error"]
    path: str  # JSON pointer
    message: str                          # English fallback
    params: dict = Field(default_factory=dict)  # values for the UI's localized template keyed by rule_code
    suggestion: list[dict] | None = None  # RFC 6902 ops
