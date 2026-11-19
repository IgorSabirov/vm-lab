"""Reproduce finite C2 comparisons and nuclear table diagnostics using only Python 3."""
from bisect import bisect_right
from collections import defaultdict
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
import json
from math import log
from pathlib import Path
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
RULE = HERE.parent / "ADD_NEIGHBOR_SYNTHESIS_20261117" / "verify.py"
TABLES = (HERE.parent / "NOW_PROJECT_INTEGRATION_20261119" / "evidence"
          / "Review_C2_BH1_S3_20261119.zip")
spec = spec_from_file_location("r130_reference", RULE)
r = module_from_spec(spec)
spec.loader.exec_module(r)
EPS = (1, -1)


def step(w):
    return r.word(r.forward(r.named(w), EPS))


def macro(w):
    pairs = tuple(zip(w, w[1:] + w[:1]))
    return len(w), tuple(w.count(s) for s in range(16)), pairs.count((1, 2)), pairs.count((8, 4))


def named_checks():
    def interact(x):
        return r.interact(x, EPS)

    def transport(x):
        return r.transport(x, 2)

    def literal(x):
        return tuple(reversed(r.transport(x, 2, True)))

    def reverse_time(x):
        return interact(r.r2(x))

    counts = defaultdict(int)
    inputs = 0
    for n in range(1, 4):
        for w in product(range(16), repeat=n):
            inputs += 1
            x = r.named(w)
            tau = tuple((name, (w[(i+1) % n] & 5) | (w[(i-1) % n] & 10))
                        for i, (name, _) in enumerate(x))
            checks = {
                "I2_squared": (interact(interact(x)), x),
                "R_squared": (r.r2(r.r2(x)), x),
                "RI2_I2R": (r.r2(interact(x)), interact(r.r2(x))),
                "RQR_Qinverse": (r.r2(transport(r.r2(x))), r.transport(x, 2, True)),
                "T_squared": (reverse_time(reverse_time(x)), x),
                "TFT_Finverse": (reverse_time(r.forward(reverse_time(x), EPS)), r.backward(x, EPS)),
                "Q_squared_tau": (transport(transport(x)), tau),
                "negative_literal_squared_tau": (literal(literal(x)), tau),
            }
            for name, (actual, expected) in checks.items():
                counts[name] += int(not r.equal(actual, expected))
    assert inputs == 4368 and counts["negative_literal_squared_tau"] == 4096
    assert all(value == 0 for name, value in counts.items() if not name.startswith("negative"))
    return {"inputs": inputs, "failures": dict(counts)}


def census():
    groups = defaultdict(lambda: [set() for _ in range(4)])
    words = 0
    for n in range(1, 5):
        for w in product(range(16), repeat=n):
            if w != r.cyclic(w):
                continue
            words += 1
            y = step(w)
            next_q = macro(y)
            for stored, outcome in zip(groups[macro(w)], (len(y), next_q[1], next_q, len(step(y)))):
                stored.add(outcome)
    ambiguous = [sum(len(outcomes[i]) > 1 for outcomes in groups.values()) for i in range(4)]
    maximum = max(len(outcomes[2]) for outcomes in groups.values())
    assert (words, len(groups), ambiguous, maximum) == (17984, 5141, [0, 4050, 4052, 2203], 6)
    return dict(rotation_classes=words, groups=len(groups),
                ambiguous=dict(zip(("next_length", "next_histogram", "next_q", "second_length"), ambiguous)),
                max_distinct_next_q=maximum)


def periodic_encounters():
    horizon = 250
    sample = {}
    for k in range(1, 17):
        n = 2*k + 3

        def ring(pos):
            return tuple(2 if i == 0 else 1 if i == pos else 0 for i in range(n))

        a, b = ring(k), ring(k+1)
        starts, observed, lengths = [], [], []
        c = k
        while c <= horizon:
            starts.append(c)
            c += n + len(starts) - 1
        for t in range(horizon+1):
            if macro(a) != macro(b):
                observed.append(t)
            if len(a) != len(b):
                lengths.append(t)
            a, b = step(a), step(b)
        predicted = sorted(t for c in starts for t in (c, c+1) if t <= horizon)
        assert observed == predicted
        assert lengths == [c+1 for c in starts if c < horizon]
        if k in (2, 3):
            sample[str(k)] = {"collision_starts": starts, "q_diff_first_8": observed[:8],
                              "length_diff_first_4": lengths[:4]}
    w = (1, 12, 2)
    trajectory = [w]
    for _ in range(3):
        trajectory.append(step(trajectory[-1]))
    assert [len(v) for v in trajectory] == [3, 4, 6, 7]
    assert trajectory[1].count(3) == trajectory[1].count(12) == 1
    return dict(k_range=[1, 16], inclusive_horizon=horizon, examples=sample,
                two_split_seed=[list(v) for v in trajectory])


def table_checks():
    with ZipFile(TABLES) as z:
        def read(name):
            rows = z.read("temp_rates/" + name + ".txt").decode().splitlines()
            return [tuple(map(float, row.split())) for row in rows if row.strip() and not row.lstrip().startswith("#")]

        tpag = read("linx_t_p__a_g")
        coarse = read("linx_He3_a__Be7_g")
        fine = read("primat_He3_a__Be7_g")

    def interp(t, left, right):
        x, y, _ = left
        u, v, _ = right
        return y+(t-x)*(v-y)/(u-x), y*(t/x)**(log(v/y)/log(u/x))

    errors = []
    for left, right in zip(tpag, tpag[1:]):
        x, y, _ = left
        u, v, _ = right
        lo, hi = max(x, 0.1), min(u, 1.)
        if lo > hi:
            continue
        slope, power = (v-y)/(u-x), log(v/y)/log(u/x)
        candidates = [lo, hi]
        if slope and power != 1:
            critical = power*(y-slope*x)/(slope*(1-power))
            if lo < critical < hi:
                candidates.append(critical)
        for t in candidates:
            linear, powerlaw = interp(t, left, right)
            errors.append((100*(linear/powerlaw-1), t))
    maximum, tpeak = max(errors, key=lambda row: abs(row[0]))
    t = .2179407
    rate, factor = next((r0, f) for t0, r0, f in fine if t0 == t)
    i = bisect_right([row[0] for row in coarse], t)
    differences = [100*(v/rate-1) for v in interp(t, coarse[i-1], coarse[i])]
    assert round(maximum, 5) == 1.08597
    assert [round(d, 5) for d in differences] == [20.82754, -1.41286]
    return dict(tpag=dict(peak_percent=maximum, T9=tpeak, nodes=len(tpag)),
                He3_alpha=dict(T9=t, PRIMAT_rate=rate, PRIMAT_factor=factor,
                               LINX_linear_minus_PRIMAT_percent=differences[0],
                               LINX_loglog_minus_PRIMAT_percent=differences[1]))


if __name__ == "__main__":
    result = dict(rule_sha256=sha256(RULE.read_bytes()).hexdigest(),
                  tables_archive_sha256=sha256(TABLES.read_bytes()).hexdigest(),
                  named=named_checks(), census=census(), collision_family=periodic_encounters(),
                  nuclear_tables=table_checks())
    print(json.dumps(result, indent=2))
