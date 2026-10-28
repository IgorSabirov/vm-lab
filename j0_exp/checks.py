"""Operator-level null controls, independent of the chosen initial state."""
from sqrt_exp.model import maxabs


def operator_checks(model, p, tolerance):
    row = lambda name: model['rows'][model['index'][name]]
    errors = {}
    if p['J'] == 0:
        for suffix in ['01', '12', '02', '_sink']:
            errors['J0_hop'+suffix] = maxabs(row('I_hop'+suffix))
    if p['gate_form'] == 'Q':
        errors['Q_form_transport'] = maxabs(row('I_form_sink'))
    if p['gate_idle'] in ['Q', 'S']:
        errors['diagonal_idle_transport'] = maxabs(row('I_idle_sink'))
    if p['J'] == 0 and p['gate_form'] == 'Q' and p['gate_idle'] in ['Q', 'S']:
        errors['analytic_sink_decay'] = maxabs(row('n2') @ model['L'] + p['kappa_out']*row('n2'))
    if max(errors.values(), default=0) > tolerance:
        raise ValueError('Null-control operator identity failed: '+str(errors))
    return errors
