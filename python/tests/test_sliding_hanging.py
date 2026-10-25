"""Step 1: sliding doors across the whole width + hanging compartments with a top storage box."""
from itertools import combinations
from uuid import UUID

from df_domain.spec import FurnitureSpec
from df_geometry.engine import parts_extent, world_aabb
from df_parametric.carcass import generate, sliding_leaf_width

from test_carcass import Catalog, Rules

HANGING_WITH_TOP = [
    {"kind": "hanging", "height": "auto", "rail": {"code": "RAIL-OVAL-30"}},
    {"kind": "shelves", "height": 400, "adjustable_shelves": 0},
]


def sliding_wardrobe(leaves: int = 2, width: int = 2000) -> FurnitureSpec:
    return FurnitureSpec.model_validate({
        "category": "wardrobe", "name": "Sliding wardrobe",
        "overall": {"width": width, "height": 2400, "depth": 620},
        "construction": {
            "carcass_material": {"code": "MFC18-OAK"},
            "back": {"style": "inset_groove", "material": {"code": "HDF8-WHITE"}, "thickness": 8},
            "base": {"kind": "plinth", "height": 100, "setback": 50, "material": {"code": "MFC18-OAK"}},
        },
        "fronts": {"style": "sliding", "material": {"code": "MFC18-OAK"}, "handle": {"kind": "none"},
                   "sliding": {"leaves": leaves, "track": {"code": "SLIDING-TRACK-2"}, "overlap": 40}},
        "sections": [
            {"width": "auto", "compartments": HANGING_WITH_TOP, "doors": []},
            {"width": "auto", "compartments": [{"kind": "shelves", "height": "auto", "adjustable_shelves": 4}],
             "doors": []},
        ],
        "rule_pack": {"id": str(UUID(int=1)), "version": 1},
    })


def by_role(g, role):
    return [p for p in g.parts if p.role == role]


def test_leaf_width_covers_opening_with_overlap():
    assert sliding_leaf_width(1964, 2, 40) == 1002          # 2 × 1002 − 40 = 1964
    assert sliding_leaf_width(2364, 3, 40) == 815           # 3 × 815 − 2 × 40 ≥ 2364 (rounded up)


def test_two_leaves_cover_the_opening_on_two_tracks():
    g = generate(sliding_wardrobe(2), Rules(), Catalog())
    doors = by_role(g, "sliding_door")
    assert len(doors) == 2 and not by_role(g, "door")
    boxes = [world_aabb(p) for p in doors]
    assert min(b[0][0] for b in boxes) == 18 and max(b[1][0] for b in boxes) == 2000 - 18   # gable to gable
    assert boxes[0][1][0] - boxes[1][0][0] == 40                                            # leaves overlap 40 mm
    assert boxes[0][0][1] != boxes[1][0][1]                                                 # different tracks
    assert {p.length for p in doors} == {2400 - 100 - 36 - 45 - 10 - 2}                     # between the rails
    assert all(set(p.edge_band) == {"L1", "L2", "W1", "W2"} and all(p.edge_band.values()) for p in doors)


def test_three_leaves_middle_on_back_track():
    g = generate(sliding_wardrobe(3, width=2400), Rules(), Catalog())
    doors = sorted(by_role(g, "sliding_door"), key=lambda p: world_aabb(p)[0][0])
    ys = [world_aabb(p)[0][1] for p in doors]
    assert ys[0] == ys[2] < ys[1]


def test_rails_and_internals_stay_out_of_the_door_zone():
    g = generate(sliding_wardrobe(), Rules(), Catalog())
    rails = by_role(g, "sliding_track")
    assert {p.key for p in rails} == {"rail_top", "rail_bottom"} and all(p.length == 2000 - 36 for p in rails)
    zone = 90
    for p in g.parts:
        if p.role in ("divider", "fixed_shelf", "adjustable_shelf", "hanging_rail"):
            assert world_aabb(p)[0][1] >= zone, p.key       # nothing inside collides with the sliding doors
    assert parts_extent(g) == (2000, 620, 2400)             # doors sit inside the depth: no front overhang


def test_hanging_compartment_has_rail_and_top_box():
    g = generate(sliding_wardrobe(), Rules(), Catalog())
    rail = next(p for p in g.parts if p.role == "hanging_rail")
    fixed = next(p for p in g.parts if p.role == "fixed_shelf")
    (_, _, rz0), (_, _, rz1) = world_aabb(rail)
    (_, _, fz0), _ = world_aabb(fixed)
    assert fz0 == 2400 - 18 - 400 - 18                      # top box is 400 mm clear under the top panel
    assert fz0 - rz1 == 60 - 30                             # rail 60 mm below the fixed shelf (30 mm tall rail)
    assert rail.material_code == "ALU-OVAL" and rail.length == fixed.length - 4
    assert any(h.hardware_code == "RAIL-SUPPORT" and h.qty == 2 for h in g.hardware)


def test_no_collisions_in_sliding_wardrobe():
    g = generate(sliding_wardrobe(3, width=2400), Rules(), Catalog())
    boxes = {p.key: world_aabb(p) for p in g.parts}

    def overlap(a, b):
        return all(min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]) > 0 for i in range(3))

    clashes = [(a, b) for a, b in combinations(boxes, 2)
               if overlap(boxes[a], boxes[b]) and "back" not in (a, b)
               and not (a.startswith("sliding.door") and b.startswith("sliding.door"))]  # leaves overlap in X only
    assert clashes == []
    leaves = [boxes[k] for k in boxes if k.startswith("sliding.door")]
    for a, b in combinations(leaves, 2):  # overlapping leaves must be on different tracks (Y)
        if min(a[1][0], b[1][0]) > max(a[0][0], b[0][0]):
            assert min(a[1][1], b[1][1]) <= max(a[0][1], b[0][1])


def test_deterministic():
    assert generate(sliding_wardrobe(), Rules(), Catalog()).graph_hash == \
        generate(sliding_wardrobe(), Rules(), Catalog()).graph_hash


def test_sketchup_tags_put_sliding_doors_on_fronts_and_rails_on_hardware():
    """The Interior scene hides DF_Fronts; sliding doors must be on that tag or they stay visible."""
    from df_domain.ports import MaterialInfo
    from df_geometry.engine import PartGraphCompiler

    class Cat(Catalog):
        def material(self, code):
            return MaterialInfo(code, "sheet", 18, "none", None, code, "#C8A27A")

    g = generate(sliding_wardrobe(), Rules(), Catalog())
    tags = {c.instance_key: c.tag for c in PartGraphCompiler(Cat()).compile(g) if c.op == "place"}
    assert tags["sliding.door1"] == tags["sliding.door2"] == "DF_Fronts"
    assert tags["rail_top"] == tags["s1.c0.rail"] == "DF_Hardware"
    assert tags["gable_l"] == "DF_Carcass"
