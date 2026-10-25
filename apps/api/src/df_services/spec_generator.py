"""FurnitureSpec Generator (pipeline stage 2): ImageObservation + user hints → buildable FurnitureSpec.

Deterministic: no LLM here. Absolute sizes come from a small log-space evidence fusion of
  user anchors (measured) > printed dimensions (OCR) > proportions × other dimensions > category priors,
each with a relative σ; the fused σ becomes the confidence shown in the UI.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from df_domain.observation import ImageObservation
from df_domain.spec import FurnitureSpec, SpecIssue
from df_parametric.carcass import compartment_heights, front_zone_depth, generate, sliding_leaf_width

from .catalog import RULE_PACK_ID, DefaultCatalog, DefaultRules

T = 18  # carcass thickness, mm

# category → prior (value mm, relative σ) for W, H, D
PRIORS: dict[str, dict[str, tuple[int, float]]] = {
    "wardrobe":         {"W": (1800, .35), "H": (2200, .12), "D": (600, .06)},
    "tall_cabinet":     {"W": (600, .30),  "H": (2000, .10), "D": (580, .06)},
    "bookcase":         {"W": (900, .35),  "H": (1800, .20), "D": (320, .15)},
    "base_cabinet":     {"W": (600, .40),  "H": (870, .05),  "D": (580, .05)},
    "wall_cabinet":     {"W": (600, .40),  "H": (720, .15),  "D": (330, .10)},
    "sideboard":        {"W": (1800, .30), "H": (800, .15),  "D": (450, .12)},
    "shoe_cabinet":     {"W": (900, .30),  "H": (1000, .20), "D": (350, .15)},
    "tv_unit":          {"W": (1800, .30), "H": (500, .20),  "D": (400, .12)},
    "chest_of_drawers": {"W": (900, .30),  "H": (900, .20),  "D": (480, .10)},
    "vanity":           {"W": (800, .30),  "H": (850, .06),  "D": (480, .10)},
}
BOUNDS = {"W": (300, 4000), "H": (300, 2700), "D": (250, 900)}
SUPPORTED = set(PRIORS)
DIM_NAME = {"W": "width", "H": "height", "D": "depth"}


class UnsupportedCategory(Exception):
    pass


@dataclass
class Estimate:
    log_value: float
    sigma: float
    source: str


@dataclass
class Fused:
    value: int
    sigma: float
    sources: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return round(math.exp(-((self.sigma / 0.12) ** 2) * 0.7), 2)


def _fuse(estimates: list[Estimate]) -> tuple[float, float]:
    weights = [1 / (e.sigma ** 2) for e in estimates]
    mean = sum(w * e.log_value for w, e in zip(weights, estimates)) / sum(weights)
    return mean, 1 / math.sqrt(sum(weights))


_PRINTED = re.compile(
    r"\b(?P<label>W|B|L|H|D|T|width|height|depth)\b\s*[:=]?\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>mm|cm|m)?\b", re.I)
_UNIT = re.compile(r"\b(mm|cm|m)\b", re.I)
_LABEL = {"w": "W", "b": "W", "l": "W", "width": "W", "h": "H", "height": "H", "d": "D", "t": "D", "depth": "D"}


def parse_printed_dimensions(texts: list[str]) -> dict[str, int]:
    """'W 240 x H 236 x D 60 cm' → {'W': 2400, 'H': 2360, 'D': 600}. Only labelled numbers are trusted."""
    found: dict[str, int] = {}
    for t in texts:
        default_unit = (_UNIT.findall(t) or ["cm"])[-1].lower()
        for m in _PRINTED.finditer(t):
            unit = (m.group("unit") or default_unit).lower()
            mm = float(m.group("num").replace(",", ".")) * {"mm": 1, "cm": 10, "m": 1000}[unit]
            key = _LABEL[m.group("label").lower()]
            if BOUNDS[key][0] <= mm <= BOUNDS[key][1]:
                found.setdefault(key, int(round(mm)))
    return found


def solve_dimensions(obs: ImageObservation, category: str, anchors: list[dict]) -> dict[str, Fused]:
    prior = PRIORS[category]
    anchored = {k: int(a["value_mm"]) for a in anchors
                for k, n in DIM_NAME.items() if a.get("dimension") == n and a.get("value_mm")}
    printed = parse_printed_dimensions(obs.printed_text)
    r_wh = obs.width_to_height.value
    sig_wh = 0.06 + 0.25 * (1 - obs.width_to_height.confidence)
    r_dw = obs.depth_to_width.value if obs.depth_to_width else None
    sig_dw = 0.10 + 0.30 * (1 - obs.depth_to_width.confidence) if obs.depth_to_width else 0

    def direct(k: str) -> list[Estimate]:
        ests = [Estimate(math.log(prior[k][0]), prior[k][1], f"category_prior:{category}")]
        if k in printed:
            ests.append(Estimate(math.log(printed[k]), 0.02, "printed_dimension"))
        if k in anchored:
            ests.append(Estimate(math.log(anchored[k]), 0.004, "user_anchor"))
        return ests

    cur = {k: (math.log(prior[k][0]), prior[k][1]) for k in "WHD"}
    for _ in range(6):  # fixed-point: W and H inform each other through the observed ratio
        w_ests = direct("W") + [Estimate(cur["H"][0] + math.log(r_wh), math.hypot(sig_wh, cur["H"][1]), "vision_ratio")]
        h_ests = direct("H") + [Estimate(cur["W"][0] - math.log(r_wh), math.hypot(sig_wh, cur["W"][1]), "vision_ratio")]
        d_ests = direct("D") + ([Estimate(cur["W"][0] + math.log(r_dw), math.hypot(sig_dw, cur["W"][1]), "vision_ratio")]
                                if r_dw else [])
        cur = {"W": _fuse(w_ests), "H": _fuse(h_ests), "D": _fuse(d_ests)}

    out: dict[str, Fused] = {}
    for k, ests in (("W", w_ests), ("H", h_ests), ("D", d_ests)):
        lo, hi = BOUNDS[k]
        if k in anchored:
            value = anchored[k]
        else:
            value = int(round(math.exp(cur[k][0]) / 10) * 10)  # nearest 10 mm when not measured
        out[k] = Fused(max(lo, min(hi, value)), cur[k][1], sorted({e.source for e in ests}))
    return out


@dataclass(frozen=True)
class Note:
    code: str
    params: dict
    text: str  # English fallback, also written into FurnitureSpec.notes

    def as_dict(self) -> dict:
        return {"code": self.code, "params": self.params, "text": self.text}


@dataclass(frozen=True)
class SpecDraft:
    spec: FurnitureSpec
    confidence: dict
    issues: list[SpecIssue]
    notes: list[Note]


def build_spec(obs: ImageObservation, hints: dict[str, Any]) -> SpecDraft:
    catalog = DefaultCatalog()
    T = int(DefaultRules().get("carcass.thickness", 18))  # board thickness from knowledge/quy-cach.yaml
    category = hints.get("category") or obs.category.value
    if category not in SUPPORTED:
        raise UnsupportedCategory(
            f"'{category}' is not supported yet. The MVP builds cabinets, wardrobes, bookcases and sideboards.")
    notes: list[Note] = []
    dims = solve_dimensions(obs, category, hints.get("anchors") or [])
    W, H, D = dims["W"].value, dims["H"].value, dims["D"].value

    # Materials
    def pick(applies: tuple[str, ...]) -> str:
        m = next((m for m in obs.materials if m.applies_to in applies), None)
        return catalog.match_material(m.colour_name, m.colour_hex, m.surface) if m else "MFC18-WHITE"
    carcass_mat, front_mat = pick(("carcass", "all")), pick(("fronts", "all"))

    # Base
    if category == "wall_cabinet" or obs.base_type == "none":
        base: dict = {"kind": "none"}
    elif obs.base_type == "legs":
        base = {"kind": "legs", "height": 100, "leg": {"code": "LEG-ADJ-100"}, "kickboard": False}
    else:
        base = {"kind": "plinth", "height": 100, "setback": 50, "material": {"code": carcass_mat}}

    # Sections: keep each at least 250 mm wide
    n = max(1, min(obs.section_count.value or 1, 8, (W - 2 * T) // (250 + T) or 1))
    shares = obs.section_width_shares
    avail = W - 2 * T - (n - 1) * T
    widths: list[int | str] = ["auto"] * n
    if len(shares) == n and abs(sum(shares) - 1) < 0.05 and min(shares) > 0.05 and max(shares) / min(shares) > 1.15:
        widths = [int(round(s / sum(shares) * avail)) for s in shares[:-1]] + ["auto"]
    if n != obs.section_count.value:
        notes.append(Note("sections_reduced", {"detected": obs.section_count.value, "used": n},
                          f"Detected {obs.section_count.value} sections; using {n} so each is at least 250 mm wide."))

    # Doors per section from detected fronts (centre x → section), else spread the door count
    bounds, acc = [], 0.0
    norm = shares if len(shares) == n and sum(shares) > 0 else [1 / n] * n
    for s in norm:
        bounds.append((acc, acc + s / sum(norm)))
        acc += s / sum(norm)
    leaves = [0] * n
    hinge_hint: list[str | None] = [None] * n
    drawers = 0
    for f in obs.fronts:
        cx = (f.x0 + f.x1) / 2
        i = next((k for k, (a, b) in enumerate(bounds) if a <= cx <= b), n - 1)
        if f.kind in ("door", "glass_door"):
            leaves[i] += 1
            hinge_hint[i] = {"right": "left", "left": "right"}.get(f.handle_side, hinge_hint[i])
        elif f.kind == "drawer_front":
            drawers += 1
    if not obs.fronts and obs.door_count.value:
        base_n, extra = divmod(obs.door_count.value, n)
        leaves = [base_n + (1 if i < extra else 0) for i in range(n)]
    leaves = [min(2, x) for x in leaves]
    sliding_leaves = sum(1 for f in obs.fronts if f.kind == "sliding_door")
    sliding = sliding_leaves >= 2
    if sliding:
        leaves = [0] * n  # one set of sliding doors across the whole width instead of per-section doors
        measured = {"user_anchor", "printed_dimension"} & set(dims["D"].sources)
        min_d = 650  # the track zone takes ~90 mm; clothes need ~500 mm behind it
        if not measured and D < min_d:
            notes.append(Note("sliding_depth", {"from": D, "to": min_d},
                              f"Depth raised from {D} to {min_d} mm so clothes can hang behind the sliding-door track."))
            D = min_d
            dims["D"] = Fused(D, dims["D"].sigma, dims["D"].sources + ["sliding_track_minimum"])
    drawers = max(drawers, obs.drawer_count.value)
    if drawers:
        notes.append(Note("drawers_not_modelled", {"count": drawers},
                          f"{drawers} drawer(s) detected — drawers are not modelled in the MVP; that space is shown as shelves."))

    base_h = base.get("height", 0)
    inner_h = H - base_h - 2 * T
    visible = obs.visible_shelf_count.value
    sections = []
    for i in range(n):
        per = visible // n + (1 if i < visible % n else 0) if visible else max(1, round(inner_h / 380) - 1)
        doors: list[dict] = []
        if leaves[i]:
            sec_w = widths[i] if isinstance(widths[i], int) else avail // n
            lv = leaves[i]
            if lv == 1 and sec_w + T > DefaultRules().get("limits.max_door_leaf_width"):
                lv = 2
                notes.append(Note("door_split", {"section": i + 1},
                                  f"Section {i + 1}: door split into two leaves (single leaf would exceed 600 mm)."))
            door = {"kind": "hinged", "leaves": lv, "spans": [0, 0]}
            if lv == 1:
                door["hinge_side"] = hinge_hint[i] or ("left" if i % 2 == 0 else "right")
            doors.append(door)
        hanging = category == "wardrobe" and (n == 1 or i % 2 == 0)  # alternate hanging / shelf sections
        if hanging:
            compartments = [{"kind": "hanging", "height": "auto", "rail": {"code": "RAIL-OVAL-30"}},
                            {"kind": "shelves", "height": 400, "adjustable_shelves": 0}]
        else:
            compartments = [{"kind": "shelves", "height": "auto", "adjustable_shelves": per}]
        sections.append({"width": widths[i], "compartments": compartments, "doors": doors})

    handle = {"handle": {"kind": "handle", "hardware": {"code": "HANDLE-BAR-128"}, "position": "auto"},
              "knob": {"kind": "handle", "hardware": {"code": "KNOB-30"}, "position": "auto"},
              "push_to_open": {"kind": "push_to_open", "hardware": {"code": "PUSH-OPEN"}},
              "gola_profile": {"kind": "gola_profile", "hardware": {"code": "GOLA-C"}},
              "integrated_groove": {"kind": "integrated_groove", "depth": 10}}.get(obs.handle_type, {"kind": "none"})
    any_doors = any(leaves) or sliding
    main_mat = next((m for m in obs.materials if m.applies_to in ("fronts", "all")), None)
    for hint in obs.review_hints[:3]:  # free text from the vision model; the mock's hint has a fixed code
        notes.append(Note("mock_analysis", {}, hint) if hint.startswith("Mock analysis") else Note("ai_hint", {"text": hint}, hint))
    spec = FurnitureSpec.model_validate({
        "category": category,
        "name": f"{category.replace('_', ' ').title()} {W}×{H}×{D}",
        "overall": {"width": W, "height": H, "depth": D},
        "construction": {
            "carcass_material": {"code": carcass_mat}, "carcass_thickness": T,
            "joinery": "gables_over_top", "connector": "minifix_dowel",
            "back": {"style": "inset_groove", "material": {"code": "HDF8-WHITE"}, "thickness": 8},
            "base": base,
        },
        "fronts": {"style": "sliding" if sliding else "overlay_full" if any_doors else "none",
                   "material": {"code": front_mat}, "thickness": T, "reveal": 3,
                   "handle": {"kind": "none"} if sliding or not any_doors else handle,
                   "sliding": {"leaves": 3 if sliding_leaves >= 3 else 2, "track": {"code": "SLIDING-TRACK-2"},
                               "overlap": 40} if sliding else None},
        "sections": sections,
        "style": {"tags": obs.style_tags[:6], "finish": main_mat.colour_name if main_mat else "",
                  "colour_hex": main_mat.colour_hex if main_mat else None},
        "rule_pack": {"id": str(RULE_PACK_ID), "version": DefaultRules().version},
        "notes": [n.text for n in notes],
    })
    confidence = {f"/overall/{DIM_NAME[k]}": {"value": f.confidence, "sources": f.sources,
                                               "source": "user_anchor" if "user_anchor" in f.sources else
                                               "printed_dimension" if "printed_dimension" in f.sources else "estimated"}
                  for k, f in dims.items()}
    confidence["/category"] = {"value": 1.0 if hints.get("category") else round(obs.category.confidence, 2),
                               "source": "user" if hints.get("category") else "vision"}
    confidence["/sections"] = {"value": round(obs.section_count.confidence, 2), "source": "vision"}
    return SpecDraft(spec, confidence, validate_spec(spec), notes)


def section_widths(spec: FurnitureSpec) -> list[int]:
    t = spec.construction.carcass_thickness
    secs = spec.sections
    avail = spec.overall.width - 2 * t - t * (len(secs) - 1)
    fixed = sum(s.width for s in secs if s.width != "auto")
    autos = [i for i, s in enumerate(secs) if s.width == "auto"]
    rest = avail - fixed
    out = [s.width if s.width != "auto" else 0 for s in secs]
    for k, i in enumerate(autos):
        out[i] = rest // len(autos) + (1 if k < rest % len(autos) else 0)
    return out  # type: ignore[return-value]


def validate_spec(spec: FurnitureSpec) -> list[SpecIssue]:
    rules = DefaultRules()
    issues: list[SpecIssue] = []

    def add(code: str, sev: str, path: str, msg: str, fix: list | None = None, **params: Any) -> None:
        issues.append(SpecIssue(rule_code=code, severity=sev, path=path, message=msg, params=params,  # type: ignore[arg-type]
                                suggestion=fix))

    if spec.category not in SUPPORTED:
        add("CATEGORY_UNSUPPORTED", "error", "/category", f"'{spec.category}' cannot be built by the MVP generator.",
            category=spec.category)
    o = spec.overall
    for k, v in (("W", o.width), ("H", o.height), ("D", o.depth)):
        lo, hi = BOUNDS[k]
        if not lo <= v <= hi:
            add("SIZE_OUT_OF_RANGE", "error", f"/overall/{DIM_NAME[k]}", f"{DIM_NAME[k].title()} {v} mm is outside {lo}–{hi} mm.",
                dimension=DIM_NAME[k], value=v, min=lo, max=hi)
    t = spec.construction.carcass_thickness
    widths = section_widths(spec)
    for i, w in enumerate(widths):
        if w < 100:
            add("SECTION_TOO_NARROW", "error", f"/sections/{i}/width", f"Section {i + 1} is {w} mm wide; minimum is 100 mm.",
                section=i + 1, width=w, min=100)
        elif w > rules.get("limits.max_shelf_span_18"):
            add("SHELF_SPAN_EXCEEDED", "warning", f"/sections/{i}",
                f"Section {i + 1} is {w} mm wide; 18 mm shelves sag beyond {rules.get('limits.max_shelf_span_18')} mm. Add a divider.",
                section=i + 1, width=w, max=rules.get("limits.max_shelf_span_18"))
        for j, d in enumerate(spec.sections[i].doors if spec.fronts.style != "sliding" else []):
            if d.kind == "hinged":
                leaf = (w + t) // d.leaves
                if leaf > rules.get("limits.max_door_leaf_width"):
                    add("DOOR_LEAF_TOO_WIDE", "warning", f"/sections/{i}/doors/{j}",
                        f"Door leaf ≈ {leaf} mm wide; hinged leaves over 600 mm tend to sag.",
                        [{"op": "replace", "path": f"/sections/{i}/doors/{j}/leaves", "value": 2}] if d.leaves == 1 else None,
                        section=i + 1, leaf=leaf, max=rules.get("limits.max_door_leaf_width"))
    base_h = getattr(spec.construction.base, "height", 0)
    front_t = spec.fronts.thickness if spec.fronts.style.startswith("overlay") else 0
    usable_d = o.depth - front_t - front_zone_depth(spec, rules) - rules.get("back.groove_inset") - spec.construction.back.thickness
    clear_h = o.height - base_h - 2 * t
    for i, sec in enumerate(spec.sections):
        try:
            heights = compartment_heights(list(sec.compartments), clear_h, t)
        except ValueError:
            add("COMPARTMENTS_TOO_TALL", "error", f"/sections/{i}/compartments",
                f"Section {i + 1}: the compartments do not fit in {clear_h} mm of clear height.",
                section=i + 1, height=clear_h)
            continue
        for ci, (comp, ch) in enumerate(zip(sec.compartments, heights)):
            if comp.kind != "hanging":
                continue
            if usable_d < rules.get("limits.min_hanging_depth"):
                add("HANGING_TOO_SHALLOW", "error", f"/sections/{i}/compartments/{ci}",
                    f"Section {i + 1}: {usable_d} mm usable depth is too shallow to hang clothes "
                    f"(needs {rules.get('limits.min_hanging_depth')} mm).",
                    section=i + 1, depth=usable_d, min=rules.get("limits.min_hanging_depth"))
            if ch < rules.get("limits.min_hanging_height"):
                add("HANGING_TOO_LOW", "warning", f"/sections/{i}/compartments/{ci}",
                    f"Section {i + 1}: {ch} mm of hanging height is short; shirts need about "
                    f"{rules.get('limits.min_hanging_height')} mm.",
                    section=i + 1, height=ch, min=rules.get("limits.min_hanging_height"))
    if spec.fronts.style == "sliding":
        cfg = spec.fronts.sliding
        if cfg is None:
            add("SLIDING_CONFIG_MISSING", "error", "/fronts/sliding", "Sliding fronts need a number of leaves.")
        else:
            leaf = sliding_leaf_width(o.width - 2 * t, cfg.leaves, cfg.overlap)
            if leaf > rules.get("limits.max_sliding_leaf"):
                add("SLIDING_LEAF_TOO_WIDE", "warning", "/fronts/sliding/leaves",
                    f"Each sliding leaf is ≈ {leaf} mm wide; over {rules.get('limits.max_sliding_leaf')} mm "
                    "is heavy and can twist. Use 3 leaves.",
                    [{"op": "replace", "path": "/fronts/sliding/leaves", "value": 3}] if cfg.leaves == 2 else None,
                    leaf=leaf, max=rules.get("limits.max_sliding_leaf"))
            elif leaf < rules.get("limits.min_sliding_leaf"):
                add("SLIDING_LEAF_TOO_NARROW", "error", "/fronts/sliding/leaves",
                    f"Each sliding leaf would be only {leaf} mm wide; minimum is {rules.get('limits.min_sliding_leaf')} mm.",
                    leaf=leaf, min=rules.get("limits.min_sliding_leaf"))
    longest = max(o.height - base_h, o.width - 2 * t)
    if longest > rules.get("limits.max_panel_length"):
        add("PANEL_TOO_LONG", "error", "/overall",
            f"A {longest} mm panel exceeds the {rules.get('limits.max_panel_length')} mm usable sheet length.",
            length=longest, max=rules.get("limits.max_panel_length"))
    if not any(i.severity == "error" for i in issues):
        try:
            generate(spec, rules, DefaultCatalog())
        except Exception as e:  # noqa: BLE001 — any generator failure is a spec problem for the user
            add("GENERATION_FAILED", "error", "/", f"Parts could not be generated: {e}", error=str(e))
    return issues
