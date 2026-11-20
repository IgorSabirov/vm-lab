"""Estimate the even fourth cumulant from a preselected stratum of Polyakov fields."""
import argparse
import json
from math import factorial, prod

import numpy as np


def partitions(positions):
    if not positions:
        yield ()
        return
    first, *others = positions
    for groups in partitions(others):
        yield ((first,),) + groups
        for j, group in enumerate(groups):
            yield groups[:j] + ((first,) + group,) + groups[j+1:]


def estimate(counts):
    counts = np.asarray(counts)
    if counts.size != 81 or counts.dtype.kind not in "iu" or np.any(counts < 0):
        raise ValueError("Expected 81 nonnegative integer counts")
    total = int(counts.sum())
    if not total:
        raise ValueError("No accepted windows in stratum")
    p = counts.reshape((3,) * 4) / total
    even = odd = connected = 0.0
    for a in range(3):
        b = (a + 1) % 3
        for labels, sign in (((a,b,a,b), 1), ((b,a,b,a), -1)):
            even += p[labels]
            odd += sign * p[labels]
            def moment(group):
                index = tuple(label if j in group else slice(None) for j, label in enumerate(labels))
                return float(p[index].sum())
            for blocks in partitions(range(4)):
                k = len(blocks) - 1
                connected += (-1)**k * factorial(k) * prod(moment(g) for g in blocks)
    return dict(windows=total, raw_even=even, raw_odd=odd, connected_even=connected)


def combine(rows):
    counts = np.zeros(81, dtype=np.int64)
    settings = None
    for item in rows:
        key = (tuple(item["shape"]), item["stride"], item["cut_rad"])
        if settings is not None and key != settings:
            raise ValueError("Mixed geometry, stride or sector mask")
        settings = key
        for axis in "xyz":
            row = item["axes"][axis]
            n = np.asarray(row["counts"])
            if n.shape != (81,) or n.dtype.kind not in "iu" or np.any(n < 0):
                raise ValueError("Invalid count row")
            if n.sum() != row["accepted"] or not 0 <= row["accepted"] <= row["total"]:
                raise ValueError("Inconsistent coverage")
            counts += n.astype(np.int64)
    return estimate(counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="One JSON measurement per line, single stratum and ensemble")
    args = parser.parse_args()
    with open(args.jsonl, encoding="utf-8") as file:
        print(json.dumps(combine(json.loads(line) for line in file if line.strip()), allow_nan=False))
