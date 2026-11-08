#!/usr/bin/env python3
"""Adversarial checks of the supplied reconstruction; no corrected ADD law is asserted.

Run beside add_backend_smoke_v1.py and ADD_ORIENTATION_CHECK.py:
  python check_author_contract.py > author_contract_results.json
All dependencies are from the Python standard library and supplied source.
"""
import hashlib
import itertools
import json
from pathlib import Path

import add_backend_smoke_v1 as m
from ADD_ORIENTATION_CHECK import canonical_cycle_word as word
from ADD_ORIENTATION_CHECK import motifs


def port_transport(states):
    """One full particle hop: a goes to predecessor, b to successor."""
    n = len(states)
    return m.ring_graph([
        (states[(i + 1) % n][0], states[(i - 1) % n][1],
         states[(i + 1) % n][2], states[(i - 1) % n][3])
        for i in range(n)
    ])


def R_bits(g):
    """Bit exchange stated in Proposition 1; preserves graph and port labels."""
    return m.Graph({n: (s[3], s[2], s[1], s[0]) for n, s in g.states.items()},
                   list(g.edges))


def run():
    states = [(1, 0, 0, 0), (0, 0, 0, 0), (0, 1, 0, 0),
              (0, 0, 0, 0), (0, 0, 0, 0)]
    g = m.ring_graph(states)
    square = m.sqrt_tau(m.sqrt_tau(g))
    expected = port_transport(states)
    results = {
        'source_sha256': hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),
        'source_contract': 'arXiv:2306.07121v2, Fig. 2a, III.B, Definition 4',
        'half_shift_square': {
            'input': word(g), 'actual': word(square), 'expected_tau': word(expected),
            'returns_input_modulo_rotation': word(square) == word(g),
            'equals_port_transport_modulo_rotation': word(square) == word(expected),
        },
    }
    identity_count = 0
    for states3 in itertools.product(itertools.product((0, 1), repeat=4), repeat=3):
        g3 = m.ring_graph(states3)
        identity_count += word(m.sqrt_tau(m.sqrt_tau(g3))) == word(g3)
    results['C2_L3_square_identity'] = {'passed': identity_count, 'tested': 4096}

    cur = m.ring_graph([(1, 0, 0, 0), (0, 0, 0, 0), (0, 1, 0, 0)])
    trace = []
    for t in range(9):
        trace.append({'t': t, 'L': len(cur.states), 'particles': m.particle_counts(cur),
                      'split_merge': list(map(len, motifs(cur))), 'word': word(cur)})
        if t < 8:
            cur = m.f_main(cur)
    results['C1_both_directions_nonexpanding_trace'] = trace

    g = m.ring_graph([(1, 1, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)])
    a, b = m.I2(R_bits(g)), R_bits(m.I2(g))
    results['I2_R_bits_only'] = {
        'I2_R': word(a), 'R_I2': word(b),
        'equal_named': m.graph_equal(a, b),
        'equal_modulo_rotation': word(a) == word(b),
    }
    checks = 0
    for states3 in itertools.product([(0, 0, 0, 0), (1, 0, 0, 0),
                                      (0, 1, 0, 0), (1, 1, 0, 0)], repeat=3):
        g3 = m.ring_graph(states3)
        checks += word(m.I2(m.f_main(m.I2(g3)))) == word(m.f_main_inverse(g3))
    results['C1_T_I2_on_cycle_quotient'] = {'passed': checks, 'tested': 64}
    results['verdict'] = 'SUPPLIED_RECONSTRUCTION_FAILS_ADVERTISED_FREE_TRANSPORT_CONTRACT'
    results['scope'] = ('No author implementation or corrected dynamics was tested. '
                        'The printed Definition 4 needs reconciliation with Fig. 2a '
                        'and the declared square-root-of-transport property.')
    return results


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
