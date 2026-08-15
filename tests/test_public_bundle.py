from pathlib import Path

from scripts.validate_public_bundle import validate


def test_checked_in_offline_bundle_can_validate(tmp_path):
    # Missing files are correctly reported.
    errors = validate(Path(tmp_path))
    assert any("missing directory.v1.json" in error for error in errors)
