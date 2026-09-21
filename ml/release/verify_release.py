"""Fail-closed verification for a candidate SafeSense INT8 model release."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--minimum-macro-f1", type=float, default=0.80)
    args = parser.parse_args()
    manifest_path = args.model_dir / "release_manifest.json"
    model_path = args.model_dir / "wisdom48_int8.tflite"
    normalization_path = args.model_dir / "normalization.npz"
    if not all(path.is_file() for path in (manifest_path, model_path, normalization_path)):
        raise SystemExit("release is incomplete: manifest, TFLite model, and normalization artifact are all required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("shape") != [100, 48, 1] or manifest.get("input_dtype") != "int8" or manifest.get("output_dtype") != "int8":
        raise SystemExit("release input contract is not 100x48x1 fully INT8")
    classes = ["vacant", "stationary", "walking"]
    if manifest.get("classes") != classes:
        raise SystemExit("release class contract must match the three-class firmware output")
    if manifest.get("status") == "DEVELOPMENT_ONLY_NO_HELD_OUT_EVALUATION":
        raise SystemExit("development-only artifact has no independent evaluation")
    if not manifest.get("protocol", {}).get("validation_used"):
        raise SystemExit("release requires a trace-separated validation partition")
    calibration = manifest.get("calibration", {}).get("class_counts", {})
    if any(calibration.get(name, 0) <= 0 for name in classes):
        raise SystemExit("INT8 calibration does not cover every output class")
    if not all(name in manifest for name in ("float_metrics", "int8_metrics", "quantization_delta")):
        raise SystemExit("float-to-INT8 comparison evidence is missing")
    if manifest.get("macro_f1", 0.0) < args.minimum_macro_f1:
        raise SystemExit(f"macro-F1 {manifest.get('macro_f1')} is below release threshold {args.minimum_macro_f1}")
    if manifest.get("tflite_sha256") != sha256(model_path):
        raise SystemExit("TFLite hash does not match manifest")
    for partition in ("train", "validation", "test"):
        if not manifest.get("groups", {}).get(partition) or not manifest.get("trace_sha256", {}).get(partition):
            raise SystemExit(f"{partition} provenance is missing")
    normalization = np.load(normalization_path)
    mean, std = normalization["mean"], normalization["std"]
    if mean.shape != (48,) or std.shape != (48,) or not np.isfinite(mean).all() or not np.isfinite(std).all() or (std <= 0).any():
        raise SystemExit("normalization artifact is invalid")
    try:
        import tensorflow as tf
    except ImportError as error:
        raise SystemExit("TensorFlow is required to inspect the release model contract") from error
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    if input_detail["shape"].tolist() != [1, 100, 48, 1] or input_detail["dtype"] != np.int8:
        raise SystemExit("TFLite input tensor does not match the firmware contract")
    if output_detail["shape"].tolist() != [1, 3] or output_detail["dtype"] != np.int8:
        raise SystemExit("TFLite output tensor does not match the firmware contract")
    print("SAFE TO PACKAGE: manifest contract, INT8 claims, provenance, hash, and macro-F1 gate passed")


if __name__ == "__main__":
    main()
