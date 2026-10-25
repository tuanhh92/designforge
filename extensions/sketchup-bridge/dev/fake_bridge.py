"""Fake SketchUp bridge for development and CI.

Speaks exactly the NDJSON protocol of designforge_bridge/main.rb on 127.0.0.1:$DF_BRIDGE_PORT, keeps an
in-memory model, and writes real OBJ/STL/PNG files from the placed geometry. The .skp it writes is a
clearly labelled placeholder — only real SketchUp produces SketchUp files. Run SketchUp with the Ruby
extension for real .skp output; nothing else in the pipeline changes.

    DF_BRIDGE_TOKEN=... DF_JOB_ROOT=./var/jobs python extensions/sketchup-bridge/dev/fake_bridge.py
"""
from __future__ import annotations

import json
import os
import socketserver
from pathlib import Path

# Same config as the real extension and the worker: env vars win, else ~/.designforge/bridge.json.
_CFG_PATH = Path(os.environ.get("DF_BRIDGE_CONFIG", "~/.designforge/bridge.json")).expanduser()
_CFG = json.loads(_CFG_PATH.read_text()) if _CFG_PATH.is_file() else {}
PORT = int(os.environ.get("DF_BRIDGE_PORT") or _CFG.get("port", 9877))
TOKEN = os.environ.get("DF_BRIDGE_TOKEN") or _CFG.get("token", "")
JOB_ROOT = Path(os.environ.get("DF_JOB_ROOT") or _CFG.get("job_root", "./var/jobs")).expanduser().resolve()
VERSION = "0.2.0-fake"
OPS = {"ensure_material", "ensure_tag", "define_panel", "define_proxy", "group", "place", "paint"}


class Model:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.materials: dict[str, str] = {}
        self.tags: set[str] = set()
        self.defs: dict[str, tuple[float, float, float]] = {}
        self.instances: list[dict] = []
        self.groups: set[str] = set()
        self.scenes: list[str] = []

    def boxes(self) -> list[tuple[tuple[float, ...], tuple[float, ...], str]]:
        out = []
        for inst in self.instances:
            l, w, t = self.defs[inst["def_key"]]
            m = inst["transform"]
            pts = [tuple(m[i] * x + m[4 + i] * y + m[8 + i] * z + m[12 + i] for i in range(3))
                   for x in (0, l) for y in (0, w) for z in (0, t)]
            out.append((tuple(min(p[i] for p in pts) for i in range(3)),
                        tuple(max(p[i] for p in pts) for i in range(3)), inst["instance_key"]))
        return out


MODEL = Model()


class BridgeError(Exception):
    def __init__(self, msg: str, retryable: bool = False):
        super().__init__(msg)
        self.retryable = retryable


