from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(exports_dir: Path) -> dict:
    quality = json.loads((exports_dir / "quality-report.json").read_text(encoding="utf-8"))
    health = json.loads((exports_dir / "source-health.json").read_text(encoding="utf-8"))
    coverage_path = exports_dir / "coverage-report.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else {}

    failed = [item["source"] for item in health.get("sources", []) if not item.get("ok")]
    summary = quality.get("summary", {})
    total = int(summary.get("total", 0))
    published = int(summary.get("publish_safe", 0))
    coverage_ready = bool(coverage.get("ready", True))
    failed_coverage = [name for name, passed in coverage.get("checks", {}).items() if not passed]

    return {
        "status": "healthy" if not failed and coverage_ready else "degraded",
        "total_records": total,
        "publish_safe_records": published,
        "publication_rate": round(published / total, 4) if total else 0.0,
        "failed_sources": failed,
        "coverage_ready": coverage_ready,
        "failed_coverage_checks": failed_coverage,
        "coverage_metrics": coverage.get("metrics", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exports-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build(Path(args.exports_dir))
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
