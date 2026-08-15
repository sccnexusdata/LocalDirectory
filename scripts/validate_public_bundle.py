from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


FORBIDDEN_KEYS = {"manual_verified", "field_provenance"}
BLOCKING_FLAG_PREFIXES = ("field_conflict:", "entity_resolution_conflict:")


def validate(bundle: Path) -> list[str]:
    errors: list[str] = []
    required = ["directory.v1.json", "directory.v1.csv", "directory.v1.geojson", "manifest.v1.json"]
    for name in required:
        if not (bundle / name).exists():
            errors.append(f"missing {name}")
    json_path = bundle / "directory.v1.json"
    if json_path.exists():
        records = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            errors.append("directory.v1.json must be a list")
        else:
            ids = [str(record.get("listing_id") or "") for record in records]
            duplicate_ids = sorted(key for key, count in Counter(ids).items() if key and count > 1)
            if duplicate_ids:
                errors.append(f"duplicate listing_id values: {duplicate_ids[:10]}")
            for index, record in enumerate(records):
                forbidden = FORBIDDEN_KEYS.intersection(record)
                if forbidden:
                    errors.append(f"record {index} exposes forbidden keys: {sorted(forbidden)}")
                if not record.get("publish_safe"):
                    errors.append(f"record {index} is not publish_safe")
                if not record.get("listing_id") or not record.get("name"):
                    errors.append(f"record {index} missing stable identity/name")
                flags = [str(flag) for flag in record.get("quality_flags", [])]
                if any(flag.startswith(BLOCKING_FLAG_PREFIXES) for flag in flags):
                    errors.append(f"record {index} exposes unresolved identity/field conflict")
                if "identity_or_field_conflict" in flags:
                    errors.append(f"record {index} exposes identity_or_field_conflict")
                if not record.get("address_public", True):
                    for key in ("address", "postcode"):
                        if record.get(key):
                            errors.append(f"record {index} exposes {key} although address_public=false")
                    if record.get("latitude") is not None or record.get("longitude") is not None:
                        errors.append(f"record {index} exposes coordinates although address_public=false")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    args = parser.parse_args()
    errors = validate(Path(args.bundle))
    if errors:
        print("PUBLIC BUNDLE VALIDATION FAILED")
        for error in errors:
            print(f" - {error}")
        return 1
    print("Public bundle validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
