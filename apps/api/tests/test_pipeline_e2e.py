"""End-to-end: upload → analyze (mock AI) → FurnitureSpec → build (glTF) → edit → rebuild → SketchUp via MCP.

Needs a real Postgres: DATABASE_URL=postgresql+psycopg://... pytest apps/api/tests
The SketchUp step uses the fake bridge (extensions/sketchup-bridge/dev/fake_bridge.py) behind the real
MCP server and MCP client, so everything except SketchUp itself is exercised.
"""
from __future__ import annotations

import io
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="needs DATABASE_URL (Postgres)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wardrobe_photo() -> bytes:
    """A tall light-oak box with two door seams: enough for the mock provider."""
    im = Image.new("RGB", (900, 1300), "#DDDDDD")
    d = ImageDraw.Draw(im)
    d.rectangle([150, 100, 750, 1250], fill="#C8A27A", outline="#555555", width=4)
    d.line([450, 100, 450, 1250], fill="#555555", width=3)
    out = io.BytesIO()
    im.save(out, "JPEG")
    return out.getvalue()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("DF_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("GEOMETRY_ENGINE", "gltf")
    monkeypatch.setenv("DF_BRIDGE_CONFIG", str(tmp_path / "no-bridge.json"))  # ignore the developer's real config
    from df_services import config, db, storage
    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    storage.get_storage.cache_clear()
    db.migrate()
    with db.tx() as conn:
        conn.exec_driver_sql("truncate designs cascade")
    yield tmp_path
    config.get_settings.cache_clear()
    storage.get_storage.cache_clear()


def _drain():
    from df_worker.main import run_once
    for _ in range(10):
        if not run_once("test-worker", None):
            return
    raise AssertionError("queue did not drain")


def test_upload_to_model_then_edit_then_sketchup(env, monkeypatch):
    from fastapi.testclient import TestClient

    from df_api.main import app
    from df_services import config

    client = TestClient(app)

    # 1. Upload with a measured height anchor
    r = client.post("/v1/designs", data={"name": "Oak wardrobe", "anchor_dimension": "height", "anchor_value_mm": "2400"},
                    files=[("images", ("wardrobe.jpg", _wardrobe_photo(), "image/jpeg"))])
    assert r.status_code == 201, r.text
    design_id = r.json()["id"]
    assert client.get(f"/v1/designs/{design_id}").json()["status"] == "analyzing"

    # 2. Worker: analyze → spec → auto build
    _drain()
    d = client.get(f"/v1/designs/{design_id}").json()
    assert d["status"] == "model_ready", d["status_message"]
    spec = d["spec"]["spec"]
    assert spec["category"] == "wardrobe"
    assert spec["overall"]["height"] == 2400                       # anchor honoured exactly
    assert d["spec"]["field_confidence"]["/overall/height"]["source"] == "user_anchor"
    assert spec["construction"]["carcass_material"]["code"] == "MFC18-OAK"   # colour matched to catalog
    kinds = {a["kind"] for a in d["artifacts"]}
    assert {"spec_json", "glb", "part_graph", "parts_csv"} <= kinds
    glb = next(a for a in d["artifacts"] if a["kind"] == "glb")
    body = client.get(glb["url"].replace("http://localhost:8000", "")).content
    assert body[:4] == b"glTF" and len(body) == int.from_bytes(body[8:12], "little")
    assert [e["message"] for e in d["events"]][-1] == "succeeded"
    # Every server message carries a code the UI translates (English text is only the fallback)
    assert d["status_code"] == "status.model_ready_web" and d["status_params"]["parts"] > 0
    assert all(e["code"] for e in d["events"]), [e["message"] for e in d["events"] if not e["code"]]
    assert {n["code"] for n in d["spec"]["notes_detail"]} >= {"mock_analysis"}
    assert spec["sections"][0]["compartments"][0]["kind"] == "hanging"   # wardrobes get a hanging rail

    # 3. Edit: make it wider, save → new version → rebuild
    spec["overall"]["width"] = 2000
    r = client.put(f"/v1/designs/{design_id}/spec", json=spec)
    assert r.status_code == 200 and r.json()["spec_id"], r.text
    _drain()
    d = client.get(f"/v1/designs/{design_id}").json()
    assert d["status"] == "model_ready" and d["spec"]["version"] == 2 and d["spec"]["origin"] == "user_edit"
    assert d["spec"]["spec"]["overall"]["width"] == 2000

    # 4. An invalid edit is rejected and nothing is saved
    bad = {**spec, "overall": {**spec["overall"], "height": 3500}}
    r = client.put(f"/v1/designs/{design_id}/spec", json=bad)
    assert r.json()["spec_id"] is None and any(i["severity"] == "error" for i in r.json()["issues"])
    too_tall = next(i for i in r.json()["issues"] if i["rule_code"] == "SIZE_OUT_OF_RANGE")
    assert too_tall["params"] == {"dimension": "height", "value": 3500, "min": 300, "max": 2700}

    # 5. SketchUp path: real MCP client → real MCP server (stdio) → fake bridge over TCP
    port, token = _free_port(), "test-token"
    bridge_env = {**os.environ, "DF_BRIDGE_PORT": str(port), "DF_BRIDGE_TOKEN": token, "DF_JOB_ROOT": str(env / "jobs")}
    bridge = subprocess.Popen([sys.executable, str(ROOT / "extensions/sketchup-bridge/dev/fake_bridge.py")],
                              env=bridge_env, stdout=subprocess.PIPE, text=True)
    try:
        assert "listening" in bridge.stdout.readline()
        monkeypatch.setenv("GEOMETRY_ENGINE", "sketchup_mcp")
        monkeypatch.setenv("SKETCHUP_MCP_ARGS", shlex.quote(str(ROOT / "extensions/sketchup-mcp-server/server.py")))
        monkeypatch.setenv("DF_BRIDGE_PORT", str(port))
        monkeypatch.setenv("DF_BRIDGE_TOKEN", token)
        config.get_settings.cache_clear()
        assert client.post(f"/v1/designs/{design_id}/rebuild").status_code == 202
        t0 = time.monotonic()
        _drain()
        d = client.get(f"/v1/designs/{design_id}").json()
        assert d["status"] == "model_ready", d["status_message"]
        assert "SketchUp model built" in d["status_message"], d["status_message"]
        kinds = [a["kind"] for a in d["artifacts"]]
        assert {"skp", "obj", "stl", "png", "glb"} <= set(kinds), kinds
        assert kinds.count("glb") == 1                             # rebuilds replace, not duplicate
        assert time.monotonic() - t0 < 60
    finally:
        bridge.terminate()
        bridge.wait(5)


def test_sketchup_unreachable_degrades_to_web_preview(env, monkeypatch):
    from fastapi.testclient import TestClient

    from df_api.main import app
    from df_services import config

    monkeypatch.setenv("GEOMETRY_ENGINE", "sketchup_mcp")
    monkeypatch.setenv("SKETCHUP_MCP_ARGS", shlex.quote(str(ROOT / "extensions/sketchup-mcp-server/server.py")))
    monkeypatch.setenv("DF_BRIDGE_PORT", str(_free_port()))  # nothing listening
    monkeypatch.setenv("DF_BRIDGE_TOKEN", "x")
    config.get_settings.cache_clear()
    client = TestClient(app)
    r = client.post("/v1/designs", data={"category": "bookcase"},
                    files=[("images", ("b.jpg", _wardrobe_photo(), "image/jpeg"))])
    design_id = r.json()["id"]

    from df_services.db import tx
    for _ in range(6):  # retries are scheduled seconds ahead (backoff); pull them forward
        _drain()
        with tx() as conn:
            conn.exec_driver_sql("update jobs set run_after = now() where status = 'queued'")
    d = client.get(f"/v1/designs/{design_id}").json()
    assert d["status"] == "model_ready"
    assert "SketchUp model failed" in d["status_message"] and "not reachable" in d["status_message"]
    assert "glb" in {a["kind"] for a in d["artifacts"]}
    build = next(j for j in d["jobs"] if j["kind"] == "build_model")
    assert build["attempts"] == 3                                 # retried, then degraded
