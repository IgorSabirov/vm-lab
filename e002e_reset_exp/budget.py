"""Measured costs; low-rank inverse work is explicitly inside setup/solve costs."""
from .plan import protocol_hash,implementation_hash


def forecast(config,metrics,records,before):
    main=[r for rec in records for r in rec['rows'] if r['method']!='gmres_ilu_tight']
    components=dict(
        assemblies_and_operator_certificates=sum(p['assembly_seconds']+p['certificate_seconds'] for p in metrics['phases']),
        factors_and_low_rank_columns=sum(r['solver']['timing']['factor_seconds']+r['solver']['timing']['low_rank_setup_seconds'] for r in main),
        scientific_solves_proxy=2*sum(r['solver']['timing']['solve_seconds'] for r in main),
        condition_estimates=sum(r['solver']['timing']['condition_seconds'] for r in main),
        density_diagnostics=3*sum(r.get('diagnostic_seconds',0.) for r in main),
        report_verification=3*metrics['verification_seconds'],
        measured_preflight=metrics['preflight_seconds'],
        vector_and_metadata_io=2*metrics['io_seconds'],
        startup_proxy=.25055742263793945)
    expected=sum(components.values());memory=dict(config['memory_budget']);after=metrics['environment_after']
    memory.update(measured_peak_rss_bytes=after['process_peak_rss_bytes'],measured_peak_vm_bytes=after['process_peak_vm_bytes'],
        simultaneous_factor_storage_bytes=max(r['solver']['factor_storage_bytes']+r['solver']['low_rank_dense_bytes'] for r in main))
    memory['calibration_configured_peak_additional_bytes']=config['memory_budget']['peak_additional_bytes']
    memory['peak_additional_bytes']=int(1.25*memory['measured_peak_vm_bytes'])
    memory['forecast_rule']='1.25 times measured VmPeak; full process peak is conservative additional-allocation proxy; reserve separate'
    memory['memory_high_water_source']='/proc/self/status VmHWM and VmPeak'
    memory['address_space_headroom_at_peak_bytes']=after['address_space_rlimit'][0]-memory['measured_peak_vm_bytes']
    return dict(status='CALIBRATION_COMPLETE_REVIEW_PENDING',counts=metrics['counts'],report_commit=None,
        implementation_sha256=implementation_hash(),protocol_sha256=protocol_hash(),environment=before,memory_budget=memory,
        forecast_components_seconds=components,
        production_forecast=dict(expected_seconds=expected,lower_seconds=.5*expected,upper_seconds=2*expected,
            basis='12 measured factor/low-rank setups; 2x random+known solve proxy; 3x known density diagnostics and independent vector verification; measured preflight and 2x vector/metadata I-O; .250557s prior VM process startup proxy. Review enclosing time before accepting forecast. Extra calibration sweep excluded.'),
        limits=['No physical finite-gamma RHS was solved in calibration.','Random RHS timing is a proxy, not a guarantee.',
                'Factor-application timing overlaps setup/solve/condition and is not added again.',
                'Enclosing process time and memory must be reviewed from GitHub before production.'])
