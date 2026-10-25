"""Stage 3: sectioned carcass (gables-over-top) with dividers, inset-groove back, plinth, and per section a
stack of compartments (adjustable shelves on the 32 mm system, hanging rail) separated by fixed shelves.

Fronts: full/half-overlay hinged doors per section, or one set of sliding doors across the whole width
running on a double track in a zone at the front of the carcass (top and bottom aluminium rails).

Drawers and top-over-gables are separate builders following the same pattern.

Invariants: integer mm only, no randomness, no I/O, parts emitted in a stable order.
"""
from __future__ import annotations

from dataclasses import dataclass

from df_domain.part_graph import (
    AssemblyNode, BBox, Drill, Groove, HardwarePlacement, Joint, Part, PartGraph, RulePackRef, translate,
)
from df_domain.ports import Catalog, RulePack
from df_domain.spec import FurnitureSpec, HangingCompartment, HingedDoors, PlinthBase, ShelvesCompartment

VERSION = "df_parametric.carcass@0.2.0"


@dataclass(frozen=True)
class Ctx:
    spec: FurnitureSpec
    rules: RulePack
    catalog: Catalog

    def r(self, key: str, default: int) -> int:
        return int(self.rules.get(key, default))


def _band(ctx: Ctx, material_code: str) -> tuple[str, int]:
    thickness = ctx.r("edge_band.visible_thickness", 1)
    return ctx.catalog.edge_band_for(material_code, thickness), thickness


def _panel(ctx: Ctx, *, key: str, role: str, label: str, material: str, length: int, width: int,
           thickness: int, banded: tuple[str, ...], at: tuple[int, int, int], path: str,
           ops: list | None = None, grain: str = "length", tags: list[str] | None = None,
           rotate_to: str = "xy") -> Part:
    """Finished size in, cut size computed from banded edges (L-edges reduce width, W-edges reduce length)."""
    band_code, band_t = _band(ctx, material)
    premill = ctx.r("edge_band.premill", 0)
    cut_l = length - sum(band_t + premill for e in banded if e.startswith("W"))
    cut_w = width - sum(band_t + premill for e in banded if e.startswith("L"))
    return Part(
        key=key, role=role, label=label, material_code=material, length=length, width=width,
        thickness=thickness, grain=grain,  # type: ignore[arg-type]
        edge_band={e: (band_code if e in banded else None) for e in ("L1", "L2", "W1", "W2")},  # type: ignore[misc]
        cut_length=cut_l, cut_width=cut_w, transform=translate(*at), assembly_path=path,
        operations=ops or [], tags=(tags or []) + [f"orient:{rotate_to}"],
    )


def _profile(*, key: str, role: str, label: str, material: str, length: int, width: int, height: int,
             at: tuple[int, int, int], path: str) -> Part:
    """Aluminium profile (track, rail): cut to length, no edge banding, lying flat along X."""
    return Part(key=key, role=role, label=label, material_code=material, length=length, width=width,
                thickness=height, grain="none", edge_band={}, cut_length=length, cut_width=width,
                transform=translate(*at), assembly_path=path, tags=["profile", "orient:xy"])


def section_widths(spec: FurnitureSpec) -> list[int]:
    """Clear width of each section, left → right. "auto" sections share what fixed ones leave."""
    t = spec.construction.carcass_thickness
    secs = spec.sections
    available = spec.overall.width - 2 * t - t * (len(secs) - 1)
    fixed = sum(s.width for s in secs if s.width != "auto")
    autos = [i for i, s in enumerate(secs) if s.width == "auto"]
    rest = available - fixed
    widths = [s.width if s.width != "auto" else 0 for s in secs]
    for n, i in enumerate(autos):  # distribute remainder deterministically, leftmost gets the extra mm
        widths[i] = rest // len(autos) + (1 if n < rest % len(autos) else 0)
    if sum(widths) != available:
        raise ValueError(f"section widths {widths} do not fill {available} mm")  # caught by Rule Engine earlier
    return widths  # type: ignore[return-value]


