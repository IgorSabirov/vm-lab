#!/usr/bin/env python3
"""Finite reference checks, distinct from the frozen ADD_FT10_MINIMAL backend.

Ring order follows b -> a; s=a1+2*b1+4*a2+8*b2. Named equality keeps
names and directed edges, and forgets only the list's starting vertex.
No renaming quotient. All-L claims require the proofs in REPORT.md.
"""
from itertools import product
from pathlib import Path
import hashlib
import json
import platform
import time


def left(u):
    return u[1] if u[0] == 'v' else ('l', u)


def right(u):
    return u[2] if u[0] == 'v' else ('r', u)


def join(x, y):
    if x[0] == 'l' and y[0] == 'r' and x[1] == y[1]:
        return x[1]
    return ('v', x, y)


def mirror_name(u):
    if u[0] == 'atom':
        return u
    if u[0] == 'l':
        return right(mirror_name(u[1]))
    if u[0] == 'r':
        return left(mirror_name(u[1]))
    return join(mirror_name(u[2]), mirror_name(u[1]))


def named(w):
    return tuple((('atom', i), s) for i, s in enumerate(w))


def canonical(x):
    return (frozenset(x), frozenset((x[i][0], x[(i+1) % len(x)][0])
                                   for i in range(len(x))))


def equal(x, y):
    return canonical(x) == canonical(y)


def word(x):
    return tuple(s for u, s in x)


def cyclic(w):
    return min(w[i:]+w[:i] for i in range(len(w)))


def transport(x, channels=1, inverse=False):
    a_mask = sum(1 << (2*c) for c in range(channels))
    b_mask = 2*a_mask
    return tuple((join(right(u), left(x[(i+1) % len(x)][0])),
                  ((s & a_mask) | (x[(i+1) % len(x)][1] & b_mask))
                  if inverse else
                  ((s & b_mask) | (x[(i+1) % len(x)][1] & a_mask)))
                 for i, (u, s) in enumerate(x))


def interact(x, eps=(1,)):
    split = {3 << (2*c): ((1 << (2*c), 2 << (2*c)) if e == 1
                         else (2 << (2*c), 1 << (2*c)))
             for c, e in enumerate(eps)}
    merge = {v: k for k, v in split.items()}
    n = len(x)
    starts = {i for i in range(n) if n > 1 and
              (x[i][1], x[(i+1) % n][1]) in merge}
    ends = {(i+1) % n for i in starts}
    start = next(i for i in range(n) if i not in ends)
    out, k = [], 0
    while k < n:
        i = (start+k) % n
        u, s = x[i]
        if i in starts:
            v, t = x[(i+1) % n]
            out.append((join(u, v), merge[s, t]))
            k += 2
        elif s in split:
            a, b = split[s]
            out.extend(((left(u), a), (right(u), b)))
            k += 1
        else:
            out.append((u, s))
            k += 1
    return tuple(out)


def forward(x, eps=(1,)):
    return transport(interact(x, eps), len(eps))


def backward(x, eps=(1,)):
    return interact(transport(x, len(eps), True), eps)


def swap_bits(x):
    return tuple((u, ((s & 1) << 1) | ((s & 2) >> 1)) for u, s in x)


def reflected_swap(x):
    return tuple((mirror_name(u), s) for u, s in reversed(swap_bits(x)))


def r2(x):
    return tuple((u, ((s & 1) << 3) | ((s & 2) << 1) |
                  ((s & 4) >> 1) | ((s & 8) >> 3)) for u, s in x)


def nf(w):
    return sum(w[i] == 1 and w[(i+1) % len(w)] == 2 for i in range(len(w)))


def df(w):
    if not nf(w):
        return 0
    n = len(w)
    return min(k for i in range(n) if w[i] == 1 and w[(i+1) % n] == 2
               for k in range(1, n+1)
               if w[(i+1+k) % n] & 1 or w[(i-k) % n] & 2)


