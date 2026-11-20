"""Classify cyclic four-site energies under C1 transport and a fixed contact cost."""
from collections import Counter
from itertools import product
import importlib.util
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADD_PATH = HERE.parents[1] / "ADD_NEIGHBOR_SYNTHESIS_20261117" / "verify.py"
spec = importlib.util.spec_from_file_location("named_add_reference", ADD_PATH)
add = importlib.util.module_from_spec(spec)
spec.loader.exec_module(add)


def counts(word, width):
    n = len(word)
    return Counter(tuple(word[(i + j) % n] for j in range(width)) for i in range(n))


def column(motif):
    a, b, c, d = motif
    return 64 * a + 16 * b + 4 * c + d


def equation(before, after, contact):
    # Unknowns 0..255 are f(abcd) = eta(abcd) + eps(ab); column 256 is h.
    coefficients = counts(before, 4)
    coefficients.subtract(counts(after, 4))
    terms = {column(motif): value for motif, value in coefficients.items() if value}
    if contact:
        terms[256] = -1
    return terms


def finite_constraints():
    """Every I row is a complete synchronous update with exactly one merge."""
    rows = []
    for n in range(3, 7):
        for word in product(range(4), repeat=n):
            if word != add.cyclic(word):
                continue
            state = add.named(word)
            moved = add.word(add.transport(state))
            rows.append(equation(word, moved, False))
            if word.count(3) == 0 and add.nf(word) == 1:
                merged = add.word(add.interact(state))
                assert len(merged) == n - 1 and add.nf(merged) == 0
                assert add.equal(add.interact(add.interact(state)), state)
                rows.append(equation(word, merged, True))
    return rows


def rank_mod_two(rows):
    # Each independent row modulo 2 certifies a nonzero integer minor over R.
    pivots = {}
    for terms in rows:
        bits = sum(1 << i for i, value in terms.items() if value % 2)
        while bits:
            lead = bits.bit_length() - 1
            if lead not in pivots:
                pivots[lead] = bits
                break
            bits ^= pivots[lead]
    return len(pivots)


def analytic_kernel():
    # Cyclic gradients + graph length + the two conserved bit counts.
    motifs = list(product(range(4), repeat=4))
    columns = {triplet: {} for triplet in product(range(4), repeat=3)}
    for m in motifs:
        i = column(m)
        if m[:3] != m[1:]:
            columns[m[:3]][i] = 1
            columns[m[1:]][i] = -1
    length = {i: 1 for i in range(257)}  # f=1, h=1
    a = {column(m): 1 for m in motifs if m[0] & 1}
    b = {column(m): 1 for m in motifs if m[0] & 2}
    return [*columns.values(), length, a, b]


def four_ones(w):
    return sum(value for motif, value in counts(w, 4).items() if all(s & 1 for s in motif))


def main():
    rows = finite_constraints()
    generators = analytic_kernel()
    assert all(sum(v * g.get(k, 0) for k, v in r.items()) == 0
               for r in rows for g in generators)
    rank, kernel = rank_mod_two(rows), rank_mod_two(generators)
    assert (rank, kernel, rank + kernel) == (191, 66, 257)

    published = json.loads((HERE.parent / "CHECKS.json").read_text())
    eta = {tuple(map(int, key)): value for key, value in published["ETA"].items()}
    eps = {tuple(map(int, key)): value for key, value in published["EPS"].items()}
    contrast = {m: (-1) ** m.count(2) for m in product((1, 2), repeat=4)}
    pairs = []
    for p in published["pairs"]:
        a, b = (tuple(map(int, p[key])) for key in ("A", "B"))
        diff = counts(a, 4)
        diff.subtract(counts(b, 4))
        sign = diff[(1, 1, 1, 1)]
        assert abs(sign) == 1 and dict(diff) == {m: sign * d for m, d in contrast.items()}
        assert counts(a, 2) == counts(b, 2)
        assert len(a) == len(b) == 24 and Counter(a) == Counter(b) == {1: 12, 2: 12}
        frozen = sum((eta[m] + eps[m[:2]]) * d for m, d in diff.items())
        assert frozen == p["delta_E"]
        pairs.append({"pair": p["pair"], "contrast_sign": sign, "frozen_delta": frozen,
                      "fixed_contact_delta": 0, "neighbor_sensitive_delta": four_ones(a) - four_ones(b)})
    # A Q-invariant local diagnostic, with two isolated merges at equal composition.
    examples = {}
    for w in ("111120", "111210"):
        src = tuple(map(int, w))
        state = add.named(src)
        dst = add.word(add.interact(state))
        assert add.nf(src) == 1 and src.count(3) == 0
        examples[w] = four_ones(src) - four_ones(dst)
    assert list(examples.values()) == [0, -1]
    # Raw inputs from the pinned GitHub LATE_TRANSFER.json cited in REPORT.md.
    heating, n_post = 0.039999949024044065, 3.0447552200318295
    ratio_fs = 7 / 8 * (4 / 11) ** (4 / 3) * n_post
    target = heating * (1 + ratio_fs) * math.pi**2 / 15
    assert math.isclose(target, 0.044518075411783944, rel_tol=1e-13)
    return {
        "constraint_rows_including_redundancies": len(rows), "rank_over_F2": rank,
        "kernel_rank_over_F2": kernel, "rank_over_reals": rank, "kernel_dimension_over_reals": kernel,
        "pairs": pairs, "frozen_contrast": sum(eta[m] * d for m, d in contrast.items()),
        "neighbor_sensitive_contact_examples": examples, "late_transfer_over_Tgamma4": target,
        "xi_if_efficiency_times_density_times_gap_is_one": target**0.25,
        "required_efficiency_times_density_times_gap": {str(x): target/x**4 for x in (1, 0.5, 0.45, 0.4)},
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
