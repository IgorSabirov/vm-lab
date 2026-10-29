"""Fixed calibration and acceptance. No damage outcomes enter selection."""
import math

EDGES = ('01', '12', '02')


def derive_rates(target, parameters):
    rates = {}
    c = parameters['delta'] + parameters['gamma_bg']
    for e in EDGES:
        x = target['edges'][e]
        l, r, loss = x['pL'], x['pR'], x['loss']
        if not all(math.isfinite(v) for v in (l, r, loss)) or min(l,r,loss)<=0:
            raise ValueError('Invalid calibration target: '+e)
        alpha, beta = loss/r, loss/l-c
        if beta < 0:
            raise ValueError('No nonnegative analytic RR control: '+e)
        if abs(r-(1-(1+parameters['delta']/parameters['eta'])*l)) > 1e-8:
            raise ValueError('Historical target is not resource-balanced: '+e)
        rates[e] = [alpha, beta]
    return rates


def scaled_rates(rates, parameters, factor):
    """Not used by v001 runs: population-preserving sensitivity formula."""
    if not math.isfinite(factor) or factor<=0:
        raise ValueError('Invalid sensitivity factor')
    c=parameters['delta']+parameters['gamma_bg']
    result={e:[factor*a, factor*(b+c)-c] for e,(a,b) in rates.items()}
    if any(b<0 for a,b in result.values()):
        raise ValueError('Sensitivity factor produces a negative rate')
    return result


def loss(ref, edge):
    return sum(ref['event_rate__'+k+'_'+edge] for k in ('break','background','idle'))


def match(candidate, control, limits, numerical_valid):
    def relative(x,y):
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError('Nonfinite matching value')
        return abs(x-y)/max(abs(y),limits['relative_denominator_floor'])
    errors={}
    for e in EDGES:
        errors['pL_'+e]=relative(control['pL'+e],candidate['pL'+e])
        errors['loss_'+e]=relative(loss(control,e),loss(candidate,e))
        errors['renew_'+e]=relative(control['event_rate__renew_'+e],loss(candidate,e))
    hop=relative(control['I_hop_sink'],candidate['I_hop_sink'])
    structure=max(v for k,v in errors.items() if k.startswith('pL_'))<=limits['population_relative']
    losses=max(v for k,v in errors.items() if k.startswith('loss_'))<=limits['loss_relative']
    renew=max(v for k,v in errors.items() if k.startswith('renew_'))<=limits['renew_relative']
    weak=min(candidate['I_hop_sink'],control['I_hop_sink'])<=limits['weak_hop_floor']
    if not numerical_valid or weak:
        state,grade='matching_numerical_failure','ineligible'
    elif not (structure and losses and renew):
        state,grade='no_matched_control','ineligible'
    elif hop>limits['hop_max_relative']:
        state,grade='structural_matched_hop_mismatch','ineligible'
    else:
        state='matched_control_found'
        grade='preferred_le_5pct' if hop<=limits['hop_preferred_relative'] else 'limited_gt5_le10pct'
    return dict(state=state,grade=grade,relative_errors=errors,
        hop_relative_error=hop,hop_signed_relative=(control['I_hop_sink']/candidate['I_hop_sink']-1) if not weak else None,
        candidate_hop=candidate['I_hop_sink'],control_hop=control['I_hop_sink'],
        damage_eligible=state=='matched_control_found',weak_hop=weak,
        selection='one analytic control per candidate; no optimizer or damage-based selection')
