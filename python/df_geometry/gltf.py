"""GltfEngine core: PartGraph → binary glTF (.glb), no third-party dependencies.

Every part is an axis-aligned box after `orient_transform` (MVP rotations are multiples of 90°),
so the mesh is exact. glTF is Y-up in metres: (x, y, z)_mm → (x, z, −y) / 1000, so the front
of the furniture faces +Z, towards a default camera.
"""
from __future__ import annotations

import json
import struct

from df_domain.part_graph import PartGraph
from df_domain.ports import Catalog

from .engine import world_aabb

# (normal, 4 corners as (ix, iy, iz) picking min=0 / max=1 per axis), counter-clockwise from outside
_FACES = [
    ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
    ((-1, 0, 0), [(0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0)]),
    ((0, 1, 0), [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)]),
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
    ((0, 0, -1), [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)]),
]
_INDICES = [i for f in range(6) for i in (4 * f, 4 * f + 1, 4 * f + 2, 4 * f, 4 * f + 2, 4 * f + 3)]


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _colour(hex_colour: str) -> list[float]:
    h = hex_colour.lstrip("#")
    return [round(_srgb_to_linear(int(h[i:i + 2], 16) / 255), 4) for i in (0, 2, 4)] + [1.0]


def part_graph_to_glb(graph: PartGraph, catalog: Catalog) -> bytes:
    codes = sorted({p.material_code for p in graph.parts})
    materials = []
    for code in codes:
        m = catalog.material(code)
        materials.append({"name": m.sketchup_material_name,
                          "pbrMetallicRoughness": {"baseColorFactor": _colour(m.colour_hex),
                                                   "metallicFactor": 0.0, "roughnessFactor": 0.85}})
    mat_index = {c: i for i, c in enumerate(codes)}

    blob = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []
    meshes: list[dict] = []
    nodes: list[dict] = []

    def add_view(data: bytes, target: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        buffer_views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(buffer_views) - 1

    for p in graph.parts:
        (x0, y0, z0), (x1, y1, z1) = world_aabb(p)
        lo = (x0 / 1000, z0 / 1000, -y1 / 1000)   # glTF min corner
        hi = (x1 / 1000, z1 / 1000, -y0 / 1000)   # glTF max corner
        pos, nrm = [], []
        for normal, corners in _FACES:
            for c in corners:
                pos.extend(hi[a] if c[a] else lo[a] for a in range(3))
                nrm.extend(normal)
        pv = add_view(struct.pack(f"<{len(pos)}f", *pos), 34962)
        nv = add_view(struct.pack(f"<{len(nrm)}f", *nrm), 34962)
        iv = add_view(struct.pack(f"<{len(_INDICES)}H", *_INDICES), 34963)
        base = len(accessors)
        accessors += [
            {"bufferView": pv, "componentType": 5126, "count": 24, "type": "VEC3", "min": list(lo), "max": list(hi)},
            {"bufferView": nv, "componentType": 5126, "count": 24, "type": "VEC3"},
            {"bufferView": iv, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ]
        meshes.append({"name": p.key, "primitives": [{
            "attributes": {"POSITION": base, "NORMAL": base + 1}, "indices": base + 2,
            "material": mat_index[p.material_code]}]})
        nodes.append({"name": p.key, "mesh": len(meshes) - 1, "extras": {
            "role": p.role, "label": p.label, "material": p.material_code,
            "size_mm": [p.length, p.width, p.thickness], "cut_mm": [p.cut_length, p.cut_width]}})

    root = {"name": "furniture", "children": list(range(len(nodes))),
            "extras": {"graph_hash": graph.graph_hash, "generator": graph.generator_version}}
    nodes.append(root)
    while len(blob) % 4:
        blob.append(0)
    doc = {
        "asset": {"version": "2.0", "generator": "DesignForge GltfEngine"},
        "scene": 0, "scenes": [{"nodes": [len(nodes) - 1]}],
        "nodes": nodes, "meshes": meshes, "materials": materials,
        "accessors": accessors, "bufferViews": buffer_views, "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    return (struct.pack("<III", 0x46546C67, 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