def main():
    started = time.perf_counter()
    c1 = {'states': 0, 'Q_squared_tau': 0, 'I_squared_id': 0,
          'F_Finv_id': 0, 'mirror_swap_commutation': 0,
          'mirror_swap_reversal_failures': 0, 'bit_only_reversal_failures': 0,
          'S_squared_tau': 0, 'vertex_balance': 0, 'nf_increase': 0}
    measure = {'states': 0, 'active': 0, 'not_strict': 0,
               'nf_unchanged': 0, 'df_not_minus_one_when_nf_unchanged': 0,
               'nf_L_not_strict': 0, 'nf_empty_not_strict': 0}
    witness = None
    for n in range(1, 7):
        for w in product(range(4), repeat=n):
            x = named(w)
            y = forward(x)
            v = word(y)
            measure['states'] += 1
            if nf(w):
                measure['active'] += 1
                measure['not_strict'] += (nf(v), df(v)) >= (nf(w), df(w))
                measure['nf_L_not_strict'] += (nf(v), len(v)) >= (nf(w), len(w))
                measure['nf_empty_not_strict'] += (nf(v), v.count(0)) >= (nf(w), w.count(0))
                if nf(v) == nf(w):
                    measure['nf_unchanged'] += 1
                    measure['df_not_minus_one_when_nf_unchanged'] += df(v) != df(w)-1
            if n < 3:
                continue
            c1['states'] += 1
            tau = tuple((x[i][0], (x[(i+1) % n][1] & 1) |
                         (x[(i-1) % n][1] & 2)) for i in range(n))
            c1['Q_squared_tau'] += not equal(transport(transport(x)), tau)
            c1['I_squared_id'] += not equal(interact(interact(x)), x)
            c1['F_Finv_id'] += not equal(forward(backward(x)), x)
            tft = reflected_swap(forward(reflected_swap(x)))
            c1['mirror_swap_commutation'] += not equal(tft, y)
            bad = not equal(tft, backward(x))
            c1['mirror_swap_reversal_failures'] += bad
            if bad and witness is None:
                witness = w
            c1['bit_only_reversal_failures'] += not equal(swap_bits(forward(swap_bits(x))), backward(x))
            s2 = transport(reflected_swap(transport(reflected_swap(x))))
            c1['S_squared_tau'] += not equal(s2, tau)
            c1['vertex_balance'] += len(v)-n != w.count(3)-nf(w)
            c1['nf_increase'] += nf(v) > nf(w)
    c2 = {}
    for eps in product((1, -1), repeat=2):
        counts = {k: 0 for k in ['states', 'I_squared_id', 'R_squared_id', 'RI_IR',
                                  'RQR_Qinv', 'T_squared_id', 'TFT_Finv', 'F_Finv_id']}
        def T(x):
            return interact(r2(x), eps)
        for n in range(1, 4):
            for w in product(range(16), repeat=n):
                x = named(w)
                counts['states'] += 1
                counts['I_squared_id'] += not equal(interact(interact(x, eps), eps), x)
                counts['R_squared_id'] += not equal(r2(r2(x)), x)
                counts['RI_IR'] += not equal(r2(interact(x, eps)), interact(r2(x), eps))
                counts['RQR_Qinv'] += not equal(r2(transport(r2(x), 2)), transport(x, 2, True))
                counts['T_squared_id'] += not equal(T(T(x)), x)
                counts['TFT_Finv'] += not equal(T(forward(T(x), eps)), backward(x, eps))
                counts['F_Finv_id'] += not equal(forward(backward(x, eps), eps), x)
        c2[str(eps)] = counts
    extinction = {}
    for n in (8, 16, 32):
        x = named((1, 2)+(0,)*(n-2))
        t = 0
        while nf(word(x)):
            x = forward(x)
            t += 1
        assert t == n-1
        extinction[n] = t
    ep = (1, -1)
    def fw(w):
        return word(forward(named(w), ep))
    assert cyclic(fw((1, 2, 12))) == cyclic((1, 2, 12))
    assert fw((6, 9)) == (3, 12)
    quiet = [(5, 10, 0, 0)]
    for _ in range(4):
        assert word(interact(named(quiet[-1]), ep)) == quiet[-1]
        quiet.append(fw(quiet[-1]))
    assert quiet[0] == quiet[-1]
    x = named((3, 12))
    forward_lengths = [len(x)]
    for n in range(1, 7):
        x = forward(x, ep)
        assert cyclic(word(x)) == cyclic((0, 2, 12, 1)+(0,)*(n-1))
        forward_lengths.append(len(x))
    x = named((3, 12))
    backward_lengths = [len(x)]
    for n in range(1, 7):
        x = backward(x, ep)
        expected = (6, 9) if n == 1 else (1, 2, 8)+(0,)*(n-2)+(4,)
        assert cyclic(word(x)) == cyclic(expected)
        backward_lengths.append(len(x))
    assert all(c1[k] == 0 for k in c1 if k not in
               {'states', 'mirror_swap_reversal_failures', 'bit_only_reversal_failures'})
    assert c1['mirror_swap_reversal_failures'] > 0
    assert c1['bit_only_reversal_failures'] > 0
    assert measure['not_strict'] == measure['df_not_minus_one_when_nf_unchanged'] == 0
    for eps, row in c2.items():
        assert all(row[k] == 0 for k in row if k not in {'states', 'RI_IR', 'T_squared_id'})
        opposite = eps in {'(1, -1)', '(-1, 1)'}
        assert (row['RI_IR'] == row['T_squared_id'] == 0) == opposite
    result = {'status': 'PASS_WITH_REJECTED_HYPOTHESES', 'scope': 'finite named rings; no global-graph attestation',
              'base_commit': 'fa5e736b5b217ce171a4d1a395544b287d7021b3',
              'python': platform.python_version(), 'elapsed_seconds': time.perf_counter()-started,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'counts_are_failure_counts_except_states': True,
              'C1_L3_to_6': c1, 'C1_first_mirror_reversal_counterexample': witness,
              'C1_measure_L1_to_6': measure, 'C2_L1_to_3_by_chirality': c2,
              'extinction_times': extinction, 'active_constant_size': {'seed': [1, 2, 12], 'I': word(interact(named((1, 2, 12)), ep)), 'F': fw((1, 2, 12))},
              'mixed_activation': {'seed': [6, 9], 'F': fw((6, 9))},
              'quiet_mixed_word_cycle': quiet,
              'mixed_seed_3_12_lengths': {'forward': forward_lengths, 'backward': backward_lengths},
              'word_periodicity_is_not_named_periodicity': True,
              'new_vm_jobs': 0, 'new_production_runs': 0}
    Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
