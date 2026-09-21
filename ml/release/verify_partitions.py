"""Verify that group-level CSI partitions have no trace or content overlap."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    groups = {name: set(values) for name, values in manifest["groups"].items()}
    hashes = {name: set(values.values()) for name, values in manifest["trace_sha256"].items()}
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if overlap := groups[left] & groups[right]:
            raise SystemExit(f"trace leakage between {left} and {right}: {sorted(overlap)}")
        if overlap := hashes[left] & hashes[right]:
            raise SystemExit(f"byte-identical content leakage between {left} and {right}: {sorted(overlap)}")
    print("PARTITION AUDIT PASSED: no trace or byte-identical content crosses train/validation/test")


if __name__ == "__main__":
    main()
