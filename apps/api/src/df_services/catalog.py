"""Catalog + rule pack read from the workshop's knowledge folder (knowledge/danh-muc.yaml, quy-cach.yaml).

Single tenant for the MVP; V1 moves these into per-org tables seeded from the same files.
"""
from __future__ import annotations

from uuid import UUID

from df_domain.ports import HardwareInfo, MaterialInfo

from .knowledge import MaterialEntry, get_knowledge

RULE_PACK_ID = UUID("00000000-0000-4000-8000-000000000001")


def _materials() -> dict[str, MaterialEntry]:
    return {m.code: m for m in get_knowledge().catalog.materials if m.active}


class DefaultCatalog:
    def material(self, code: str) -> MaterialInfo:
        m = _materials()[code]
        return MaterialInfo(code, m.kind, m.thickness, m.grain, None, m.name, m.colour)

    def material_entry(self, code: str) -> MaterialEntry:
        return _materials()[code]

    def hardware(self, code: str) -> HardwareInfo:
        h = next(h for h in get_knowledge().catalog.hardware if h.code == code)
        return HardwareInfo(code, h.family, h.params, [], None)

    def edge_band_for(self, material_code: str, thickness: int) -> str:
        return f"EB-{material_code}-{thickness:.1f}"

    def material_codes(self, kind: str | None = None) -> list[str]:
        return [c for c, m in _materials().items() if kind is None or m.kind == kind]

    def hardware_codes(self, family: str | None = None) -> list[str]:
        return [h.code for h in get_knowledge().catalog.hardware if h.active and (family is None or h.family == family)]

    def match_material(self, colour_name: str, colour_hex: str | None, surface: str | None) -> str:
        """Map an AI colour description to the closest stocked board (rules: knowledge/danh-muc.yaml)."""
        boards = [m for m in _materials().values() if m.kind == "sheet"]
        name = (colour_name or "").lower()
        if surface in ("lacquer",) and "wood" not in name:
            painted = next((m for m in boards if m.painted), None)
            if painted:
                return painted.code
        for m in boards:
            if any(w in name for w in m.keywords):
                return m.code
        candidates = [m for m in boards if m.colour_match]
        if colour_hex and len(colour_hex) == 7 and candidates:
            target = _rgb(colour_hex)
            return min(candidates, key=lambda m: sum((a - b) ** 2 for a, b in zip(_rgb(m.colour), target))).code
        default = next((m for m in boards if m.default), boards[0])
        return default.code


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class DefaultRules:
    """Rule pack values from knowledge/quy-cach.yaml, addressed as "group.key" (e.g. "sliding.overlap")."""
    id = RULE_PACK_ID

    @property
    def version(self) -> int:
        return get_knowledge().rules_version

    def get(self, key: str, default=None):
        return get_knowledge().rules.get(key, default)
