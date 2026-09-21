"""Generate the TFLite Micro model and preprocessing headers for ESP-IDF."""
import argparse
from pathlib import Path
import numpy as np


def c_array(values: bytes) -> str:
    return ", ".join(f"0x{value:02x}" for value in values)


def c_floats(values: np.ndarray) -> str:
    return ", ".join(f"{float(value):.9g}f" for value in values)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("input",type=Path)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    normalization = np.load(args.normalization)
    mean, std = normalization["mean"], normalization["std"]
    if mean.shape != (48,) or std.shape != (48,) or not np.isfinite(mean).all() or not np.isfinite(std).all() or (std <= 0).any():
        raise SystemExit("normalization must contain finite 48-element mean/std arrays with positive std")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(
        "#pragma once\n#include <cstddef>\n#include <cstdint>\n"
        "alignas(16) const unsigned char g_wisdom48_model[] = {" + c_array(args.input.read_bytes()) + "};\n"
        "const size_t g_wisdom48_model_len = sizeof(g_wisdom48_model);\n",
        encoding="utf-8",
    )
    (args.out.parent / "wisdom48_normalization.h").write_text(
        "#pragma once\n"
        "static const float g_wisdom48_mean[48] = {" + c_floats(mean) + "};\n"
        "static const float g_wisdom48_std[48] = {" + c_floats(std) + "};\n",
        encoding="utf-8",
    )
if __name__=="__main__": main()
