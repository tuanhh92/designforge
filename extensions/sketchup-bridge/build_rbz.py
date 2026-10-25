"""Package the DesignForge Bridge extension as dist/designforge_bridge.rbz (a zip SketchUp installs)."""
from __future__ import annotations

import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "dist" / "designforge_bridge.rbz"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    files = [HERE / "designforge_bridge.rb", *sorted((HERE / "designforge_bridge").rglob("*.rb"))]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(HERE).as_posix())  # loader at the root, code in designforge_bridge/
    print(f"{OUT} ({OUT.stat().st_size} bytes): " + ", ".join(f.relative_to(HERE).as_posix() for f in files))


if __name__ == "__main__":
    main()
