"""Determinism + geometry sanity for the carcass generator. Run: pytest python/tests"""
from uuid import UUID

from df_domain.spec import FurnitureSpec
from df_parametric.carcass import generate


class Rules:
    id = UUID(int=1)
    version = 1
    _d = {"hardware.hinge": "BLUM-71B3550", "hardware.shelf_pin": "SHELF-PIN-5"}

    def get(self, key, default=None):
        return self._d.get(key, default)


class Catalog:
    def edge_band_for(self, material_code, thickness):
        return f"EB-{material_code}-{thickness}.0"


SPEC = FurnitureSpec.model_validate({
    "category": "wardrobe", "name": "Test wardrobe",
    "overall": {"width": 1800, "height": 2400, "depth": 600},
    "construction": {
        "carcass_material": {"code": "MFC18-W1000"},
        "back": {"style": "inset_groove", "material": {"code": "HDF8-W"}, "thickness": 8},
        "base": {"kind": "plinth", "height": 100, "setback": 50, "material": {"code": "MFC18-W1000"}},
    },
    "fronts": {"style": "overlay_full", "material": {"code": "MFC18-W1000"}, "handle": {"kind": "none"}},
    "sections": [
        {"width": "auto", "compartments": [{"kind": "shelves", "height": "auto", "adjustable_shelves": 4}],
         "doors": [{"kind": "hinged", "leaves": 1, "hinge_side": "left", "spans": [0, 0]}]},
        {"width": "auto", "compartments": [{"kind": "shelves", "height": "auto", "adjustable_shelves": 4}],
         "doors": [{"kind": "hinged", "leaves": 2, "spans": [0, 0]}]},
    ],
    "rule_pack": {"id": str(UUID(int=1)), "version": 1},
})


def test_deterministic():
    assert generate(SPEC, Rules(), Catalog()).graph_hash == generate(SPEC, Rules(), Catalog()).graph_hash


def test_parts_and_sizes():
    g = generate(SPEC, Rules(), Catalog())
    keys = [p.key for p in g.parts]
    assert {"gable_l", "gable_r", "top", "bottom", "back", "s2.divider", "plinth_front"} <= set(keys)
    assert sum(p.role == "adjustable_shelf" for p in g.parts) == 8
    assert sum(p.role == "door" for p in g.parts) == 3
    gable = g.part("gable_l")
    assert gable.length == 2300 and gable.width == 582          # 2400 − plinth; 600 − 18 door
    assert gable.cut_width == 581                                 # front edge banded 1 mm
    top = g.part("top")
    assert top.length == 1800 - 36
    # two equal sections: (1764 − 18) / 2
    assert g.part("s1.c0.shelf1").length == 873 - 2


def test_door_hinges_scale_with_height():
    g = generate(SPEC, Rules(), Catalog())
    hinge = next(h for h in g.hardware if h.attached_to[0] == "s1.door1")
    # 2400 − 100 plinth − 3 reveal = 2297 mm door → > 2000 mm → 5 hinges, evenly spaced from 100 to 2197
    assert hinge.qty == 5 and hinge.attached_to[1] == "gable_l"
    assert hinge.params["positions_from_bottom"] == [100, 624, 1148, 1672, 2197]


def test_world_geometry_fills_overall_box_without_collisions():
    from itertools import combinations

    from df_geometry.engine import world_aabb

    g = generate(SPEC, Rules(), Catalog())
    boxes = {p.key: world_aabb(p) for p in g.parts}
    lo = [min(b[0][i] for b in boxes.values()) for i in range(3)]
    hi = [max(b[1][i] for b in boxes.values()) for i in range(3)]
    assert [hi[i] - lo[i] for i in range(3)] == [1800, 600, 2400]   # W, D, H

    def overlap(a, b):  # strictly positive volume intersection
        return all(min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]) > 0 for i in range(3))

    # The back sits in grooves cut into gables/top/bottom, so its overlap is expected; all else must be clear.
    allowed = {"back"}
    clashes = [(a, b) for a, b in combinations(boxes, 2)
               if overlap(boxes[a], boxes[b]) and not ({a, b} & allowed)]
    assert clashes == []


def test_shelves_spread_over_height_on_32mm_grid():
    from df_geometry.engine import world_aabb

    g = generate(SPEC, Rules(), Catalog())
    floor = 100 + 18  # plinth + bottom panel
    zs = sorted(world_aabb(p)[0][2] for p in g.parts if p.key.startswith("s1.") and p.role == "adjustable_shelf")
    assert len(zs) == 4 and len(set(zs)) == 4
    assert all((z + 9 - floor) % 32 == 0 for z in zs)            # shelf centre on the pin grid
    assert zs[0] > floor + 300 and zs[-1] < 2400 - 18 - 300


def test_compiler_shares_definitions_and_is_stable():
    from df_domain.ports import MaterialInfo
    from df_geometry.engine import PartGraphCompiler

    class Cat(Catalog):
        def material(self, code):
            return MaterialInfo(code, "sheet", 18, "none", None, code, "#F4F4F1")

    g = generate(SPEC, Rules(), Catalog())
    cmds = PartGraphCompiler(Cat()).compile(g)
    defs = [c for c in cmds if c.op == "define_panel"]
    places = [c for c in cmds if c.op == "place"]
    assert len(places) == len(g.parts)
    assert len(defs) < len(places)                     # 8 identical shelves → 1 definition
    assert [c.model_dump() for c in cmds] == [c.model_dump() for c in PartGraphCompiler(Cat()).compile(g)]


def test_parts_extent_excludes_undrawn_legs():
    """A carcass on legs is 100 mm taller overall than its drawn panels; geometry checks use the panels."""
    from df_geometry.engine import parts_extent

    data = SPEC.model_dump(mode="json")
    data["construction"]["base"] = {"kind": "legs", "height": 100, "leg": {"code": "LEG-ADJ-100"}, "kickboard": False}
    on_legs = type(SPEC).model_validate(data)
    g = generate(on_legs, Rules(), Catalog())
    assert g.bbox.height == 2400
    assert parts_extent(g) == (1800, 600, 2300)   # X width, Y depth, Z height of the drawn panels
