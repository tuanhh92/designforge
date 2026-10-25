"""Create ~/.designforge/bridge.json, shared by the SketchUp extension and the DesignForge worker.

Keeps an existing file (and its token) unless --force is given. Prints where everything lives.
"""
from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

CONFIG = Path("~/.designforge/bridge.json").expanduser()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=9877)
    ap.add_argument("--job-root", default="~/DesignForge/jobs", help="folder where SketchUp writes .skp/.png/.obj")
    ap.add_argument("--force", action="store_true", help="overwrite an existing config (new token)")
    args = ap.parse_args()

    if CONFIG.exists() and not args.force:
        cfg = json.loads(CONFIG.read_text())
        print(f"Keeping existing {CONFIG}")
    else:
        cfg = {"port": args.port, "token": secrets.token_urlsafe(32),
               "job_root": str(Path(args.job_root).expanduser().resolve())}
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        CONFIG.chmod(0o600)  # the token lets local processes drive SketchUp
        print(f"Wrote {CONFIG}")
    Path(cfg["job_root"]).mkdir(parents=True, exist_ok=True)
    print(f"  port     {cfg['port']}\n  job_root {cfg['job_root']}\n  token    (saved in the file)")


if __name__ == "__main__":
    main()
