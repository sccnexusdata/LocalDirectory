from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from localdirectory.config import load_config
from localdirectory.runner import DirectoryRunner


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Harvest and publish a local service directory")
    sub = p.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run a configured harvest")
    run.add_argument("--config", default="config/lewes.yaml")
    run.add_argument("--offline", action="store_true", help="Run deterministic/manual sources only")

    init = sub.add_parser("init", help="Create a postcode/radius configuration")
    init.add_argument("--name", required=True)
    init.add_argument("--location", required=True)
    init.add_argument("--postcode", required=True)
    init.add_argument("--latitude", required=True, type=float)
    init.add_argument("--longitude", required=True, type=float)
    init.add_argument("--radius-miles", default=10.0, type=float)
    init.add_argument("--output", required=True)

    inspect = sub.add_parser("inspect", help="Summarise a generated output directory")
    inspect.add_argument("--exports-dir", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command in {None, "run"}:
        config_path = getattr(args, "config", "config/lewes.yaml")
        offline = getattr(args, "offline", False)
        output = DirectoryRunner(load_config(config_path), offline=offline).run()
        print(output)
        return 0
    if args.command == "init":
        radius_km = args.radius_miles * 1.609344
        payload = {
            "project": {"name": args.name, "slug": _slug(args.name)},
            "location": {
                "name": args.location,
                "country": "GB",
                "postcode": args.postcode,
                "latitude": args.latitude,
                "longitude": args.longitude,
                "radius_miles": args.radius_miles,
                "radius_km": round(radius_km, 4),
            },
            "outputs": {"directory": "exports"},
            "policy": {"minimum_independent_sources": 2, "allow_class_a_single_source": True},
            "sources": {"enabled": ["fhrs", "osm_overpass", "companies_house", "json_ld"], "websites": [], "manual_csv": "data/manual/listings.csv"},
        }
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        print(path)
        return 0
    if args.command == "inspect":
        directory = Path(args.exports_dir)
        report = json.loads((directory / "quality-report.json").read_text(encoding="utf-8"))
        print(json.dumps(report["summary"], indent=2))
        return 0
    return 2


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split() if part)
