#!/usr/bin/env python3
"""Phase 0-2 finite audit; calibration precedes main. Standard library only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import random
import resource
import time

import ring_engine as ring
import graph_engine as graph

HERE = Path(__file__).resolve().parent
FROZEN = ['SPEC.json', 'PLAN.json', 'ring_engine.py', 'graph_engine.py', 'run_block1.py']


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')


def hashes():
    return {p: hashlib.sha256((HERE/p).read_bytes()).hexdigest() for p in FROZEN}


def counts(snap):
    return [sum(s & 1 for n, s in snap['states']), sum((s >> 1) & 1 for n, s in snap['states'])]


def tau(snap):
    """Third oracle: move bits directly over old edges, with no Q or name algebra."""
    states = dict(snap['states'])
    out = {n: 0 for n in states}
    for u, v in snap['edges_b_to_a']:
        out[u] |= states[v] & 1
        out[v] |= states[u] & 2
    return {'states': sorted(map(list, out.items())), 'edges_b_to_a': snap['edges_b_to_a']}


def ops(engine, x, version):
    q = engine.q(x, version)
    qi = engine.q(x, version, True)
    inter = engine.interact(x)
    f = engine.q(inter, version)
    fi = engine.interact(qi)
    return {'Q': q, 'Qi': qi, 'I': inter, 'F': f, 'Fi': fi,
            'QQ': engine.q(q, version),
            'QiQ': engine.q(q, version, True), 'QQi': engine.q(qi, version),
            'II': engine.interact(inter),
            'TQT': engine.flip(engine.q(engine.flip(x), version)),
            'FiF': engine.backward(f, version), 'FFi': engine.forward(fi, version)}


class Audit:
    def __init__(self):
        self.cases = Counter()
        self.metrics = {v: {} for v in ['A', 'P_ring']}
        self.witnesses = {}
        self.digest = hashlib.sha256()
        self.total_vertices = 0

    def check(self, version, name, ok, meta, source, observed=None, expected=None):
        row = self.metrics[version].setdefault(name, {'checked': 0, 'failed': 0})
        row['checked'] += 1
        if not ok:
            row['failed'] += 1
            key = version+':'+name
            if key not in self.witnesses:
                self.witnesses[key] = {'case': meta, 'input': source,
                                       'observed': observed, 'expected': expected,
                                       'minimality': 'first by declared enumeration within this group; not global term-size minimization'}

    def case(self, x, g, meta):
        original = ring.snapshot(x)
        assert original == graph.snapshot(g), 'harness input conversion differs'
        self.cases[meta['group']] += 1
        self.total_vertices += len(x)
        self.digest.update(json.dumps([meta, original], sort_keys=True).encode()+b'\n')
        expected_tau = tau(original)
        for version in self.metrics:
            rs, gs = ops(ring, x, version), ops(graph, g, version)
            result = {}
            for op in rs:
                a, b = ring.snapshot(rs[op]), graph.snapshot(gs[op])
                result[op] = a
                self.check(version, 'DIFF_'+op, a == b, meta, original, a, b)
                for key, engine, value in [('ring', ring, rs[op]), ('graph', graph, gs[op])]:
                    try:
                        engine.validate(value)
                        valid = True
                    except ValueError:
                        valid = False
                    self.check(version, 'G1_'+key+'_'+op, valid, meta, original)
                self.check(version, 'PARTICLES_'+op, counts(a) == counts(original), meta, original)
            for name, lhs, rhs in [
                ('G3_Q2_tau', result['QQ'], expected_tau),
                ('G3_QiQ_id', result['QiQ'], original),
                ('G3_QQi_id', result['QQi'], original),
                ('G3_TQT_Qi', result['TQT'], result['Qi']),
                ('G4_I2_id', result['II'], original),
                ('FULL_FiF_id', result['FiF'], original),
                ('FULL_FFi_id', result['FFi'], original),
            ]:
                self.check(version, name, lhs == rhs, meta, original, lhs, rhs)
            self.check(version, 'G2_vertex_count', len(result['Q']['states']) == len(x), meta, original)
            # G2 tracks each edge's two bit sources, separately from whole-graph equality.
            correct = True
            qstates = dict(result['Q']['states'])
            for i, (u, s) in enumerate(x):
                v, t = x[(i+1) % len(x)]
                name = ring.label(ring.join(ring.r(u), ring.l(v)))
                bits = (t & 1) | (s & 2) if version == 'A' else (s & 1) | (t & 2)
                correct &= qstates.get(name) == bits
            self.check(version, 'G2_names_and_bit_sources', correct, meta, original)
            reversed_storage = graph.Graph(dict(reversed(list(g.states.items()))), tuple(reversed(g.edges)))
            rotated = x[1:]+x[:1]
            self.check(version, 'G4_graph_order_independent', graph.snapshot(graph.interact(reversed_storage)) == result['I'], meta, original)
            self.check(version, 'G4_ring_start_independent', ring.snapshot(ring.interact(rotated)) == result['I'], meta, original)
            split = sum(s == 3 for n, s in x)
            merger = sum(x[i][1] == 1 and x[(i+1) % len(x)][1] == 2 for i in range(len(x)))
            self.check(version, 'G4_size_balance', len(result['I']['states'])-len(x) == split-merger, meta, original)

    def result(self):
        unexpected = {v: {k: x for k, x in rows.items() if x['failed'] and not
                         (v == 'P_ring' and k in {'G3_Q2_tau', 'G3_TQT_Qi'})}
                      for v, rows in self.metrics.items()}
        return {'case_counts': dict(self.cases), 'total_case_inputs': sum(self.cases.values()),
                'total_input_vertices': self.total_vertices,
                'corpus_sha256': self.digest.hexdigest(), 'metrics': self.metrics,
                'unexpected_failures': unexpected,
                'status': 'FINITE_BLOCK_PASS_WITH_PRINTED_CONTROL_FAILURES' if not any(unexpected.values()) else 'BLOCK_FAILURE'}


def reject_fixtures():
    cases = [graph.Graph({}, ()), graph.Graph({'u0':0,'u1':0}, (('u0','u0'),('u1','u1'))),
             graph.Graph({'u0':0,'Lu0':0}, (('u0','Lu0'),('Lu0','u0'))),
             graph.Graph({'(u0,u0)':0}, (('(u0,u0)','(u0,u0)'),)),
             graph.Graph({'(Lu0,Ru0)':0}, (('(Lu0,Ru0)','(Lu0,Ru0)'),)),
             graph.Graph({'u0':0,'u1':0}, (('u0','u1'),('u0','u0')))]
    for g in cases:
        try:
            graph.validate(g)
        except ValueError:
            continue
        raise AssertionError('graph invalid fixture accepted')
    u=ring.atom(0)
    for x in [(), ((u,0),(ring.l(u),0)), ((('join',u,u),0),), ((('join',ring.l(u),ring.r(u)),0),)]:
        try:
            ring.validate(x)
        except ValueError:
            continue
        raise AssertionError('ring invalid fixture accepted')
    return {'graph_rejected': len(cases), 'ring_rejected': 4}


def calibration_cases():
    # Same operations as main, spread uniformly over four alphabet values/lengths.
    for n in range(3, 7):
        for k in range(32):
            rng = random.Random(170000+n*100+k)
            w = tuple(rng.randrange(4) for _ in range(n))
            yield w, {'group':'calibration', 'L':n, 'index':k}


def main_cases(plan):
    for group, lengths in [('simple_exhaustive',range(3,7)), ('small_port_cycles',range(1,3))]:
        for n in lengths:
            for index, w in enumerate(itertools.product(range(4), repeat=n)):
                yield ring.make(w), graph.make(w), {'group':group,'L':n,'index':index,'word':w}
    rng = random.Random(plan['corpus']['seed'])
    for case in range(plan['corpus']['random_initials']):
        n = rng.randrange(7,25)
        w = tuple(rng.randrange(4) for _ in range(n))
        x, g = ring.make(w), graph.make(w)
        for step in range(plan['corpus']['random_reached_states_per_initial']):
            yield x, g, {'group':'seeded_reachable','index':case,'initial_L':n,'step':step}
            x, g = ring.forward(x), graph.forward(g)
    for case, w in enumerate(plan['corpus']['adversarial_words']):
        x, g = ring.make(w), graph.make(w)
        for step in range(plan['corpus']['adversarial_reached_states_per_initial']):
            yield x, g, {'group':'adversarial_reachable','index':case,'initial_word':w,'step':step}
            x, g = ring.forward(x), graph.forward(g)


def environment():
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'machine': platform.machine(), 'cpu_logical': os.cpu_count(),
            'cpu_model': next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),None),
            'meminfo': Path('/proc/meminfo').read_text().splitlines()[:3],
            'execution_location': 'assistant_local_environment', 'dependencies':'Python standard library'}


def raw_diagnostics():
    rows = []
    for n in (1,2,3):
        a = ring.printed_shape(ring.make((0,)*n))
        b = graph.printed_shape(graph.make((0,)*n))
        assert a == b
        missing = sorted(set(v for edge in a['edges_b_to_a'] for v in edge)-set(a['vertices']))
        rows.append({'L':n,'shape':a,'dangling_endpoint_names':missing,
                     'vertex_count':len(a['vertices']), 'edge_count':len(a['edges_b_to_a']),
                     'status':'SPEC_NOT_CLOSED' if missing else 'BIT_CLAUSE_UNBOUND'})
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--calibrate',action='store_true')
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    assert args.calibrate != args.run
    plan=json.loads((HERE/'PLAN.json').read_text())
    frozen=hashes()
    started=time.perf_counter()
    audit=Audit()
    rejection=reject_fixtures()
    raw=raw_diagnostics()
    if args.calibrate:
        for w,meta in calibration_cases():
            audit.case(ring.make(w),graph.make(w),meta)
    else:
        forecast=json.loads((HERE/'PREFLIGHT.json').read_text())
        assert forecast['source_sha256']==frozen, 'source changed after calibration'
        for x,g,meta in main_cases(plan):
            audit.case(x,g,meta)
    elapsed=time.perf_counter()-started
    result=audit.result()
    result.update({'scope':'finite C1 phase 0-2; no asymptotic or entropy replication',
                   'measured_at_utc':datetime.now(timezone.utc).isoformat(),
                   'elapsed_seconds':elapsed,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   'environment':environment(),'source_sha256':frozen,
                   'negative_validation_controls':rejection,'P_raw':raw})
    if args.calibrate:
        dump(HERE/'CALIBRATION.json',result)
        n=plan['corpus']['total_case_inputs']
        # Longer reached terms and prefix validation cost more than atomic rings.
        scale=n/result['total_case_inputs']
        central=elapsed*scale*2.0
        forecast={'made_before_main_utc':datetime.now(timezone.utc).isoformat(),
                  'source_sha256':frozen,'calibration_seconds':elapsed,
                  'calibration_inputs':result['total_case_inputs'],'planned_main_inputs':n,
                  'method':'same checks; case-count scaling x2 for larger rings/reached terms; interval x0.5..3 of central',
                  'forecast_seconds':central,'range_seconds':[central*.5,central*3],
                  'hard_time_limit':None,'execution_location':'assistant_local_environment',
                  'owner_instruction':plan['owner_instruction'],
                  'main_allowed_by_checks':result['status']=='FINITE_BLOCK_PASS_WITH_PRINTED_CONTROL_FAILURES'}
        dump(HERE/'PREFLIGHT.json',forecast)
        print(json.dumps({'calibration_status':result['status'],'seconds':elapsed,'forecast':forecast},ensure_ascii=False,indent=2))
    else:
        assert sum(audit.cases.values())==plan['corpus']['total_case_inputs']
        result['runtime_plan_actual']={'forecast_seconds':forecast['forecast_seconds'],
             'range_seconds':forecast['range_seconds'],'actual_seconds':elapsed,
             'ratio':elapsed/forecast['forecast_seconds'],
             'in_range':forecast['range_seconds'][0]<=elapsed<=forecast['range_seconds'][1],
             'range_is_not_stop_condition':True}
        dump(HERE/'RESULTS.json',result)
        demo=ring.make((1,0,2))
        dump(HERE/'WITNESSES.json',{'counterexamples':audit.witnesses,
             'author_example':{'input':ring.snapshot(demo),'Q_A':ring.snapshot(ring.q(demo)),
                'Q_A_squared':ring.snapshot(ring.q(ring.q(demo))),'direct_tau':tau(ring.snapshot(demo))},
             'P_raw':raw})
        print(json.dumps({'status':result['status'],'cases':result['case_counts'],'seconds':elapsed,
             'peak_rss_kib':result['peak_rss_kib'],'runtime':result['runtime_plan_actual'],
             'failures':{v:{k:x['failed'] for k,x in rows.items() if x['failed']} for v,rows in audit.metrics.items()}},indent=2))
    if result['status']=='BLOCK_FAILURE':
        raise SystemExit(1)


if __name__=='__main__':
    main()
