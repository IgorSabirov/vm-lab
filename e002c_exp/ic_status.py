"""Pure IC status transition table; no numerical engine or I/O imports."""
import math

def decide_ic_status(fit, validation, transport=None):
    def state(structural,transport_status):
        return dict(ic_structural_status=structural,ic_transport_status=transport_status)
    if fit is None:
        if validation is not None or transport is not None:raise ValueError('IC outcome without a fit')
        return state('not_run','not_evaluated')
    if fit.get('selected') is None:
        if validation is not None or transport is not None:raise ValueError('IC outcome without a selected candidate')
        return state('no_match_found_within_declared_search','not_evaluated')
    if validation is None:
        if transport is not None:raise ValueError('Transport before validation')
        return state('structural_candidate_found_validation_pending','not_evaluated')
    if type(validation.get('structural_pass')) is not bool:raise ValueError('Missing structural decision')
    if not validation['structural_pass']:
        if transport is not None:raise ValueError('Transport after rejected validation')
        return state('structural_candidate_rejected_by_validation','not_evaluated')
    if transport is None:return state('structural_PASS','transport_pending')
    if type(transport.get('evaluable')) is not bool:raise ValueError('Missing transport evaluability')
    if not transport['evaluable']:return state('structural_PASS','transport_not_evaluable')
    error=transport.get('relative_error')
    if not isinstance(error,(float,int)) or not math.isfinite(error) or error<0:
        raise ValueError('Invalid transport error')
    return state('structural_PASS','transport_close_5pct' if error<=.05 else
                 ('transport_close_10pct' if error<=.10 else 'structural_matched_hop_mismatch'))