def safe_path(path: str) -> Path:
    p = Path(path).resolve()
    if not p.is_relative_to(JOB_ROOT):
        raise BridgeError(f"path outside job root: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def execute_batch(commands: list[dict]) -> dict:
    staged = []
    for c in commands:  # validate the whole batch first: all-or-nothing like start/abort_operation
        if c.get("op") not in OPS:
            raise BridgeError(f"op not allowed: {c.get('op')}")
        if c["op"] == "place" and c["def_key"] not in MODEL.defs and not any(
                s["op"] == "define_panel" and s["def_key"] == c["def_key"] for s in staged):
            raise BridgeError(f"unknown def {c['def_key']}")
        staged.append(c)
    for c in staged:
        op = c["op"]
        if op == "ensure_material":
            MODEL.materials[c["code"]] = c["color"]
        elif op == "ensure_tag":
            MODEL.tags.add(c["name"])
        elif op == "define_panel":
            MODEL.defs[c["def_key"]] = (c["length"], c["width"], c["thickness"])
        elif op == "define_proxy":
            MODEL.defs[c["def_key"]] = tuple(c["size"])
        elif op == "group":
            MODEL.groups.add(c["key"])
        elif op == "place":
            MODEL.instances.append({"def_key": c["def_key"], "instance_key": c["instance_key"],
                                    "transform": c["transform"], "tag": c.get("tag")})
    return {"created": len(staged)}


def write_obj(path: Path) -> None:
    lines = ["# DesignForge fake bridge — boxes in mm"]
    v = 0
    for lo, hi, key in MODEL.boxes():
        lines.append(f"o {key}")
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                for z in (lo[2], hi[2]):
                    lines.append(f"v {x:.1f} {y:.1f} {z:.1f}")
        for f in ((1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2), (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)):
            lines.append("f " + " ".join(str(v + i) for i in f))
        v += 8
    path.write_text("\n".join(lines) + "\n")


def write_stl(path: Path) -> None:
    out = ["solid designforge"]
    for lo, hi, _ in MODEL.boxes():
        c = lambda ix, iy, iz: (hi[0] if ix else lo[0], hi[1] if iy else lo[1], hi[2] if iz else lo[2])  # noqa: E731
        quads = [((1, 0, 0), [c(1, 0, 0), c(1, 1, 0), c(1, 1, 1), c(1, 0, 1)]),
                 ((-1, 0, 0), [c(0, 0, 1), c(0, 1, 1), c(0, 1, 0), c(0, 0, 0)]),
                 ((0, 1, 0), [c(0, 1, 1), c(1, 1, 1), c(1, 1, 0), c(0, 1, 0)]),
                 ((0, -1, 0), [c(0, 0, 0), c(1, 0, 0), c(1, 0, 1), c(0, 0, 1)]),
                 ((0, 0, 1), [c(0, 0, 1), c(1, 0, 1), c(1, 1, 1), c(0, 1, 1)]),
                 ((0, 0, -1), [c(1, 0, 0), c(0, 0, 0), c(0, 1, 0), c(1, 1, 0)])]
        for n, (a, b, cc, d) in quads:
            for tri in ((a, b, cc), (a, cc, d)):
                out.append(f"facet normal {n[0]} {n[1]} {n[2]}\n outer loop")
                out += [f"  vertex {p[0]:.1f} {p[1]:.1f} {p[2]:.1f}" for p in tri]
                out.append(" endloop\nendfacet")
    out.append("endsolid designforge")
    path.write_text("\n".join(out) + "\n")


def write_png(path: Path, scene: str) -> None:
    from PIL import Image, ImageDraw  # front elevation sketch; real renders come from SketchUp

    boxes = MODEL.boxes()
    xs = [b[0][0] for b in boxes] + [b[1][0] for b in boxes]
    zs = [b[0][2] for b in boxes] + [b[1][2] for b in boxes]
    W, H = 960, 720
    s = 0.85 * min(W / (max(xs) - min(xs)), H / (max(zs) - min(zs)))
    ox, oz = (W - s * (max(xs) - min(xs))) / 2 - s * min(xs), (H + s * (max(zs) - min(zs))) / 2 + s * min(zs)
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    hide_fronts = scene == "Interior"
    for (lo, hi, key), inst in sorted(zip(boxes, MODEL.instances), key=lambda t: -t[0][0][1]):  # back to front
        if hide_fronts and inst.get("tag") == "DF_Fronts":
            continue
        d.rectangle([ox + s * lo[0], oz - s * hi[2], ox + s * hi[0], oz - s * lo[2]], fill="#EEEDE8", outline="#555555")
    d.text((12, 10), f"{scene} — fake bridge preview", fill="#333333")
    im.save(path)


def dispatch(method: str, params: dict) -> dict:
    if method == "ping":
        return {"bridge_version": VERSION, "sketchup_version": "none (fake bridge)"}
    if method == "new_model":
        MODEL.reset()
        return {}
    if method == "execute_batch":
        return execute_batch(params["commands"])
    if method == "add_scenes":
        MODEL.scenes = [s["name"] for s in params["scenes"]]
        return {"scenes": MODEL.scenes}
    if method in ("export", "save"):
        path = safe_path(params["path"])
        fmt = "skp" if method == "save" else params["format"]
        if fmt == "skp":
            path.write_text(json.dumps({"designforge_fake_skp": True, "note": "Placeholder: run SketchUp with the "
                                        "DesignForge Bridge extension for a real .skp", "instances": MODEL.instances}))
        elif fmt == "obj":
            write_obj(path)
        elif fmt == "stl":
            write_stl(path)
        elif fmt == "png":
            if params.get("scene") not in MODEL.scenes:
                raise BridgeError(f"no scene {params.get('scene')}")
            write_png(path, params["scene"])
        else:
            raise BridgeError(f"unsupported export {fmt}")
        return {"path": str(path), "bytes": path.stat().st_size}
    if method == "model_stats":
        boxes = MODEL.boxes()
        lo = [min(b[0][i] for b in boxes) for i in range(3)] if boxes else [0, 0, 0]
        hi = [max(b[1][i] for b in boxes) for i in range(3)] if boxes else [0, 0, 0]
        return {"bbox_mm": [round(hi[i] - lo[i]) for i in range(3)], "instance_count": len(MODEL.instances),
                "definition_count": len(MODEL.defs), "bridge_version": VERSION}
    raise BridgeError(f"unknown method {method}")


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for line in self.rfile:
            req: dict = {}
            try:
                req = json.loads(line)
                if req.get("token") != TOKEN:
                    raise BridgeError("bad token")
                resp = {"id": req.get("id"), "ok": True, **dispatch(req["method"], req.get("params") or {})}
            except BridgeError as e:
                resp = {"id": req.get("id"), "ok": False, "error": str(e), "retryable": e.retryable}
            except Exception as e:  # noqa: BLE001
                resp = {"id": req.get("id"), "ok": False, "error": f"{type(e).__name__}: {e}", "retryable": False}
            self.wfile.write((json.dumps(resp) + "\n").encode())


def main() -> None:
    if not TOKEN:
        raise SystemExit(f"no bridge token: run `make bridge-setup` (creates {_CFG_PATH})")
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as srv:
        print(f"[fake-bridge] {VERSION} listening on 127.0.0.1:{PORT}, job root {JOB_ROOT}", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
