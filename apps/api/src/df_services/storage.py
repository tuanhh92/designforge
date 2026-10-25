"""Blob storage. MVP: local filesystem under STORAGE_DIR, served by the API.

Keys are relative POSIX paths: designs/{design_id}/images/{sha256}.jpg,
designs/{design_id}/specs/{spec_id}/model.glb … A key never contains '..'.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True)
class StoredBlob:
    key: str
    bytes: int
    sha256: str


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError(f"storage key escapes root: {key!r}")
        return p

    def put(self, key: str, data: bytes) -> StoredBlob:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)  # atomic: readers never see a half-written file
        return StoredBlob(key, len(data), hashlib.sha256(data).hexdigest())

    def put_file(self, key: str, src: Path) -> StoredBlob:
        return self.put(key, src.read_bytes())

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()


@lru_cache
def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)
