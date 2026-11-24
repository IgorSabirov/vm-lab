"""Compare the order of the archived unfolded gaps with permutation of the same gaps."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np


def ratio(a, b):
    return np.minimum(a, b) / np.maximum(a, b)


def within_blocks(gaps, prefix_blocks):
    blocks = np.split(gaps, prefix_blocks)
    edges = sum(len(b) - 1 for b in blocks)
    observed = sum(ratio(b[:-1], b[1:]).sum() for b in blocks) / edges
    # Any unordered pair is adjacent with probability 2/m in a uniform permutation.
    expected = 0.0
    for b in blocks:
        i, j = np.triu_indices(len(b), 1)
        expected += 2 * ratio(b[i], b[j]).sum() / len(b)
    expected /= edges
    simulations = 9999
    rng = np.random.default_rng(141596)
    extreme = 0
    for _ in range(simulations):
        total = 0.0
        for b in blocks:
            sample = rng.permutation(b)
            total += ratio(sample[:-1], sample[1:]).sum()
        extreme += int(abs(total / edges - expected) >= abs(observed - expected))
    return dict(blocks=prefix_blocks, edges=edges, observed=observed,
                exact_null_mean=expected, difference=observed-expected,
                simulations=simulations, extreme=extreme,
                two_sided_mc_p=(1+extreme)/(1+simulations))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zeros", type=Path)
    raw = parser.parse_args().zeros.read_bytes()
    digest = sha256(raw).hexdigest()
    assert digest == "c3ea7085b25c16caafb43db250efefd171b627a34c3097498027751226d61c28"
    rows = json.loads(raw)["roots"]
    assert [r["n"] for r in rows] == list(range(1, 658))
    t = np.array([float(r["gamma"]) for r in rows[60:]]) / (2*np.pi)
    gaps = np.diff(t * (np.log(t)-1) + 7/8)
    assert len(gaps) == 596 and np.all(gaps > 0)
    print(json.dumps(dict(input_sha256=digest, zero_indices=[61,657], seed=141596,
                          tests=[within_blocks(gaps, k) for k in (1,4)]), indent=2))


if __name__ == "__main__":
    main()
