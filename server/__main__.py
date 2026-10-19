"""Entry point: python -m server [--config config/server.json]"""

import argparse
import asyncio
import shutil
from pathlib import Path

from .core import ROOT, Server, load_config


def main() -> None:
    ap = argparse.ArgumentParser(description="Madden Forever Blaze server (skeleton)")
    ap.add_argument("--config", default=str(ROOT / "config" / "server.json"))
    args = ap.parse_args()

    path = Path(args.config)
    if not path.exists():
        example = ROOT / "config" / "server.example.json"
        shutil.copy(example, path)
        print(f"created {path} from {example.name}")

    server = Server(load_config(path))
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
