"""Workshop knowledge loaded from the `knowledge/` folder (see knowledge/README.md).

- quy-cach.yaml   → rule pack values (nested groups flattened to "group.key")
- danh-muc.yaml   → materials and hardware the workshop stocks
- nhan-dien-anh.md → recognition notes appended to the vision prompt (text after the first "---" line)

Files are validated on load so a typo fails loudly at startup instead of producing wrong parts.
Loaded once per process (restart API/worker after editing); DF_KNOWLEDGE_DIR overrides the folder.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# apps/api/src/df_services/knowledge.py → repository root is four levels up from this package
DEFAULT_DIR = Path(__file__).resolve().parents[4] / "knowledge"


class KnowledgeError(RuntimeError):
    pass


class MaterialEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-_.]*$")
    kind: Literal["sheet", "profile"]
    thickness: int = Field(ge=0, le=100)
    grain: Literal["none", "length", "width"] = "none"
    name: str
    name_vi: str | None = None
    colour: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    keywords: list[str] = Field(default_factory=list)
    colour_match: bool = False
    painted: bool = False
    default: bool = False
    active: bool = True


class HardwareEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9\-_.]*$")
    family: str
    name_vi: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class CatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    materials: list[MaterialEntry]
    hardware: list[HardwareEntry]

    @model_validator(mode="after")
    def _unique_codes(self) -> "CatalogFile":
        for kind, items in (("materials", self.materials), ("hardware", self.hardware)):
            codes = [i.code for i in items]
            dupes = sorted({c for c in codes if codes.count(c) > 1})
            if dupes:
                raise ValueError(f"duplicate {kind} codes: {dupes}")
        return self


class Knowledge(BaseModel):
    folder: Path
    rules_version: int
    rules: dict[str, Any]          # flattened "group.key" → value
    catalog: CatalogFile
    recognition_notes: str         # "" when the file is missing
    fingerprint: str               # changes whenever any knowledge file changes


def _flatten(tree: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in tree.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise KnowledgeError(f"missing {path} (see knowledge/README.md)")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise KnowledgeError(f"{path.name}: not valid YAML — {e}") from e
    if not isinstance(data, dict):
        raise KnowledgeError(f"{path.name}: expected a mapping at the top level")
    return data


def load(folder: Path) -> Knowledge:
    rules_path, catalog_path, notes_path = folder / "quy-cach.yaml", folder / "danh-muc.yaml", folder / "nhan-dien-anh.md"
    raw_rules = _read_yaml(rules_path)
    version = raw_rules.pop("version", None)
    if not isinstance(version, int) or version < 1:
        raise KnowledgeError(f"{rules_path.name}: `version` must be a whole number ≥ 1")
    rules = _flatten(raw_rules)
    bad = {k: v for k, v in rules.items() if not isinstance(v, (int, str)) or isinstance(v, bool)}
    if bad:
        raise KnowledgeError(f"{rules_path.name}: values must be whole numbers (mm) or codes, got {bad}")
    try:
        catalog = CatalogFile.model_validate(_read_yaml(catalog_path))
    except ValidationError as e:
        raise KnowledgeError(f"{catalog_path.name}: {e}") from e
    codes = {h.code for h in catalog.hardware} | {m.code for m in catalog.materials}
    missing = {k: v for k, v in rules.items() if k.startswith("hardware.") and v not in codes}
    if missing:
        raise KnowledgeError(f"{rules_path.name}: hardware codes not in {catalog_path.name}: {missing}")
    notes = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else ""
    notes = notes.split("\n---\n", 1)[1].strip() if "\n---\n" in notes else ""
    digest = hashlib.sha256()
    for p in (rules_path, catalog_path, notes_path):
        if p.is_file():
            digest.update(p.read_bytes())
    return Knowledge(folder=folder, rules_version=version, rules=rules, catalog=catalog,
                     recognition_notes=notes, fingerprint=digest.hexdigest()[:12])


@lru_cache
def get_knowledge() -> Knowledge:
    return load(Path(os.environ.get("DF_KNOWLEDGE_DIR", DEFAULT_DIR)).expanduser().resolve())
