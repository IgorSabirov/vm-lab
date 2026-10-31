"""Enumerate proposed E002e v002 work. No model build, NESS, or evolution."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).parent
MODELS = ('QS', 'RR_QS', 'IC1_QS')
CENTRAL = (-0.125, 0.0, 0.125)
OUTER = (-0.5, -0.125, 0.0, 0.125, 0.5)


def key(c):
    return (c['model'], c['phi_over_pi'], c['epsilon'], c['node_noise'], c['m6_v_over_J'])


def main():
    full = []
    def add(block, model, phi, epsilon, v=1.0, responses=()):
        c = dict(model=model, phi_over_pi=phi, epsilon=epsilon,
                 node_noise=0.05, m6_v_over_J=v, block=block,
                 tasks=['NESS', *responses])
        c['id'] = 'full_' + hashlib.sha256(json.dumps(key(c)).encode()).hexdigest()[:12]
        assert key(c) not in {key(x) for x in full}
        full.append(c)
    for model in MODELS:
        add('R', model, 0.0, 0.0, responses=('S2a', 'S2b', 'S1a', 'S1b'))
        for epsilon in CENTRAL:
            add('R', model, 0.5, epsilon, responses=('M1', 'M2'))
    for model in MODELS[:2]:
        for epsilon in (-0.5, -0.25, -0.0625, 0.0625, 0.25, 0.5):
            add('F1', model, 0.5, epsilon)
        for v in (0.0, 0.5):
            for epsilon in OUTER:
                add('F2', model, 0.5, epsilon, v=v)
    base_id = {(c['model'], c['phi_over_pi']): c['id'] for c in full
               if c['block'] == 'R' and c['epsilon'] == 0.0}
    freq = [dict(base_id=base_id[(model, 0.5)], omega_over_J=w,
                 input='source_rate_modulation', block='F3',
                 nonzero_shift=w != 0.0)
            for model in MODELS[:2] for w in (-0.5, *[i/2 for i in range(9)])]
    corr = [dict(base_id=base_id[(model, phi)], input=b,
                 outputs=['J_h', 'P_m6_N2', 'K'], block='T')
            for model in MODELS for phi in (0.0, 0.5)
            for b in ('J_h', 'P_m6_N2', 'K')]
    small = []
    for dim in (4, 8):
        for mask in (6, 7):
            for v in (0.0, 0.5, 1.0):
                for epsilon in OUTER:
                    small.append(dict(block='G', dimension=dim, mask=mask,
                                      phi_over_pi=0.5, epsilon=epsilon, v_over_J=v,
                                      changed_edge='12' if mask == 6 else '01'))
            for epsilon in CENTRAL:
                small.append(dict(block='G', dimension=dim, mask=mask,
                                  phi_over_pi=0.0, epsilon=epsilon, v_over_J=1.0,
                                  changed_edge='12' if mask == 6 else '01'))
    peer = [dict(block='peer_reconstruction', dimension=4, mask=7,
                 phi_over_pi=phi, epsilon=e, source=1.0, sink=1.0,
                 node_noise=0.05, jump_convention='sqrt(phi)*n1_only')
            for phi in (0.0, 0.5) for e in (-4.0, -0.125, 0.0, 0.125, 4.0)]
    counts = dict(full_static_generators=len(full),
                  static_rhs_including_NESS=sum(len(c['tasks']) for c in full),
                  frequency_rhs=len(freq), nonzero_frequency_shifts=sum(c['nonzero_shift'] for c in freq),
                  correlation_inputs=len(corr), small_main=len(small), small_peer=len(peer))
    counts['large_static_plus_frequency_rhs'] = counts['static_rhs_including_NESS'] + len(freq)
    assert counts == dict(full_static_generators=44, static_rhs_including_NESS=74,
                          frequency_rhs=20, nonzero_frequency_shifts=18,
                          correlation_inputs=18, small_main=72, small_peer=10,
                          large_static_plus_frequency_rhs=94)
    assert all(c['base_id'] in {x['id'] for x in full} for c in freq+corr)
    payload = dict(version='E002e-CONCEPT-v002', status='PROPOSED_NOT_RUN',
                   source_commit='1f12d2f56145a30d2066f4b9f53592ebdc8a96e9',
                   comparison_report='071e15ebc37227b1549e660121bc735a1d86cb13',
                   science_evolution_steps_executed=0, counts=counts,
                   full_static=full, frequency=freq, correlations=corr,
                   small_main=small, small_peer=peer,
                   conditions=dict(frozen_m6_v0='Select invariant n1=0 sector from declared empty initial state; test other invariants and nullity',
                       full_F2='Hermitian m6-local hopping12 deformation in all N; all dissipators retained; rebuild currents',
                       main_small_noise='Three sqrt(phi)*Z_i, phi=0.05; source=sink=0.5',
                       future_budget='Calibration, refinement, tail extensions, adaptive frequencies, modes and retries are NOT costed by these counts',
                       no_new_physical_results=True))
    (OUT/'case_inventory.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
