"""Build a local, reproducible window cache for rapid TinyML experiments."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ml.preprocessing.wisdom48 import build_split


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/cache/wisdom48_windows.npz"))
    args = parser.parse_args()
    partitions = {
        "train": {"lab", "corridor"},
        "validation": {"parking"},
        "test": {"yard"},
    }
    cached: dict[str, np.ndarray] = {}
    for name, locations in partitions.items():
        x, y, groups = build_split(args.data, locations)
        cached[f"x_{name}"] = x
        cached[f"y_{name}"] = y
        cached[f"groups_{name}"] = np.asarray(groups)
        print(f"{name}: {x.shape}, {len(set(groups))} traces")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, **cached)
    print(args.out)


if __name__ == "__main__":
    main()
