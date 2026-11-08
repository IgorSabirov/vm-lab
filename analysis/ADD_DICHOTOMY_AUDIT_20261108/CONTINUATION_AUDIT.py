#!/usr/bin/env python3
"""Independent bounded audit of four explicitly distinct transport conventions.

Bit order: integer bit 0=a1, 1=b1, 2=a2, 3=b2. Words follow b->a.
The imported frozen core supplies Name/Graph/I2, never the word dynamics.
No VM calls, network, pip installs, or experiment integration.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import platform
import sys
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("frozen_ft10", HERE / "source/ADD_FT10_MINIMAL.py")
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)
MODES = {
    "LITERAL_DEF4": (False, True),
    "FIG2A_BITS_ONLY": (True, True),
    "FIG2A_FULL": (True, False),
    "PRESERVE_EDGES_LITERAL_BITS": (False, False),
}
SPLIT = {3: (1, 2), 12: (4, 8)}
MERGE = {(1, 2): 3, (4, 8): 12}


def canon(w):
    w = tuple(w)
    return min(w[i:] + w[:i] for i in range(len(w)))


def bits(s):
    return tuple((s >> i) & 1 for i in range(4))


def motifs(w):
    return (sum(x in SPLIT for x in w),
            sum((x, w[(i+1) % len(w)]) in MERGE for i, x in enumerate(w)))


def particles(w):
    return tuple(sum((s >> i) & 1 for s in w) for i in range(4))


def collision(w):
    """Simultaneous disjoint rewrites; explicitly handle a pair crossing the cut."""
    n = len(w)
    start = 1 if (w[-1], w[0]) in MERGE else 0
    out = []
    i = 0
    while i < n:
        s, t = w[(start+i) % n], w[(start+i+1) % n]
        if (s, t) in MERGE:
            out.append(MERGE[s, t])
            i += 2
        else:
            out.extend(SPLIT.get(s, (s,)))
            i += 1
    return tuple(out)


def half(w, mode):
    swap, reverse = MODES[mode]
    h = tuple(((t & 5) | (s & 10)) if swap else ((s & 5) | (t & 10))
              for s, t in zip(w, w[1:] + w[:1]))
    return h[::-1] if reverse else h


def step(w, mode):
    return half(collision(w), mode)


def facing(s, t):
    """One b-channel at the left faces the same single a-channel at the right."""
    return ((s & 10), (t & 5)) in ((2, 1), (8, 4))


def gap_toggle(w):
    """Independent J=Q I Q rule: toggle zero/one empty vertex at eligible gaps.

    Nonzero vertices retain their states. Simultaneous deletions never touch;
    insertions occur only between original adjacent nonzero endpoints.
    """
    out = []
    for i, s in enumerate(w):
        previous, following = w[i-1], w[(i+1) % len(w)]
        if not (s == 0 and facing(previous, following)):
            out.append(s)
        if facing(s, following):
            out.append(0)
    assert out
    return tuple(out)


def structural_checks(max_L=5):
    """Finite crosschecks of the local rules used in the arbitrary-L proof."""
    results = []
    active_period2 = None
    mode = "FIG2A_BITS_ONLY"
    for L in range(1,max_L+1):
        reps, weighted = 0, 0
        started = time.perf_counter()
        for w in itertools.product(range(16), repeat=L):
            if canon(w) != w:
                continue
            reps += 1
            weighted += len({w[i:]+w[:i] for i in range(L)})
            j = gap_toggle(w)
            assert canon(j) == canon(half(collision(half(w,mode)),mode))
            assert canon(gap_toggle(j)) == w
            assert canon(collision(j)) == canon(gap_toggle(collision(w)))
            assert particles(j) == particles(w)
            z = w
            for _ in range(4):
                z = step(z,mode)
            assert canon(z) == w
            if active_period2 is None and not any(motifs(w)):
                o = orbit(w,mode,4)
                if o['active'] and o['period'] == 2:
                    active_period2 = {"initial":w, **o}
        assert weighted == 16**L
        row = {"L":L,"all_labelled_words":weighted,"rotation_representatives":reps,
               "J_equals_QIQ":True,"J_involution":True,"I_J_commute":True,
               "F_fourth_is_identity_word":True,"seconds":time.perf_counter()-started}
        results.append(row)
        print(json.dumps(row),flush=True)
    return {"all_states_not_only_E0":results,"active_period2_E0_witness":active_period2,
            "proof_reference":"CONTINUATION_REPORT.md#arbitrary-l-proof"}


def spectral_checks():
    import sympy as sp
    x = sp.Symbol('lambda')
    valid = [s for s in range(16) if s not in SPLIT]
    pairs = [(s,t) for s in valid for t in valid if (s,t) not in MERGE]
    indexes = {pair:i for i,pair in enumerate(pairs)}
    E = sp.zeros(16)
    QL = sp.zeros(16)
    QF = sp.zeros(len(pairs))
    for s,t in pairs:
        E[s,t] = 1
        if ((s & 5) | (t & 10)) not in SPLIT:
            QL[s,t] = 1
    for i,(s,t) in enumerate(pairs):
        h1 = (t & 5) | (s & 10)
        for u in valid:
            if (t,u) not in indexes:
                continue
            h2 = (u & 5) | (t & 10)
            # h1 was checked by the previous transition of every closed walk.
            # Keeping these transient edges reproduces the supplied 2424-edge
            # presentation rather than its equally valid 2196-edge pruning.
            if h2 not in SPLIT and (h2,h1) not in MERGE:
                QF[i,indexes[t,u]] = 1
    expected = [x**14*(x*x-14*x+2), x**13*(x-1)*(x*x-13*x+4),
                x**187*(x**3-x*x-2*x-1)*(x**4-13*x**3+6*x*x+7*x+4)]
    rows = {}
    for name,M,want in zip(('E0','Q_literal','Q_bits_only'),(E,QL,QF),expected):
        t0 = time.perf_counter()
        polynomial = M.charpoly(x).as_expr()
        assert sp.expand(polynomial-want) == 0
        factor = sp.factor(polynomial)
        # Obtain exact traces from the characteristic polynomial (Newton sums),
        # avoiding dense matrix powers; these are compared to direct word counts.
        coefficients = sp.Poly(polynomial,x).all_coeffs()
        traces = [M.rows]
        for n in range(1,7):
            traces.append(-sum(coefficients[j]*traces[n-j] for j in range(1,n))-n*coefficients[n])
        rows[name] = {'dimension':M.rows,'transition_edges':int(sum(M)),
                      'charpoly':str(factor),'matches_neighbor':True,
                      'traces_L1_L6':[int(v) for v in traces[1:]],'seconds':time.perf_counter()-t0}
    return {'sympy':sp.__version__,'matrices':rows,
            'quiet_invariant_all_L':True,'proof_reference':'CONTINUATION_REPORT.md#quiet-class'}


def ordered_nodes(g):
    nxt = {p.node: q.node for p, q in g.edges}
    out = [next(iter(g.states))]
    while nxt[out[-1]] != out[0]:
        out.append(nxt[out[-1]])
    assert len(out) == len(g.states)
    return out


def graph_word(g):
    return canon(tuple(sum(v << i for i, v in enumerate(g.states[n])) for n in ordered_nodes(g)))


def graph_half(g, mode):
    swap, reverse = MODES[mode]
    ns = ordered_nodes(g)
    names = [core.merge_name(core.proj_right(u), core.proj_left(v))
             for u, v in zip(ns, ns[1:] + ns[:1])]
    states = {}
    for i, name in enumerate(names):
        s, t = g.states[ns[i]], g.states[ns[(i+1) % len(ns)]]
        states[name] = (t[0], s[1], t[2], s[3]) if swap else (s[0], t[1], s[2], t[3])
    es = [(core.Port(n, "b"), core.Port(names[(i+(-1 if reverse else 1)) % len(ns)], "a"))
          for i, n in enumerate(names)]
    out = core.Graph(states, es)
    core.validate_graph(out)
    core.validate_A1(out)
    return out


def graph_half_inverse(g, mode):
    """Recover each old vertex from its adjacent new vertices, with explicit names."""
    swap, reverse = MODES[mode]
    ws = ordered_nodes(g)
    # For reverse edges w_i follows w_(i+1); for forward edges w_i follows w_(i-1).
    old, states = [], {}
    for i, w in enumerate(ws):
        previous = ws[(i + (1 if reverse else -1)) % len(ws)]
        u = core.merge_name(core.proj_right(previous), core.proj_left(w))
        old.append(u)
        a_source, b_source = (previous, w) if swap else (w, previous)
        a, b = g.states[a_source], g.states[b_source]
        states[u] = (a[0], b[1], a[2], b[3])
    es = [(core.Port(u, "b"), core.Port(old[(i+(-1 if reverse else 1)) % len(old)], "a"))
          for i, u in enumerate(old)]
    out = core.Graph(states, es)
    core.validate_graph(out)
    core.validate_A1(out)
    return out


def snapshot(g):
    return {"vertices": [{"name": core.name_text(n), "bits": g.states[n]} for n in ordered_nodes(g)],
            "edges": [[core.name_text(p.node)+":b", core.name_text(q.node)+":a"] for p,q in g.edges],
            "word": graph_word(g)}


def graph_gates():
    """Exhaustive L<=2 C2 plus L=3 C1; no derived Q used as tau oracle."""
    count = 0
    for alphabet, lengths in ((range(16), (1, 2)), (range(4), (3,))):
        for L in lengths:
            for w in itertools.product(alphabet, repeat=L):
                g = core.ring_graph([bits(s) for s in w])
                core.validate_A1(g)
                ig = core.I2(g)
                core.validate_A1(ig)
                assert graph_word(ig) == canon(collision(w))
                assert core.graph_equal(core.I2(ig), g)
                for mode in MODES:
                    q = graph_half(g, mode)
                    assert graph_word(q) == canon(half(w, mode))
                    assert graph_word(graph_half(ig, mode)) == canon(step(w, mode))
                    assert core.graph_equal(graph_half_inverse(q, mode), g)
                    assert core.graph_equal(graph_half(graph_half_inverse(g, mode), mode), g)
                    assert particles(w) == core.particle_counts(q)
                    if mode == "LITERAL_DEF4":
                        assert core.graph_equal(q, core.sqrt_tau(g))
                count += 1
    # Independent 16 single-occupied-slot worldlines on a four-node ring.
    tau_results = {}
    for mode in MODES:
        named_pass = word_pass = 0
        witness = None
        for slot in range(16):
            w = [0]*4
            w[slot//4] = 1 << (slot % 4)
            g = core.ring_graph([bits(s) for s in w])
            q2 = graph_half(graph_half(g, mode), mode)
            tau = core.tau_port_reference(g)
            ok = core.graph_equal(q2, tau)
            named_pass += ok
            word_pass += graph_word(q2) == graph_word(tau)
            if not ok and witness is None:
                witness = {"input": snapshot(g), "q_squared": snapshot(q2), "tau_port": snapshot(tau)}
        tau_results[mode] = {"cases": 16, "exact_named_pass": named_pass,
                             "word_rotation_pass": word_pass, "counterexample": witness}
    # Rotation alone hides the single-particle shift; use a mixed C2 state as well.
    w = (0, 4, 9, 2)
    g = core.ring_graph([bits(s) for s in w])
    for mode in MODES:
        q2 = graph_half(graph_half(g, mode), mode)
        tau_results[mode]["mixed_word_equals_tau"] = graph_word(q2) == graph_word(core.tau_port_reference(g))
        tau_results[mode]["mixed_q_squared"] = graph_word(q2)
    return {"projection_and_inverses_graphs": count, "four_modes": list(MODES),
            "tau_port_worldlines": tau_results}


def orbit(w, mode, horizon=40, cap=256):
    initial = canon(w)
    seen, states = {}, []
    current = initial
    for t in range(horizon+1):
        key = canon(current)
        if key in seen:
            start = seen[key]
            return {"period": t-start, "transient": start, "active": any(any(motifs(x)) for x in states),
                    "max_L": max(map(len, states)), "min_L": min(map(len, states)), "states": states}
        if len(current) > cap:
            break
        seen[key] = t
        states.append(key)
        current = step(key, mode)
    return {"period": None, "transient": None, "active": any(any(motifs(x)) for x in states),
            "max_L": max(map(len, states)), "min_L": min(map(len, states)), "states": states}


def exhaustive(L, alphabet, modes, horizon=40):
    started = time.perf_counter()
    e0_alphabet = [s for s in alphabet if s not in SPLIT]
    total, reps = 0, 0
    data = {m: {"first": Counter(), "periods": Counter(), "active": 0, "transients": 0,
                "unresolved": 0, "max_L": L, "min_L": L, "witnesses": {}} for m in modes}
    for w in itertools.product(e0_alphabet, repeat=L):
        if motifs(w)[1] or canon(w) != w:
            continue
        weight = len({w[i:]+w[:i] for i in range(L)})
        total += weight
        reps += 1
        for mode in modes:
            d = data[mode]
            s, m = motifs(half(w, mode))
            category = "both" if s and m else "split_only" if s else "merge_only" if m else "none"
            d["first"][category] += weight
            o = orbit(w, mode, horizon)
            assert all(particles(x) == particles(w) for x in o["states"])
            if mode in ("LITERAL_DEF4", "FIG2A_FULL"):
                assert all(motifs(x)[1] == 0 for x in o["states"])
                assert all(len(y)-len(x) == motifs(x)[0] for x,y in zip(o['states'],o['states'][1:]))
            if mode == "LITERAL_DEF4":
                assert all(motifs(y)[0] >= motifs(x)[0] for x,y in zip(o['states'],o['states'][1:]))
            label = str(o["period"]) if o["period"] is not None else "unresolved"
            d["periods"][label] += weight
            d["active"] += weight*o["active"]
            d["transients"] += weight*bool(o["transient"])
            d["unresolved"] += weight*(o["period"] is None)
            d["max_L"] = max(d["max_L"], o["max_L"])
            d["min_L"] = min(d["min_L"], o["min_L"])
            if label not in d["witnesses"]:
                d["witnesses"][label] = {"initial": w, **o}
    return {"L": L, "alphabet_size": len(alphabet), "labelled_E0": total,
            "rotation_representatives": reps, "horizon": horizon, "modes": data,
            "seconds": time.perf_counter()-started}


def named_witness(w, mode, horizon):
    g = g0 = core.ring_graph([bits(s) for s in w])
    records, period = [], None
    for t in range(horizon+1):
        core.validate_A1(g)
        records.append({"t": t, "L": len(g.states), "motifs": motifs(graph_word(g)), **snapshot(g)})
        if t and core.graph_equal(g, g0):
            period = t
            break
        if t < horizon:
            g = graph_half(core.I2(g), mode)
    return {"initial": w, "mode": mode, "exact_named_period": period, "trace": records}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=("gates", "orbits", "witnesses", "structural", "spectra"), required=True)
    p.add_argument("--lengths", default="2,3,4")
    p.add_argument("--alphabet", type=int, default=16, choices=(4,16))
    p.add_argument("--modes", default="FIG2A_BITS_ONLY")
    p.add_argument("--horizon", type=int, default=40)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    t0 = time.perf_counter()
    result = {"stage": a.stage, "python": sys.version, "platform": platform.platform(),
              "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "frozen_core_sha256": hashlib.sha256((HERE/"source/ADD_FT10_MINIMAL.py").read_bytes()).hexdigest()}
    if a.stage == "gates":
        result["gates"] = graph_gates()
    elif a.stage == "orbits":
        result["exhaustive"] = []
        for L in map(int, a.lengths.split(",")):
            r = exhaustive(L, range(a.alphabet), a.modes.split(","), a.horizon)
            result["exhaustive"].append(r)
            print(json.dumps({"L":L,"E0":r["labelled_E0"],"seconds":r["seconds"],
                              "modes": {m:{k:v for k,v in d.items() if k!="witnesses"} for m,d in r["modes"].items()}}),flush=True)
    elif a.stage == "spectra":
        result["spectra"] = spectral_checks()
    elif a.stage == "structural":
        result["structural"] = structural_checks(max(map(int,a.lengths.split(','))))
    else:
        result["witnesses"] = [named_witness(w,m,h) for w,m,h in
            [((0,2,0,1),"LITERAL_DEF4",8), ((0,2,0,1),"FIG2A_BITS_ONLY",20),
             ((0,4,9),"FIG2A_BITS_ONLY",8), ((0,4,9),"LITERAL_DEF4",8),
             ((0,2,0,1),"FIG2A_FULL",12), ((0,4,9),"FIG2A_FULL",12),
             ((0,1,6,1,6),"FIG2A_BITS_ONLY",4)]]
    result["wall_seconds"] = time.perf_counter()-t0
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"saved":str(a.out),"seconds":result["wall_seconds"]}),flush=True)


if __name__ == "__main__":
    main()
