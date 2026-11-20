"""Count ordered windows of four local Polyakov-loop sectors on a periodic spatial lattice."""
import argparse
import json
from pathlib import Path

import numpy as np


def count_windows(field, stride, cut=0.0):
    field = np.asarray(field)
    if field.ndim != 3 or field.dtype.kind != "c" or not np.isfinite(field).all():
        raise ValueError("Expected a finite complex field with axes x,y,z")
    if stride < 1 or any(n % stride or n // stride < 4 for n in field.shape):
        raise ValueError("Each periodic axis must contain at least four distinct, equally spaced sites")
    if not 0 <= cut < np.pi / 3:
        raise ValueError("Invalid exclusion width in radians")
    centers = np.exp(2j * np.pi * np.arange(3) / 3)
    distances = np.abs(np.angle(field[..., None] * np.conjugate(centers)))
    labels = distances.argmin(axis=-1)
    valid = (field != 0) & (distances.min(axis=-1) < np.pi / 3 - cut - 1e-12)
    axes = {}
    for axis, name in enumerate("xyz"):
        code = np.zeros(field.shape, dtype=np.int16)
        keep = np.ones(field.shape, dtype=bool)
        for j in range(4):
            code = 3 * code + np.roll(labels, -j * stride, axis=axis)
            keep &= np.roll(valid, -j * stride, axis=axis)
        counts = np.bincount(code[keep], minlength=81).reshape((3,)*4)
        forward = sum(counts[a, (a+1)%3, a, (a+1)%3] for a in range(3))
        backward = sum(counts[(a+1)%3, a, (a+1)%3, a] for a in range(3))
        axes[name] = dict(total=int(keep.size), accepted=int(keep.sum()),
                          M_plus=int(forward+backward), M_minus=int(forward-backward),
                          counts=counts.ravel().tolist())
    return dict(shape=list(field.shape), stride=stride, cut_rad=cut, axes=axes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("polyakov", type=Path, help="One complex .npy field, trace divided by three")
    parser.add_argument("--stride", type=int, required=True)
    parser.add_argument("--cut", type=float, default=0.0)
    args = parser.parse_args()
    result = count_windows(np.load(args.polyakov, allow_pickle=False), args.stride, args.cut)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
