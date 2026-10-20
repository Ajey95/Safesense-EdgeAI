"""Train a CSI-only count baseline from the supplied nested PRoFENCH archive.

The archive has one continuous recording per count. The chronological split and
embargo below prevent shared packets/windows, but cannot measure transfer to a
new recording, room, board, or person arrangement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
)
from safesense.csi_count_features import (
    FEATURE_NAMES, PAIR_POSITIONS, WINDOW_FRAMES, WINDOW_STRIDE,
    selected_amplitudes, window_features,
)


DEFAULT_ARCHIVE = Path(r"C:\Users\AJEYA\Downloads\PRoFENCH-Dataset-20261008T082054Z-1-001.zip")
MAX_PACKET_GAP_SECONDS = 0.5
TRAIN_FRACTION = 0.70
TEST_START_FRACTION = 0.80


@contextmanager
def inner_archive(outer_path: Path, supplied_inner: Path | None) -> Iterator[ZipFile]:
    if supplied_inner is not None:
        with ZipFile(supplied_inner) as inner:
            yield inner
        return
    with tempfile.TemporaryDirectory(prefix="safesense-profench-") as directory:
        inner_path = Path(directory) / "wivi32-dataset.zip"
        with ZipFile(outer_path) as outer:
            nested = [item for item in outer.infolist() if item.filename.endswith("wivi32-dataset.zip")]
            if len(nested) != 1:
                raise ValueError("Expected exactly one nested wivi32-dataset.zip")
            with outer.open(nested[0]) as source, inner_path.open("wb") as target:
                shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
        with ZipFile(inner_path) as inner:
            yield inner


def parse_recording(inner: ZipFile, count: int) -> tuple[np.ndarray, np.ndarray, dict]:
    matches = [name for name in inner.namelist() if name.endswith(f"/csi_{count}.csv")]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one csi_{count}.csv")
    name = matches[0]
    digest = hashlib.sha256()
    amplitudes: list[np.ndarray] = []
    times: list[float] = []
    rejection_reasons: Counter[str] = Counter()
    inferred_labels = 0
    first_word_invalid = 0
    with inner.open(name) as stream:
        header = stream.readline()
        digest.update(header)
        columns = header.decode("utf-8-sig").strip().split(",")
        first_word_column = columns.index("first_word")
        start_time: datetime | None = None
        for line in stream:
            digest.update(line)
            try:
                prefix, sep, following = line.decode("utf-8").partition("[")
                if not sep:
                    raise ValueError("missing_iq_array")
                body, sep, suffix = following.partition("]")
                if not sep:
                    raise ValueError("unterminated_iq_array")
                fields = prefix.rstrip(",").split(",")
                stamp = datetime.fromisoformat(fields[columns.index("timestamp")])
                if start_time is None:
                    start_time = stamp
                seconds = (stamp - start_time).total_seconds()
                iq = np.fromstring(body, sep=",", dtype=np.float32)
                amplitude = selected_amplitudes(iq)
                label = suffix[1:].split(",", 1)[0].strip() if suffix.startswith(",") else ""
                if label:
                    if int(label) != count:
                        raise ValueError("label_disagrees_with_file")
                elif count == 4:  # csi_4.csv uniquely lacks a label column.
                    inferred_labels += 1
                else:
                    raise ValueError("missing_explicit_count_label")
                first_word_invalid += int(fields[first_word_column])
                amplitudes.append(amplitude)
                times.append(seconds)
            except (ValueError, IndexError) as error:
                rejection_reasons[str(error) if isinstance(error, ValueError) else "missing_field"] += 1
    if not amplitudes:
        raise ValueError(f"No valid CSI packets in {name}")
    time_array = np.asarray(times, dtype=np.float64)
    if np.any(np.diff(time_array) <= 0):
        raise ValueError(f"Timestamps in {name} are not strictly increasing")
    return np.stack(amplitudes), time_array, {
        "source_member": name,
        "source_sha256": digest.hexdigest(),
        "valid_packets": len(amplitudes),
        "rejected_packets": sum(rejection_reasons.values()),
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "inferred_count_labels": inferred_labels,
        "first_word_invalid_packets": first_word_invalid,
        "duration_seconds": float(time_array[-1] - time_array[0]),
    }


def partition_bounds(packet_count: int) -> dict[str, tuple[int, int]]:
    train_end = int(packet_count * TRAIN_FRACTION)
    test_start = int(packet_count * TEST_START_FRACTION)
    if train_end < WINDOW_FRAMES or packet_count - test_start < WINDOW_FRAMES:
        raise ValueError("Recording too short for blocked split")
    return {"train": (0, train_end), "embargo": (train_end, test_start), "test": (test_start, packet_count)}


def make_windows(
    amplitude: np.ndarray, times: np.ndarray, bounds: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]]]:
    first, stop = bounds
    features: list[np.ndarray] = []
    starts: list[tuple[int, int]] = []
    for start in range(first, stop - WINDOW_FRAMES + 1, WINDOW_STRIDE):
        end = start + WINDOW_FRAMES
        if np.max(np.diff(times[start:end])) > MAX_PACKET_GAP_SECONDS:
            continue
        features.append(window_features(amplitude[start:end]))
        starts.append((start, end))
    if not features:
        raise ValueError("No contiguous CSI windows in the requested partition")
    return np.stack(features), np.asarray([times[a] for a, _ in starts]), starts


def score(y_true: np.ndarray, y_pred: np.ndarray, counts: list[int]) -> dict:
    report = classification_report(y_true, y_pred, labels=counts, output_dict=True, zero_division=0)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=counts, average="macro", zero_division=0)),
        "count_mae": float(mean_absolute_error(y_true, y_pred)),
        "confusion_matrix_rows_actual_columns_predicted": confusion_matrix(y_true, y_pred, labels=counts).tolist(),
        "per_count": {str(count): report[str(count)] for count in counts},
    }


def train(outer_path: Path, supplied_inner: Path | None, counts: list[int], output: Path) -> dict:
    if not counts or len(set(counts)) != len(counts) or any(count < 0 or count > 7 for count in counts):
        raise ValueError("Counts must be unique integers between 0 and 7")
    x_train: list[np.ndarray] = []
    y_train: list[np.ndarray] = []
    x_test: list[np.ndarray] = []
    y_test: list[np.ndarray] = []
    replay_windows: list[np.ndarray] = []
    sources: dict[str, dict] = {}
    with inner_archive(outer_path, supplied_inner) as inner:
        for count in counts:
            amplitude, times, source = parse_recording(inner, count)
            bounds = partition_bounds(len(amplitude))
            train_x, _, train_spans = make_windows(amplitude, times, bounds["train"])
            test_x, _, test_spans = make_windows(amplitude, times, bounds["test"])
            if train_spans[-1][1] > bounds["train"][1] or test_spans[0][0] < bounds["test"][0]:
                raise AssertionError("A window crossed the partition embargo")
            x_train.append(train_x)
            y_train.append(np.full(len(train_x), count, dtype=np.int8))
            x_test.append(test_x)
            y_test.append(np.full(len(test_x), count, dtype=np.int8))
            replay_windows.append(np.stack([amplitude[start:end] for start, end in test_spans]))
            source.update({
                "packet_ranges_end_exclusive": {key: list(value) for key, value in bounds.items()},
                "train_windows": len(train_x),
                "test_windows": len(test_x),
                "train_last_window_end_exclusive": train_spans[-1][1],
                "test_first_window_start": test_spans[0][0],
            })
            sources[str(count)] = source
            print(f"count={count} packets={len(amplitude)} rejected={source['rejected_packets']} "
                  f"train_windows={len(train_x)} test_windows={len(test_x)}", flush=True)
    train_x = np.concatenate(x_train)
    train_y = np.concatenate(y_train)
    test_x = np.concatenate(x_test)
    test_y = np.concatenate(y_test)
    baseline = DummyClassifier(strategy="most_frequent").fit(train_x, train_y)
    model = RandomForestClassifier(
        n_estimators=300, min_samples_leaf=3, max_features="sqrt", random_state=42, n_jobs=-1
    ).fit(train_x, train_y)
    predictions = model.predict(test_x)
    evaluation = {
        "status": "WITHIN_RECORDING_ONLY_NOT_LIVE_VALIDATED",
        "counts": counts,
        "train_windows": len(train_y),
        "test_windows": len(test_y),
        "model": score(test_y, predictions, counts),
        "majority_baseline": score(test_y, baseline.predict(test_x), counts),
        "split": {
            "method": "chronological_per_count_70pct_train_10pct_embargo_20pct_test_before_windowing",
            "window_frames": WINDOW_FRAMES,
            "stride_frames": WINDOW_STRIDE,
            "max_packet_gap_seconds": MAX_PACKET_GAP_SECONDS,
            "independent_recordings_per_count": 1,
            "cross_session_generalization_measured": False,
        },
        "features": {
            "source": "CSI I/Q only; same 50 pair positions as SafeSense RX WISDOM_CSI serial export",
            "pair_positions": PAIR_POSITIONS.tolist(),
            "names": FEATURE_NAMES,
            "excluded": ["count label", "sample_ID", "timestamp", "file name", "RSSI", "camera image", "YOLO annotation", "radio metadata"],
        },
        "sources": sources,
        "limitation": (
            "Each count has only one contiguous recording. Disjoint temporal windows and the embargo "
            "prevent direct sample overlap, but count remains confounded with recording/session. "
            "The score cannot establish accuracy in a new room or on SafeSense hardware."
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    model_path = output / "model.joblib"
    joblib.dump({"model": model, "counts": counts, "pair_positions": PAIR_POSITIONS.tolist(),
                 "window_frames": WINDOW_FRAMES, "feature_names": FEATURE_NAMES}, model_path, compress=3)
    evaluation["model_sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    replay_path = output / "replay_windows.npz"
    np.savez_compressed(replay_path, windows=np.concatenate(replay_windows), labels=test_y)
    evaluation["replay_sha256"] = hashlib.sha256(replay_path.read_bytes()).hexdigest()
    (output / "evaluation.json").write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "accuracy": evaluation["model"]["accuracy"],
                      "macro_f1": evaluation["model"]["macro_f1"], "count_mae": evaluation["model"]["count_mae"]}, indent=2))
    return evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outer-zip", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--inner-zip", type=Path, help="Use an already staged nested ZIP")
    parser.add_argument("--counts", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--output", type=Path, default=Path("ml/models/profench_count_012_blocked"))
    args = parser.parse_args()
    train(args.outer_zip, args.inner_zip, args.counts, args.output)


if __name__ == "__main__":
    main()
