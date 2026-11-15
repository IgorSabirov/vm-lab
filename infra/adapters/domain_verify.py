"""Independent checks of output data; never calls either adapter or F2 operator."""
from fractions import Fraction
import math
import random


def add_f2(raw, config):
    assert raw['variant'] == 'ADD_F2' and raw['operator'] == 'sqrt_tau(I2(g))'
    assert raw['not_author_code'] is True and raw['not_NOW_integration'] is True
    t = raw['trajectory']; rows = t['rows']
    assert len(rows) == config['steps'] + 1
    rng = random.Random(config['seed'])
    states = [[int(rng.random() < config['bit_probability']) for _ in range(4)]
              for _ in range(config['initial_vertices'])]
    expected = [sum(row[i] for row in states) for i in range(4)]
    for i, row in enumerate(rows):
        assert row['t'] == i and row['p_by_bit'] == expected
        assert row['p_total'] == sum(expected) and row['L'] > 0
        assert math.isclose(row['slot_occupancy_fraction'], sum(expected)/(4*row['L']), abs_tol=1e-14)
        assert row['causal_reachability'] == 'NOT_DEFINED_BY_SPATIAL_GRAPH_ALONE'
    assert rows[0]['L'] == config['initial_vertices']
    return {'status': 'PASS', 'scope': 'Initial condition and particle conservation; not independent proof of F2 law',
            'rows': len(rows), 'expected_particles': expected, 'scientific_acceptance': False}


def serbian(raw, config):
    assert raw['build_passed'] is True
    obs = raw['observed']; records = []
    assert len(raw['matrices']) == len(config['fixtures']) == len(obs['counts']) == 4
    for i, fixture in enumerate(config['fixtures']):
        a, b, c = map(lambda x: Fraction(str(x)), fixture['sides'])
        # Exact determinant by Heron factorisation, independent of eigensolver.
        determinant = ((a+b)**2-c*c)*(c*c-(a-b)**2)/4
        exact = [2, 0, 0] if determinant > 0 else [1, 0, 1] if determinant == 0 else [1, 1, 0]
        assert exact == fixture['expected_inertia']
        matrix = raw['matrices'][i]
        assert matrix[0][0] == float(a*a) and matrix[1][1] == float(b*b)
        assert math.isclose(matrix[0][1], float((a*a+b*b-c*c)/2), abs_tol=2e-15)
        assert matrix[1][0] == matrix[0][1]
        assert obs['status'][i] == 0 and obs['symmetry_adjusted'][i] is False
        assert sum(obs['counts'][i]) == 2 and obs['zero_tolerance'][i] >= 0
        if fixture['category'] in ('valid_pd', 'indefinite'):
            assert obs['counts'][i] == exact and obs['reliable'][i] is True
            assert obs['numerically_ambiguous'][i] is False
        elif fixture['category'] == 'exact_degenerate':
            assert obs['counts'][i] == exact
            # A zero eigenvalue may be flagged ambiguous by this classifier.
        else:
            assert fixture['category'] == 'near_threshold'
            assert obs['numerically_ambiguous'][i] is True
        records.append({'id': fixture['id'], 'exact_inertia': exact, 'category': fixture['category'],
                        'observed': {k: v[i] for k, v in obs.items()}})
    return {'status': 'PASS', 'scope': 'Four Gram controls; mathematical inertia and numerical flags separate',
            'fixtures': records, 'scientific_acceptance': False}


def verify(adapter, raw, config):
    return {'add_f2': add_f2, 'serbian_signature': serbian}[adapter](raw, config)
