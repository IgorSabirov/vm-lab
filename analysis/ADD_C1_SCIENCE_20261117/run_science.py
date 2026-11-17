#!/usr/bin/env python3
"""C1 scientific continuation. Run --calibrate first, then --run."""
import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
import platform
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'ADD_C1_LOCAL_REPRO_20261117'))
import ring_engine as ring
import graph_engine as graph
import science_engine as fast

PLAN = json.loads((HERE / 'PLAN.json').read_text())


def dump(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def source_hashes():
    paths = [HERE / n for n in ['PLAN.json', 'science_engine.py', 'run_science.py']]
    paths += [HERE.parent/'ADD_C1_LOCAL_REPRO_20261117'/n
              for n in ['ring_engine.py', 'graph_engine.py']]
    return {str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


def word_interact(w):
    # Independent short-word reference, avoiding numpy overhead on tiny rings.
    if w[-1] == 1 and w[0] == 2:
        w = w[-1:] + w[:-1]
    out, i, split, merge = [], 0, 0, 0
    while i < len(w):
        if w[i] == 3:
            out.extend((1, 2)); split += 1
        elif i + 1 < len(w) and w[i] == 1 and w[i+1] == 2:
            out.append(3); merge += 1; i += 1
        else:
            out.append(w[i])
        i += 1
    return tuple(out), split, merge


def word_step(w, inverse=False):
    if inverse:
        x = tuple((s & 1) | (w[(i+1) % len(w)] & 2) for i, s in enumerate(w))
        return word_interact(x)
    x, split, merge = word_interact(w)
    return tuple((x[(i+1) % len(x)] & 1) | (s & 2) for i, s in enumerate(x)), split, merge


def measure(w):
    n = len(w)
    pairs = [i for i in range(n) if w[i] == 1 and w[(i+1) % n] == 2]
    if not pairs:
        return 0, 0
    best = n
    for i in pairs:
        for k in range(1, best+1):
            if w[(i+1+k) % n] & 1 or w[(i-k) % n] & 2:
                best = k; break
    return len(pairs), best


def graph_word(g):
    successor = dict(g.edges)
    start = next(iter(g.states))
    out, u = [], start
    while not out or u != start:
        out.append(g.states[u]); u = successor[u]
    return out


def named_checks(words):
    stats = Counter()
    witness = {}
    start = time.perf_counter()
    for w in words:
        x, g = ring.make(w), graph.make(w)
        for inverse in (False, True):
            xr = ring.backward(x) if inverse else ring.forward(x)
            xg = graph.backward(g) if inverse else graph.forward(g)
            assert ring.snapshot(xr) == graph.snapshot(xg)
            wf, _, _ = fast.step(np.array(w, dtype=np.uint8), inverse)
            wr, _, _ = word_step(w, inverse)
            assert fast.cyclic_equal(wf, [s for _, s in xr])
            assert fast.cyclic_equal(wf, graph_word(xg))
            assert fast.cyclic_equal(wf, wr)
            stats['projected_transitions'] += 1
        # Lemma 1: exact two names, states, and oriented edge in predecessor.
        for version in ('A', 'P_ring'):
            pre = ring.backward(x, version)
            pg = graph.backward(g, version)
            assert ring.snapshot(pre) == graph.snapshot(pg)
            states = dict(pre)
            edges = {(u, pre[(i+1) % len(pre)][0]) for i, (u, _) in enumerate(pre)}
            for i, (u, s) in enumerate(x):
                v, t = x[(i+1) % len(x)]
                if s == 1 and t == 2:
                    ok = states.get(ring.r(u)) == 1 and states.get(ring.l(v)) == 2 and (ring.r(u), ring.l(v)) in edges
                    stats[version + '_lemma_patterns_checked'] += 1
                    if not ok:
                        stats[version + '_lemma_failed'] += 1
                        witness.setdefault(version, {'word': w, 'input': ring.snapshot(x), 'preimage': ring.snapshot(pre),
                                                     'expected_names': [ring.label(ring.r(u)),ring.label(ring.l(v))]})
                    if version == 'A':
                        assert ok
        assert measure(w) == fast.pattern_measure(np.array(w, dtype=np.uint8))
        stats['inputs'] += 1
    return {'counts': dict(stats), 'witnesses': witness, 'seconds': time.perf_counter()-start}


def short_trajectories(words, output=False):
    stats = Counter()
    start = time.perf_counter()
    rows = []
    steps = PLAN['exhaustive_trajectory_steps_each_direction']
    for index, initial in enumerate(words):
        ca = sum(s & 1 for s in initial)
        cb = sum(s >> 1 for s in initial)
        for inverse in (False, True):
            w = initial
            prev = measure(w)
            extinct = 0 if prev[0] == 0 else None
            sizes = [len(w)]
            for t in range(steps):
                nw, split, merge = word_step(w, inverse)
                assert len(nw) - len(w) == split - merge
                if not inverse:
                    nxt = measure(nw)
                    assert nxt[0] <= prev[0]
                    if prev[0]:
                        assert nxt < prev
                        stats['strict_lex_steps'] += 1
                    if extinct is None and nxt[0] == 0:
                        extinct = t+1
                    prev = nxt
                w = nw
                sizes.append(len(w))
            assert (sum(s & 1 for s in w), sum(s >> 1 for s in w)) == (ca, cb)
            stats['trajectories'] += 1
            stats['steps'] += steps
            stats['particle_conservation_checks'] += 1
            if not inverse and ca and cb:
                assert extinct is not None
                stats['merger_extinctions'] += 1
                stats['latest_extinction'] = max(stats['latest_extinction'], extinct)
                for t in range(extinct, steps+1):
                    j = t + sizes[t]
                    if j <= steps:
                        assert 1 <= sizes[j] - sizes[t] <= 2 * ca * cb
                        stats['appendix_b_windows'] += 1
            differences = [b-a for a, b in zip(sizes[:-1], sizes[1:])]
            slope = differences[-1]
            tail = all(d == slope for d in differences[-32:])
            if inverse and ca and cb:
                assert tail and 1 <= slope <= min(ca, cb)
                stats['positive_integer_inverse_tails'] += 1
            if not ca or not cb:
                assert all(n == len(initial) for n in sizes)
                stats['nongrowing_controls'] += 1
            if output:
                rows.append([index, ''.join(map(str,initial)), int(inverse), ca, cb,
                             len(w), extinct, slope, int(tail)])
    if output:
        with gzip.open(HERE/'EXHAUSTIVE.csv.gz', 'wt', newline='') as f:
            writer = csv.writer(f); writer.writerow(['case','word','inverse','na','nb','final_L','forward_extinction','last_dL','tail32_constant']); writer.writerows(rows)
    return {'counts': dict(stats), 'seconds': time.perf_counter()-start}


def initials():
    out = []
    for seed in PLAN['uniform_L100_seeds']:
        rng = np.random.default_rng(seed)
        w = rng.integers(0,4,100,dtype=np.uint8)
        assert all(fast.counts(w))
        out.append((f'uniform_{seed}', w))
    for seed in PLAN['sparse_L100_seeds']:
        rng = np.random.default_rng(seed)
        w = (rng.random(100)<0.1).astype(np.uint8) + 2*(rng.random(100)<0.1).astype(np.uint8)
        assert all(fast.counts(w))
        out.append((f'sparse_{seed}',w))
    fixtures = {
        'merger_L128': [1,2]+[0]*126,
        'approaching_L128': [2]+[0]*63+[1]+[0]*63,
        'full_L16': [3]*16,
        'alternating_L16': [1,2]*8,
        'isolated_double_L128': [3]+[0]*127,
        'empty_L100': [0]*100,
        'a_only_L100': [1]*100,
        'b_only_L100': [2]*100,
    }
    for key in PLAN['adversarial']:
        out.append((key,np.array(fixtures[key],dtype=np.uint8)))
    return out


def long_trace(key, initial, inverse, steps, output):
    w = initial.copy()
    ca, cb = fast.counts(w)
    previous_measure = fast.pattern_measure(w)
    extinct = 0 if previous_measure[0] == 0 else None
    samples, sizes, deltas = [], [len(w)], []
    work = 0
    literal_fail = Counter()
    started = time.perf_counter()
    name = key + ('_backward' if inverse else '_forward')
    raw = gzip.open(HERE/(name+'.csv.gz'), 'wt', newline='') if output else None
    writer = csv.writer(raw) if raw else None
    if writer:
        writer.writerow(['t','L','na','nb','n_f','d_f','split_next','merge_next','S_global','S_local_r1','sum_local_r1','S_local_r5','sum_local_r5'])
    for t in range(steps+1):
        na, nb = fast.counts(w)
        assert (na,nb) == (ca,cb)
        nf, df = fast.pattern_measure(w)
        if not inverse:
            assert nf <= previous_measure[0]
            if t and previous_measure[0]:
                assert (nf,df) < previous_measure
            if extinct is None and nf == 0:
                extinct = t
        previous_measure = (nf,df)
        sg = fast.entropy(len(w),ca+cb)
        row = [t,len(w),ca,cb,nf,df,'','','','','','','']
        row[8] = sg
        if t <= 128 or t % 16 == 0 or t == steps:
            for j,radius in enumerate(PLAN['local_radii']):
                local,total = fast.local_entropy(w,radius)
                width = min(len(w),2*radius+1)
                corrected_bound = width * math.log(2*width) * (ca+cb) / len(w)
                assert local <= corrected_bound + 1e-9
                if local > radius * (ca+cb) / len(w) + 1e-9:
                    literal_fail[str(radius)] += 1
                row[9+2*j:11+2*j] = [local,total]
            samples.append(row.copy())
        if t < steps:
            nw, split, merge = fast.step(w,inverse)
            assert len(nw)-len(w) == split-merge
            row[6:8] = [split,merge]
            work += len(w)
            deltas.append(len(nw)-len(w))
            w = nw
            sizes.append(len(w))
        if writer:
            writer.writerow(row)
    if raw:
        raw.close()
    checked = 0
    if ca and cb and not inverse:
        assert extinct is not None
        for t in range(extinct,steps+1):
            j=t+sizes[t]
            if j<=steps:
                assert 1 <= sizes[j]-sizes[t] <= 2*ca*cb
                checked += 1
    if not ca or not cb:
        assert all(n == len(initial) for n in sizes)
    tail = deltas[-min(512,steps):]
    linear = bool(tail) and len(set(tail))==1
    if inverse and ca and cb and steps >= 4096:
        assert linear and 1<=tail[0]<=min(ca,cb)
    ts=np.arange(max(1,steps//2),steps+1)
    # Diagnostic only; finite fits are not asymptotic proofs.
    exponent=float(np.polyfit(np.log(ts),np.log(np.array(sizes)[ts]),1)[0])
    result = {'name':name,'direction':'backward' if inverse else 'forward','steps':steps,
              'initial_word':initial.tolist(),'final_word':w.tolist() if output else None,
              'na':ca,'nb':cb,'initial_L':len(initial),'final_L':len(w),
              'forward_merger_extinction':None if inverse else extinct,
              'appendix_b_windows':checked,'integer_linear_tail512':linear,
              'tail_slope':tail[-1], 'late_log_size_log_t_fit':exponent,
              'literal_theorem4_failures_under_declared_convention':dict(literal_fail),
              'visited_vertices':work,'seconds':time.perf_counter()-started}
    if output:
        # Full words are in a separate compressed JSON, summary stays compact.
        with gzip.open(HERE/(name+'_words.json.gz'),'wt') as f:
            json.dump({'initial':result['initial_word'],'final':result.pop('final_word')},f)
        result.pop('initial_word')
        dump(name+'_samples.json',samples)
    return result


def entropy_witnesses():
    # Distinct, separated particles of both types also give the contradiction.
    out=[]
    for word,radius in [([1]+[0]*12,1),([1]+[0]*5+[2]+[0]*6,1),([1]+[0]*30,5)]:
        w=np.array(word,dtype=np.uint8)
        val,total=fast.local_entropy(w,radius)
        p=sum(fast.counts(w)); width=min(len(w),2*radius+1)
        out.append({'word':word,'radius':radius,'window_vertices':width,'S_local':val,
                    'printed_rhs':radius*p/len(w), 'corrected_rhs':width*math.log(2*width)*p/len(w),
                    'literal_inequality':val<=radius*p/len(w), 'sum_local':total})
    return out


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--calibrate',action='store_true'); parser.add_argument('--run',action='store_true')
    args=parser.parse_args(); assert args.calibrate != args.run
    hashes=source_hashes()
    words=[w for n in PLAN['exhaustive_lengths'] for w in itertools.product(range(4),repeat=n)]
    if args.calibrate:
        selected=words[::40]
        named=named_checks(selected)
        small=short_trajectories(selected)
        probes=[long_trace(key,w,inv,512,False) for key,w in initials()[:1] for inv in (False,True)]
        predicted_small=(named['seconds']+small['seconds'])*len(words)/len(selected)
        # Quadratic envelope for backward growing-array work; forward is O(t^1.5).
        predicted_long=sum(p['seconds']*(4096/512)**(2 if p['direction']=='backward' else 1.5) for p in probes)*len(initials())
        forecast=predicted_small+predicted_long
        dump('CALIBRATION.json',{'source_sha256':hashes,'named':named,'short':small,'long':probes,
                                'environment':{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()},
                                'forecast_code_seconds':forecast,'range_seconds':[forecast/4,forecast*3],
                                'scope_note':'Calibration separate; includes actual code, checks and raw result writing; excludes preparation/publishing. Envelope uses a dense seed for every long case.'})
        print(json.dumps({'calibration':'done','forecast_code_seconds':forecast}),flush=True)
        return
    calibration=json.loads((HERE/'CALIBRATION.json').read_text())
    assert hashes==calibration['source_sha256']
    started=time.perf_counter()
    named=named_checks(words); dump('LEMMA_AND_PROJECTION.json',named)
    print(json.dumps({'phase':'named_done','counts':named['counts']}),flush=True)
    small=short_trajectories(words,True); dump('EXHAUSTIVE.json',small)
    print(json.dumps({'phase':'exhaustive_done','counts':small['counts']}),flush=True)
    long=[]
    for key,w in initials():
        for inverse in (False,True):
            row=long_trace(key,w,inverse,PLAN['long_trajectory_steps_each_direction'],True)
            long.append(row); dump('LONG_SUMMARY.json',long)
            print(json.dumps({'phase':'trajectory_done','name':row['name'],'final_L':row['final_L'],'seconds':row['seconds']}),flush=True)
    dump('ENTROPY_WITNESSES.json',entropy_witnesses())
    elapsed=time.perf_counter()-started
    assert hashes==source_hashes()
    result={'status':'C1_SCIENCE_EXECUTED_WITH_LOCAL_ENTROPY_COEFFICIENT_QUALIFICATION',
            'named_inputs':len(words),'exhaustive_trajectories':small['counts']['trajectories'],
            'exhaustive_steps':small['counts']['steps'],'long_trajectories':len(long),
            'long_steps':sum(r['steps'] for r in long),'code_seconds':elapsed,
            'forecast_code_seconds':calibration['forecast_code_seconds'],
            'actual_over_forecast':elapsed/calibration['forecast_code_seconds'],
            'source_sha256':hashes,'unexpected_assertion_failures':0,
            'limitation':'Numerical results do not prove infinite-time asymptotics; see separate analytical reconstruction. Literal Theorem 4 is not marked PASS.'}
    dump('RESULTS.json',result); print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
