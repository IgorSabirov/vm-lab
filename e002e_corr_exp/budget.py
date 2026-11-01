"""Cost accounting for both publications and both core verifications."""
import numpy as np
from .plan import PROTOCOL, workload


def forecast_components(phases, timing, actual_counts, calibration_horizon):
    scale = PROTOCOL['horizon']/calibration_horizon
    io_scale = workload(PROTOCOL['horizon'])['checkpoint_writes']/actual_counts['checkpoint_writes']
    publications = timing['summary_publications_seconds']
    verifications = timing['core_verifications_seconds']
    if len(publications)!=2 or len(verifications)!=2:
        raise ValueError('Exactly two measured publications/verifications required')
    if (not np.isfinite(publications+verifications+[timing['first_report_export_seconds']]).all()
            or min(publications+verifications+[timing['first_report_export_seconds']])<0
            or timing['first_report_export_seconds']<publications[0]):
        raise ValueError('Invalid measured report timings')
    result = dict(setup_and_solvers=sum(p['assembly']+p['baseline'] for p in phases),
        propagation_compute=scale*sum(max(0.,p['propagation']-p['checkpoint_io_seconds']) for p in phases),
        checkpoint_io=io_scale*sum(p['checkpoint_io_seconds'] for p in phases),
        case_export_and_diagnostics=scale*sum(max(0.,p['total']-p['assembly']-p['baseline']-p['propagation']) for p in phases),
        report_non_summary_export=scale*(timing['first_report_export_seconds']-publications[0]),
        first_summary_publication=scale*publications[0], second_summary_publication=scale*publications[1],
        first_verification=scale*verifications[0],second_verification=scale*verifications[1],
        preparation_reserve=8., metadata_finalization_reserve=max(.1,sum(publications)))
    if not np.isfinite(list(result.values())).all() or min(result.values())<0:
        raise ValueError('Invalid forecast components')
    return result