def compartment_heights(compartments: list, clear_h: int, t: int) -> list[int]:
    """Clear height of each compartment, bottom → top. A fixed shelf (thickness t) separates neighbours."""
    available = clear_h - t * (len(compartments) - 1)
    fixed = sum(c.height for c in compartments if c.height != "auto")
    autos = [i for i, c in enumerate(compartments) if c.height == "auto"]
    heights = [c.height if c.height != "auto" else 0 for c in compartments]
    rest = available - fixed
    for n, i in enumerate(autos):
        heights[i] = rest // len(autos) + (1 if n < rest % len(autos) else 0)
    if sum(heights) != available or min(heights) <= 0:
        raise ValueError(f"compartment heights {heights} do not fill {available} mm")
    return heights  # type: ignore[return-value]


def front_zone_depth(spec: FurnitureSpec, rules: RulePack) -> int:
    """Depth at the front of the carcass reserved for sliding doors and their tracks (0 for hinged)."""
    return int(rules.get("sliding.track_depth", 90)) if spec.fronts.style == "sliding" else 0


def _system32(ctx: Ctx, depth: int, z_from: int, z_to: int, face: str, front: int) -> list[Drill]:
    """Line-bore rows on a gable: front row 37 mm behind the usable front, back row 37 mm before the back."""
    setback = ctx.r("system32.front_setback", 37)
    back_row = depth - ctx.r("back.groove_inset", 16) - ctx.r("back.thickness", 8) - setback
    holes = []
    z = z_from + (32 - (z_from % 32)) % 32
    while z <= z_to:
        for y in (front + setback, back_row):
            holes.append(Drill(face=face, x=z, y=y, diameter=5, depth=13, tool_hint="D5", source="system32"))  # type: ignore[arg-type]
        z += 32
    return holes


