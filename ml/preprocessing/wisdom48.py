"""WISDOM ESP32 log reader matching the SafeSense 48-carrier edge pipeline."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import hashlib
import numpy as np

RAW_ORDER = tuple(range(0, 32)) + tuple(range(-32, 0))
# Preserve the ESP32 CSI payload's physical carrier order.  Sorting carriers by
# signed index here would silently swap the positive and negative halves versus
# the firmware preprocessor.
DATA_CARRIERS = tuple(
    carrier
    for carrier in RAW_ORDER
    if -26 <= carrier <= 26 and carrier and carrier not in {-21, -7, 7, 21}
)
EDGE_POSITIONS = tuple(RAW_ORDER.index(carrier) for carrier in DATA_CARRIERS)
CLASS_NAMES = ("empty", "standing", "sitting", "sittingupdown", "jumping", "walking")
LABELS = {name: index for index, name in enumerate(CLASS_NAMES)}
FILENAME = re.compile(r"^(?P<location>[^_]+)_(?P<label>empty|standing|sitting|sittingupdown|jumping|walking)(?:_fast)?_")

@dataclass(frozen=True)
class Trace:
    path: Path
    location: str
    label: str

def discover(root: Path) -> list[Trace]:
    traces=[]
    for path in sorted(root.rglob("*.txt")):
        match=FILENAME.match(path.name)
        if match: traces.append(Trace(path, match["location"], match["label"]))
    return traces

def _frame(line: str) -> np.ndarray | None:
    if "CSI_DATA" not in line: return None
    parts=[part for part in line.split("CSI_DATA", 1)[1].split(",") if part]
    # The public format has 24 metadata fields followed by its bracketed IQ vector.
    if len(parts) != 25: return None
    matches=re.findall(r"-?\d+", parts[-1])
    if len(matches) != 128: return None
    values=np.asarray(matches, dtype=np.float32)
    imaginary, real=values[0::2], values[1::2]
    amplitude=np.hypot(real, imaginary)
    return amplitude[np.asarray(EDGE_POSITIONS)]

def windows(trace: Trace, window_size: int = 100, trim_frames: int = 1500) -> np.ndarray:
    frames=[]
    with trace.path.open("r", encoding="utf-8", errors="ignore") as source:
        for line in source:
            sample=_frame(line)
            if sample is not None: frames.append(sample)
    matrix=np.asarray(frames, dtype=np.float32)
    if len(matrix) <= trim_frames * 2: return np.empty((0, window_size, 48), dtype=np.float32)
    matrix=matrix[trim_frames:-trim_frames]
    usable=(len(matrix)//window_size)*window_size
    return matrix[:usable].reshape(-1, window_size, 48)

def build_split(root: Path, locations: set[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    xs=[]; ys=[]; groups=[]; seen_content=set()
    for trace in discover(root):
        if trace.location not in locations: continue
        with trace.path.open("rb") as source:
            content_hash = hashlib.file_digest(source, "sha256").digest()
        if content_hash in seen_content:
            continue  # Public folder contains byte-identical walking/walking_fast aliases.
        seen_content.add(content_hash)
        trace_windows=windows(trace)
        if not len(trace_windows): continue
        xs.append(trace_windows); ys.extend([LABELS[trace.label]]*len(trace_windows)); groups.extend([str(trace.path.relative_to(root))]*len(trace_windows))
    if not xs: raise ValueError(f"no usable traces in {sorted(locations)}")
    return np.concatenate(xs), np.asarray(ys, dtype=np.int64), groups
