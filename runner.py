from __future__ import annotations

import argparse

from app.runner import PipelineRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified sports/TV pipeline runner")
    parser.add_argument(
        "--mode",
        required=True,
        choices=("pr", "health", "production", "debug"),
    )
    parser.add_argument(
        "--source",
        default="all",
        help="all, one source, or comma-separated sources",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = PipelineRunner().run(mode=args.mode, source=args.source)
    failed = [item for item in results if item.status == "down"]
    warnings = [item for item in results if item.status == "warning"]
    print(
        f"[RUNNER] mode={args.mode} sources={len(results)} "
        f"failed={len(failed)} warnings={len(warnings)}"
    )
    if failed and args.mode in {"production", "debug", "pr"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
