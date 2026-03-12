from __future__ import annotations

import argparse
import os
from pathlib import Path

from .pipeline import run_once
from .queue_jobs import refresh_noon_queue
from .settings import load_config


def _default_queue_path() -> str:
    data_dir = os.getenv("XAP_DATA_DIR")
    if data_dir:
        return str((Path(data_dir).resolve() / "queue_plan.json"))
    return "queue_plan.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="X auto poster for AI x Design")
    p.add_argument("command", choices=["run-once", "refresh-noon-queue"])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--slot", choices=["morning", "noon", "evening"], default=None)
    p.add_argument("--queue-path", default=_default_queue_path())
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    queue_path = args.queue_path or _default_queue_path()

    if args.command == "run-once":
        run_once(config, slot=args.slot, queue_path=queue_path)
    elif args.command == "refresh-noon-queue":
        refresh_noon_queue(config, queue_path=queue_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
