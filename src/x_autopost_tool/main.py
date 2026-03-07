from __future__ import annotations

import argparse

from .pipeline import run_once
from .queue_jobs import refresh_noon_queue
from .settings import load_config


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="X auto poster for AI x Design")
    p.add_argument("command", choices=["run-once", "refresh-noon-queue"])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--slot", choices=["morning", "noon", "evening"], default=None)
    p.add_argument("--queue-path", default="queue_plan.json")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    if args.command == "run-once":
        run_once(config, slot=args.slot)
    elif args.command == "refresh-noon-queue":
        refresh_noon_queue(config, queue_path=args.queue_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