def generate(spec: FurnitureSpec, rules: RulePack, catalog: Catalog) -> PartGraph:
    ctx = Ctx(spec, rules, catalog)
    c = spec.construction
    t = c.carcass_thickness
    mat = c.carcass_material.code
    W, H, D = spec.overall.width, spec.overall.height, spec.overall.depth
    base_h = getattr(c.base, "height", 0)
    sliding = spec.fronts.style == "sliding"
    front_t = spec.fronts.thickness if spec.fronts.style.startswith("overlay") else 0
    reveal = spec.fronts.reveal
    carcass_d = D - front_t            # sliding doors sit inside the carcass depth
    zone = front_zone_depth(spec, rules)  # internals start behind the sliding-door zone
    carcass_h = H - base_h
    groove_inset = ctx.r("back.groove_inset", 16)
    groove_depth = ctx.r("back.groove_depth", 10)
    back_t = c.back.thickness
    inner_d = carcass_d - groove_inset - back_t - zone   # depth available to dividers and fixed shelves

    parts: list[Part] = []
    hardware: list[HardwarePlacement] = []
    joints: list[Joint] = []
    assemblies: list[AssemblyNode] = [AssemblyNode(path="carcass", label="Carcass")]
    joint_kind = c.connector if c.connector != "lamello_clamex" else "dowel_glue"

    def back_groove(length: int) -> Groove:
        y = carcass_d - groove_inset - back_t
        return Groove(face="right", x1=0, y1=y, x2=length, y2=y, width=back_t + 1, depth=groove_depth, source="back:inset_groove")  # type: ignore[arg-type]

    # Gables (full carcass height, gables-over-top)
    inner_z0, inner_z1 = t, carcass_h - t
    for side, x in (("l", 0), ("r", W - t)):
        face = "right" if side == "l" else "left"
        parts.append(_panel(
            ctx, key=f"gable_{side}", role="gable", label=f"Gable {side.upper()}", material=mat,
            length=carcass_h, width=carcass_d, thickness=t, banded=("L1",), at=(x, 0, base_h),
            path="carcass", ops=[back_groove(carcass_h), *_system32(ctx, carcass_d, inner_z0 + 64, inner_z1 - 64, face, zone)],
            rotate_to="yz", tags=["visible"]))

    # Top & bottom between gables
    inner_w = W - 2 * t
    for role, z in (("bottom", base_h), ("top", base_h + carcass_h - t)):
        parts.append(_panel(
            ctx, key=role, role=role, label=role.capitalize(), material=mat, length=inner_w, width=carcass_d,
            thickness=t, banded=("L1",), at=(t, 0, z), path="carcass", ops=[back_groove(inner_w)]))
        for g in ("gable_l", "gable_r"):
            joints.append(Joint(kind=joint_kind, parts=(g, role),  # type: ignore[arg-type]
                                positions=[50, carcass_d // 2, carcass_d - 50 - groove_inset]))

    # Back in grooves
    parts.append(_panel(
        ctx, key="back", role="back", label="Back", material=c.back.material.code,
        length=inner_w + 2 * (groove_depth - 1), width=carcass_h - 2 * t + 2 * (groove_depth - 1),
        thickness=back_t, banded=(), at=(t - groove_depth + 1, carcass_d - groove_inset - back_t, base_h + t - groove_depth + 1),
        path="carcass", grain="none", rotate_to="xzh"))

    # Sections: divider, compartments (bottom → top) separated by fixed shelves, hinged doors
    widths = section_widths(spec)
    clear_h = carcass_h - 2 * t
    setback = ctx.r("shelf.front_setback", 20)
    shelf_d = inner_d - setback
    pin_code = ctx.rules.get("hardware.shelf_pin", "SHELF-PIN-5")
    x = t
    for si, (sec, sw) in enumerate(zip(spec.sections, widths), start=1):
        path = f"carcass/section_{si}"
        assemblies.append(AssemblyNode(path=path, label=f"Section {si}"))
        if si > 1:  # divider on the left of this section
            parts.append(_panel(
                ctx, key=f"s{si}.divider", role="divider", label=f"Divider S{si-1}|S{si}", material=mat,
                length=clear_h, width=inner_d, thickness=t, banded=("L1",),
                at=(x - t, zone, base_h + t), path=path, rotate_to="yz"))

        heights = compartment_heights(list(sec.compartments), clear_h, t)
        zb = base_h + t
        for ci, (comp, ch) in enumerate(zip(sec.compartments, heights)):
            zt = zb + ch
            if isinstance(comp, ShelvesCompartment):
                # Default positions: evenly spaced over the compartment, snapped to the 32 mm pin grid
                gap = ch // (comp.adjustable_shelves + 1) if comp.adjustable_shelves else 0
                for n in range(comp.adjustable_shelves):
                    key = f"s{si}.c{ci}.shelf{n + 1}"
                    z = zb + round(gap * (n + 1) / 32) * 32 - t // 2
                    label = f"Shelf S{si}-{n + 1}" if len(sec.compartments) == 1 else f"Shelf S{si}-{ci + 1}.{n + 1}"
                    parts.append(_panel(
                        ctx, key=key, role="adjustable_shelf", label=label, material=mat,
                        length=sw - ctx.r("shelf.side_clearance", 2), width=shelf_d, thickness=t, banded=("L1",),
                        at=(x + 1, zone + setback, z), path=path, tags=["position_adjustable"]))
                    hardware.append(HardwarePlacement(hardware_code=pin_code, qty=4, attached_to=[key]))
            elif isinstance(comp, HangingCompartment):
                key = f"s{si}.c{ci}.rail"
                rail_w, rail_h = 15, 30  # oval rail section, mm
                parts.append(_profile(
                    key=key, role="hanging_rail", label=f"Hanging rail S{si}-{ci + 1}",
                    material="ALU-OVAL", length=sw - 4, width=rail_w, height=rail_h,
                    at=(x + 2, zone + (inner_d - rail_w) // 2, zt - ctx.r("hanging.rail_from_top", 60)), path=path))
                hardware.append(HardwarePlacement(
                    hardware_code=ctx.rules.get("hardware.rail_support", "RAIL-SUPPORT"), qty=2, attached_to=[key]))
            if ci < len(sec.compartments) - 1:  # fixed shelf closing this compartment
                key = f"s{si}.fixed{ci + 1}"
                parts.append(_panel(
                    ctx, key=key, role="fixed_shelf", label=f"Fixed shelf S{si}-{ci + 1}", material=mat,
                    length=sw, width=inner_d, thickness=t, banded=("L1",), at=(x, zone, zt), path=path))
                left = "gable_l" if si == 1 else f"s{si}.divider"
                right = "gable_r" if si == len(spec.sections) else f"s{si + 1}.divider"
                for side in (left, right):
                    joints.append(Joint(kind=joint_kind, parts=(side, key), positions=[50, inner_d - 50]))  # type: ignore[arg-type]
                zb = zt + t
        if not sliding:
            for door in sec.doors:
                if isinstance(door, HingedDoors):
                    _hinged_doors(ctx, door, si, x, sw, base_h, carcass_h, reveal, parts, hardware)
        x += sw + t

    if sliding:
        _sliding_doors(ctx, inner_w, base_h, carcass_h, zone, parts, hardware, assemblies)

    # Plinth
    if isinstance(c.base, PlinthBase):
        parts.append(_panel(
            ctx, key="plinth_front", role="plinth_front", label="Plinth front", material=c.base.material.code,
            length=W, width=c.base.height, thickness=t, banded=("L1",), at=(0, c.base.setback, 0),
            path="carcass", rotate_to="xzh", tags=["visible"]))

    graph = PartGraph(
        spec_hash=spec.spec_hash(), generator_version=VERSION,
        rule_pack=RulePackRef(id=spec.rule_pack.id, version=spec.rule_pack.version),
        bbox=BBox(width=W, height=H, depth=D), parts=parts, hardware=hardware, joints=joints, assemblies=assemblies,
    )
    return graph.with_hash()


def _hinged_doors(ctx: Ctx, door: HingedDoors, si: int, x: int, sw: int, base_h: int, carcass_h: int,
                  reveal: int, parts: list[Part], hardware: list[HardwarePlacement]) -> None:
    spec = ctx.spec
    t = spec.construction.carcass_thickness
    path = f"carcass/section_{si}"
    outer_l = x - (t if si == 1 else t // 2)
    outer_r = x + sw + (t if si == len(spec.sections) else t // 2)
    span = outer_r - outer_l
    leaf_w = (span - reveal * (door.leaves + 1)) // door.leaves
    door_h = carcass_h - reveal
    hinge_code = (spec.fronts.hinge.code if spec.fronts.hinge else ctx.rules.get("hardware.hinge"))
    hinges_per_leaf = 2 if door_h <= 900 else 3 if door_h <= 1600 else 4 if door_h <= 2000 else 5
    for leaf in range(door.leaves):
        key = f"s{si}.door{leaf + 1}"
        lx = outer_l + reveal + leaf * (leaf_w + reveal)
        hinge_side = door.hinge_side if door.leaves == 1 else ("left" if leaf == 0 else "right")
        cup_x = ctx.r("hinge.cup_edge_distance", 22) + 35 // 2
        end = ctx.r("hinge.end_distance", 100)
        zs = [end + (door_h - 2 * end) * k // (hinges_per_leaf - 1) for k in range(hinges_per_leaf)]
        cups = [Drill(face="back", x=z, y=cup_x if hinge_side == "left" else leaf_w - cup_x,  # type: ignore[arg-type]
                      diameter=35, depth=13, tool_hint="D35", source=f"hardware:{hinge_code}")
                for z in sorted(zs)]
        parts.append(_panel(
            ctx, key=key, role="door", label=f"Door S{si}-{leaf + 1}", material=spec.fronts.material.code,
            length=door_h, width=leaf_w, thickness=spec.fronts.thickness,
            banded=("L1", "L2", "W1", "W2"), at=(lx, -spec.fronts.thickness, base_h + reveal // 2),
            path=path, ops=cups, rotate_to="xz", tags=["visible", f"hinge:{hinge_side}"]))
        if hinge_side == "left":
            hinged_on = "gable_l" if si == 1 else f"s{si}.divider"
        else:
            hinged_on = "gable_r" if si == len(spec.sections) else f"s{si + 1}.divider"
        hardware.append(HardwarePlacement(
            hardware_code=hinge_code, qty=hinges_per_leaf, attached_to=[key, hinged_on],
            params={"positions_from_bottom": sorted(zs)}))


def sliding_leaf_width(opening: int, leaves: int, overlap: int) -> int:
    """Leaves of equal width that cover the opening with `overlap` mm where neighbours meet."""
    return -(-(opening + overlap * (leaves - 1)) // leaves)  # ceiling division


def _sliding_doors(ctx: Ctx, opening: int, base_h: int, carcass_h: int, zone: int,
                   parts: list[Part], hardware: list[HardwarePlacement], assemblies: list[AssemblyNode]) -> None:
    """Sliding doors on a double track in the front `zone` of the carcass, between top and bottom rails.

    Tracks: the front track is 10 mm behind the carcass front, the back track one door thickness + 10 mm
    behind it. With 2 leaves the left runs on the back track; with 3 the middle one does.
    """
    spec = ctx.spec
    cfg = spec.fronts.sliding
    t = spec.construction.carcass_thickness
    leaves = cfg.leaves if cfg else 2
    overlap = cfg.overlap if cfg else ctx.r("sliding.overlap", 40)
    door_t = spec.fronts.thickness
    top_h, bottom_h = ctx.r("sliding.top_rail_height", 45), ctx.r("sliding.bottom_rail_height", 10)
    rail_d = zone - 10
    path = "fronts/sliding"
    assemblies.append(AssemblyNode(path=path, label="Sliding doors"))
    z_bottom = base_h + t
    z_top = base_h + carcass_h - t
    parts.append(_profile(key="rail_top", role="sliding_track", label="Top rail", material="ALU-TRACK",
                          length=opening, width=rail_d, height=top_h, at=(t, 5, z_top - top_h), path=path))
    parts.append(_profile(key="rail_bottom", role="sliding_track", label="Bottom rail", material="ALU-TRACK",
                          length=opening, width=rail_d, height=bottom_h, at=(t, 5, z_bottom), path=path))
    door_h = z_top - top_h - (z_bottom + bottom_h) - 2  # 1 mm running clearance top and bottom
    leaf_w = sliding_leaf_width(opening, leaves, overlap)
    tracks = {"front": 10, "back": 10 + door_t + 10}
    for i in range(leaves):
        track = ("back", "front")[i % 2] if leaves == 2 else ("front", "back", "front")[i]
        lx = t + min(i * (leaf_w - overlap), opening - leaf_w)  # last leaf flush with the right gable
        key = f"sliding.door{i + 1}"
        parts.append(_panel(
            ctx, key=key, role="sliding_door", label=f"Sliding door {i + 1}", material=spec.fronts.material.code,
            length=door_h, width=leaf_w, thickness=door_t, banded=("L1", "L2", "W1", "W2"),
            at=(lx, tracks[track], z_bottom + bottom_h + 1), path=path, rotate_to="xz",
            tags=["visible", f"track:{track}"]))
        hardware.append(HardwarePlacement(
            hardware_code=ctx.rules.get("hardware.sliding_roller", "SLIDING-ROLLER"), qty=2, attached_to=[key]))
    hardware.append(HardwarePlacement(
        hardware_code=(cfg.track.code if cfg else ctx.rules.get("hardware.sliding_track", "SLIDING-TRACK-2")),
        qty=1, attached_to=["rail_top", "rail_bottom"], params={"length_mm": opening, "leaves": leaves}))
