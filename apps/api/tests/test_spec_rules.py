"""Spec generator + rule checks for sliding doors and hanging compartments (no database needed)."""
from df_domain.observation import FrontRect
from df_domain.spec import FurnitureSpec
from df_services.analysis import mock_analyze
from df_services.spec_generator import build_spec, validate_spec

import io

from PIL import Image


def _obs(category: str = "wardrobe"):
    buf = io.BytesIO()
    Image.new("RGB", (800, 1100), "#C8A27A").save(buf, "JPEG")
    return mock_analyze([buf.getvalue()], category).observation


def _codes(issues):
    return {i.rule_code: i for i in issues}


def test_sliding_fronts_detected_become_one_sliding_set():
    obs = _obs()
    obs = obs.model_copy(update={"fronts": [
        FrontRect(x0=0, y0=0, x1=0.52, y1=1, kind="sliding_door"),
        FrontRect(x0=0.48, y0=0, x1=1, y1=1, kind="sliding_door")]})
    draft = build_spec(obs, {"anchors": [{"dimension": "width", "value_mm": 2000}]})
    s = draft.spec
    assert s.fronts.style == "sliding" and s.fronts.sliding.leaves == 2
    assert all(sec.doors == [] for sec in s.sections)
    assert s.sections[0].compartments[0].kind == "hanging"
    assert not [i for i in draft.issues if i.severity == "error"], draft.issues


def test_wide_two_leaf_sliding_suggests_three_leaves():
    draft = build_spec(_obs(), {"anchors": [{"dimension": "width", "value_mm": 2400}]})
    data = draft.spec.model_dump(mode="json")
    data["fronts"].update(style="sliding", handle={"kind": "none"},
                          sliding={"leaves": 2, "track": {"code": "SLIDING-TRACK-2"}, "overlap": 40})
    for sec in data["sections"]:
        sec["doors"] = []
    issues = _codes(validate_spec(FurnitureSpec.model_validate(data)))
    wide = issues["SLIDING_LEAF_TOO_WIDE"]
    assert wide.severity == "warning" and wide.params["leaf"] == 1202
    assert wide.suggestion == [{"op": "replace", "path": "/fronts/sliding/leaves", "value": 3}]


def test_shallow_sliding_wardrobe_cannot_hang_clothes():
    draft = build_spec(_obs(), {"anchors": [{"dimension": "depth", "value_mm": 550}]})
    data = draft.spec.model_dump(mode="json")
    data["fronts"].update(style="sliding", handle={"kind": "none"},
                          sliding={"leaves": 2, "track": {"code": "SLIDING-TRACK-2"}, "overlap": 40})
    issues = _codes(validate_spec(FurnitureSpec.model_validate(data)))
    shallow = issues["HANGING_TOO_SHALLOW"]
    assert shallow.severity == "error" and shallow.params["depth"] == 550 - 90 - 16 - 8


def test_compartments_that_do_not_fit_are_an_error():
    draft = build_spec(_obs(), {"anchors": [{"dimension": "height", "value_mm": 1200}]})
    data = draft.spec.model_dump(mode="json")
    data["sections"][0]["compartments"] = [
        {"kind": "hanging", "height": 900, "rail": {"code": "RAIL-OVAL-30"}},
        {"kind": "shelves", "height": 400, "adjustable_shelves": 0}]
    assert "COMPARTMENTS_TOO_TALL" in _codes(validate_spec(FurnitureSpec.model_validate(data)))
