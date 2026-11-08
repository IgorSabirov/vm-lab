"""Explicit denominators and unresolved promises for R127, without promotion."""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
import json
from .observables import distribution


def report(rows, contrasts):
    grouped = defaultdict(list)
    for row in rows:
        if row['case_id'].startswith('patch::'):
            grouped[row['case_id']].append(row)
    result = {}
    for name, group in sorted(grouped.items()):
        weighted = distribution(group)
        n = len(weighted[0][1]['profile'])
        task_mass = sum(w*t['success']/n for w, r in weighted for t in r['task_results'])
        reserve_mass = sum(w*bool(t.get('full_reserve'))/n for w, r in weighted for t in r['task_results'])
        reserve_joint = sum(w*bool(t.get('full_reserve'))*t['success']/n for w, r in weighted for t in r['task_results'])
        result[name] = dict(p_task_success=task_mass, p_full_fixed_reserve=reserve_mass,
                            p_task_given_full_reserve=None if reserve_mass == 0 else reserve_joint/reserve_mass,
                            conditional_denominator=reserve_mass,
                            primary_denominator='all prepared carriers times normalized input probability',
                            conditioning_status='zero_conditioning_mass' if reserve_mass == 0 else 'defined',
                            input_mass=sum(w for w, _ in weighted),
                            expected_credits=sum(w*r['total_spent_fuel'] for w, r in weighted),
                            expected_blocked_routes=sum(w*r.get('geometry', {}).get('blocked', 0) for w, r in weighted),
                            finite_resources_balanced=all(r['material_and_credit_balance'] == r['initial_totals'] for _, r in weighted))
    bank = json.loads((Path(__file__).resolve().parents[1]/'preregistration/PREPARED_GEOMETRIES.json').read_text())
    ensemble_returns = {}
    for name, ensemble in bank['ensembles'].items():
        expected = ensemble['expected_cases']
        missing = sorted(set(expected)-set(result))
        by_template = defaultdict(list)
        for case, weight in expected.items():
            if case in result:
                by_template[case.rsplit('::', 1)[1]].append((Fraction(weight), result[case]['p_task_success']))
        ensemble_returns[name] = dict(status='NOT_EVALUABLE_MISSING_CASES' if missing else 'EXECUTED_CONDITIONAL_MEASURE',
            missing_cases=missing, measure=ensemble['measure'], input_sha256=ensemble['input_sha256'],
            estimates={} if missing else {t: sum(float(w)*y for w,y in values) for t, values in by_template.items()},
            geometry_weight_mass={t:str(sum(w for w,y in values)) for t,values in by_template.items()},
            uncertainty='No population confidence interval: stationarity and independent geometry sampling not established here')
    return dict(ensembles=ensemble_returns, experiment_id='NOW_INTEGRATED_CONTINUATION_V1', registry='R127', cases=result,
                contrasts={k:v for k,v in contrasts.items() if k.startswith('patch::')},
                measure='conditional finite fixtures; no pooling into an equilibrium ensemble',
                C3_D='NOT_IMPLEMENTED', physical_reverse='NOT_IMPLEMENTED',
                Ising_j_star='NOT_ESTIMATED', spontaneous_metric='NOT_ESTABLISHED',
                scientific_status='NO_PROMOTION_FROM_TECHNICAL_RUN')
