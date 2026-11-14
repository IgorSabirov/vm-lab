"""One explicitly requested, bounded GitHub-hosted P2 run; no automatic retry."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
import traceback
import fullnet_orchestrator as o


def estimate(probe, request):
    """Engineering work-count analogy, NOT a precision-error scaling law."""
    strict = request['local_evidence']['P1_strict_nfev']
    terms = {e['era']: e['solver_seconds'] * strict[e['era']] / e['nfev']
             for e in probe['timing']['eras']}
    # Same machine initialization; 10 s per run for exports/strict grid overhead.
    central = 2 * (sum(terms.values()) + probe['timing']['initialization_seconds'] + 10)
    return {'low': 0.5 * central, 'central': central, 'high': 1.75 * central,
            'era_seconds_per_run': terms, 'export_allowance_seconds_per_run': 10,
            'uncertainty_factors': [0.5, 1.75],
            'method': 'Target P2 probe per-era solver time multiplied by strict P1 nfev / probe P2 nfev; two full runs. Envelope is engineering judgment, not a confidence interval.',
            'limitations': 'Full-network adaptive step count and strict Jacobian cost are unknown. P1 work counts are an analogy, not guaranteed P2 work. Hard caps bound overruns; no precision reduction or automatic retry.'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--upstream', required=True)
    args = ap.parse_args()
    req = o.read_json(o.PACKAGE / 'RUN_REQUEST.json')
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'IgorSabirov/vm-lab':
        raise RuntimeError('This request is for the named GitHub-hosted VM only')
    if os.environ.get('GITHUB_REF') != 'refs/heads/s0-fullnet':
        raise RuntimeError('Wrong branch')
    if req['id'] != 'P2_GHA_20261114_r1' or req['no_automatic_retry'] is not True:
        raise RuntimeError('Wrong run request')
    if os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise RuntimeError('Automatic/manual workflow retry forbidden: use a reviewed new request')
    if req['package_wall_cap_seconds'] != 3000 or req['process_wall_cap_seconds'] != 1400:
        raise RuntimeError('Request exceeds reviewed envelope')
    if req['main_precision'] != 1e-10 or req['main_nuclear_grid_npts'] != 4000:
        raise RuntimeError('Production profile mismatch')
    source = o.check_branch()
    if source != os.environ['GITHUB_SHA']:
        raise RuntimeError('Checkout differs from triggering source SHA')
    o.git('merge-base', '--is-ancestor', req['source_ancestor'], source)
    root = o.PACKAGE / 'results' / req['id']
    if root.exists():
        raise RuntimeError('Request already has evidence; refusing duplicate calculation')
    status = 1
    try:
        o.prepare(SimpleNamespace(upstream=args.upstream, run_root=str(root)))
        o.append_ledger(root, {'utc':o.now(),'stage':'CARRIED_PRIOR_LOCAL_P2','run_id':'LOCAL_PROBES','exit_code':1,
            'wall_seconds':req['prior_P2_local_wall_seconds'],'source':'../P2_FULLNET_v2/PROBE_RECOVERY.json',
            'reason':'Prior P2 attempts remain charged to the package after executor transfer'})
        o.write_json(root/'EXECUTOR.json', {
            'executor': 'GITHUB_ACTIONS_VM', 'request_sha256': o.digest(o.PACKAGE/'RUN_REQUEST.json'),
            'request': req, 'run_url': 'https://github.com/IgorSabirov/vm-lab/actions/runs/'+os.environ['GITHUB_RUN_ID'],
            'trigger_source': source, 'runner_os':os.environ.get('RUNNER_OS'),
            'runner_arch':os.environ.get('RUNNER_ARCH'), 'scientific_acceptance':False})
        if o.probe(SimpleNamespace(upstream=args.upstream, run_root=str(root))) != 0:
            raise RuntimeError('Target-machine probe failed; main not admitted')
        result = o.read_json(root/'runs/PROBE/RESULT.json')
        if result['status'] != 'ENGINEERING_PASS':
            raise RuntimeError('Target-machine probe numerical checks failed')
        predicted = estimate(result, req)
        o.write_json(root/'FORECAST_BASIS.json', predicted)
        basis = json.dumps(predicted, ensure_ascii=False)
        o.forecast(SimpleNamespace(run_root=str(root), low=predicted['low'],
            central=predicted['central'], high=predicted['high'], basis=basis,
            auto_approve=False, publish=False))
        o.finalize_artifacts(root)
        o.publish(root)
        # Admission and its provenance reach GitHub before any strict integration.
        if predicted['high'] + o.spent_seconds(root) > req['package_wall_cap_seconds']:
            raise RuntimeError('Target-machine forecast exceeds reviewed total cap; main not started')
        if predicted['high']/2 > req['process_wall_cap_seconds']:
            raise RuntimeError('Per-run forecast exceeds reviewed process cap; main not started')
        o.create_approval(root, o.digest(root/'FORECAST.json'),
            'USER_AUTHORIZATION_20261114: '+req['user_authorization'], req['package_wall_cap_seconds'])
        o.finalize_artifacts(root)
        o.publish(root)
        o.execute_main(root, args.upstream)
        status = 0
    except Exception as exc:
        if root.exists():
            o.write_json(root/'EXECUTION_ERROR.json', {'utc':o.now(), 'error_type':type(exc).__name__,
                'error':str(exc), 'traceback':traceback.format_exc(), 'scientific_acceptance':False,
                'automatic_retry':False, 'physics_failure_inference':'NOT_MADE'})
        traceback.print_exc()
    finally:
        if root.exists():
            o.finalize_artifacts(root)
            o.publish(root)
    return status

if __name__ == '__main__':
    raise SystemExit(main())
