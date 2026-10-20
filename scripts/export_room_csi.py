"""Export one room commissioning session as a compressed NumPy archive."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from safesense.room_capture import RoomCaptureStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_id", help="Session ID shown in the CSI dashboard")
    parser.add_argument("--out", type=Path, required=True, help="Output .npz path")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".npz":
        parser.error("--out must end in .npz")
    print(json.dumps(RoomCaptureStore().export(args.session_id, args.out)))


if __name__ == "__main__":
    main()
