"""Declared comparison policy, independent of integration and I/O."""
import math

POLICY='same_horizon_stationary_or_fixed_window_200_v1'

def comparison_gate(summaries, numerical_screen_pass, kind='stationary'):
    if kind not in ('stationary','transition_200'):raise ValueError('Unknown comparison kind')
    reasons=[];horizons=[float(s['horizon']) for s in summaries]
    if any(s.get('failed') is not None for s in summaries):reasons.append('failed_case')
    if kind=='stationary':
        if not horizons or max(horizons)-min(horizons)>1e-9:reasons.append('different_horizons')
        if any(not s['stationarity']['pass_gate'] for s in summaries):reasons.append('not_stationary')
        refs=[s.get('reference') for s in summaries]
    else:
        if any(h<200-1e-9 for h in horizons):reasons.append('common_window_not_reached')
        refs=[s.get('transition_reference') for s in summaries]
    if any(r is None or any(not math.isfinite(v) for v in r.values()) for r in refs):reasons.append('invalid_reference')
    refinements=[s.get('refinement_status','not_refined') for s in summaries]
    if any(x=='failed' for x in refinements):reasons.append('refinement_failed')
    if any(x not in ('passed','failed','not_refined') for x in refinements):reasons.append('unknown_refinement')
    refined=bool(summaries) and all(x=='passed' for x in refinements)
    if not refined and not numerical_screen_pass:reasons.append('numerical_screen_unverified')
    return dict(policy=POLICY,kind=kind,comparable=not reasons,reasons=reasons,
                case_ids=[s['case']['id'] for s in summaries],horizons=horizons,
                window=[190.,200.] if kind=='transition_200' else ([horizons[0]-10,horizons[0]] if horizons and not reasons else None),
                evidence_level='REFINEMENT_CHECKED' if refined else 'SCREENING_ONLY')

def response_status(comparison,resolved,positive='flux_response',negative='no_resolved_response'):
    if not comparison['comparable']:return 'not_comparable'
    if comparison['kind']=='transition_200':return 'finite_time_difference' if resolved else 'no_resolved_finite_time_difference'
    if resolved and comparison['evidence_level']=='SCREENING_ONLY':return 'SCREENING_SIGNAL'
    return positive if resolved else negative
