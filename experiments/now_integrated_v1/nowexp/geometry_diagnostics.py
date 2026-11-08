"""Optional use of the already adopted Serbian C++ signature kernel."""
import hashlib
import importlib.util
from itertools import combinations
from pathlib import Path


def diagnose(snapshot, library=None):
    carrier = snapshot.get('carrier')
    result = dict(status='NOT_REQUESTED' if library is None else 'PENDING',
                  physical_reverse='NOT_IMPLEMENTED',
                  arrow_claim=False, metric_origin='preparation, not derived')
    if library is None:
        return result
    import numpy as np
    repo = Path(__file__).resolve().parents[3]
    path = repo/'tools/piecewise_flat_qg/signature_kernel.py'
    spec = importlib.util.spec_from_file_location('now_signature_kernel', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kernel = module.SignatureKernel(library)
    result['library_sha256'] = hashlib.sha256(Path(library).read_bytes()).hexdigest()
    matrices = []
    if carrier and carrier['spec'].get('family') == 'cdt_strip':
        # Declared local CDT triangle: one spacelike and two timelike edges.
        q = np.array([[0., 1., -1.], [1., 0., -1.], [-1., -1., 0.]])
        matrices.append((q[0, 1:, None]+q[0, None, 1:]-q[1:, 1:])/2)
        result['metric_origin'] = 'given CDT triangle lengths: spacelike +1, timelike -1'
    else:
        if carrier:
            if carrier['spec']['kind'] != 'prepared_order':
                return dict(result, status='NOT_EVALUABLE_NO_METRIC')
            events = {e['id']: e for e in carrier['spec']['events']}
            points = [events[t['event']].get('coordinates') for t in carrier['trace'] if 'event' in t]
            points = [p for p in points if p is not None]
        else:
            points = [[item['event']['t'], snapshot['lines'][item['event']['owner']]['x0']+
                       snapshot['lines'][item['event']['owner']]['v']*item['event']['t']]
                      for item in snapshot['log'] if item['kind'] == 'event']
        unique = list(dict.fromkeys(map(tuple, points)))[:16]
        for tri in combinations(unique, 3):
            p = np.array(tri)
            d = p[1:]-p[0]
            matrices.append(d @ np.diag([-1., 1.]) @ d.T)
            if len(matrices) == 64:
                break
    if not matrices:
        return dict(result, status='NOT_EVALUABLE_NO_METRIC')
    r = kernel.classify(np.array(matrices), strict=False)
    result.update(status='EXECUTED_DIAGNOSTIC', matrices=len(matrices),
                  counts=r['counts'].tolist(), reliable=r['reliable'].tolist(),
                  interpretation='Signature of supplied metric only; no spontaneous Lorentzian geometry or physical reverse inferred')
    return result
