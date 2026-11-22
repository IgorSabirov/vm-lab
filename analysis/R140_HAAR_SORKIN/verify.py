"""Haar transport and length-history operators on the named ADD ring (R140)."""
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
from runpy import run_path

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / 'ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py'
E = run_path(str(ENGINE))
EPS = (1, -1)
N = 3
TOL = 1e-12


def near(x, y):
    np.testing.assert_allclose(x, y, rtol=0, atol=TOL)


def rooted(graph):
    """Quotient only by the starting index of an oriented named ring."""
    return min(graph[i:] + graph[:i] for i in range(len(graph)))


@lru_cache(None)
def alternatives(graph):
    return (rooted(E['transport'](graph, 2)), rooted(E['forward'](graph, EPS)))


@lru_cache(None)
def links(length):
    return tuple(product(range(N), repeat=length))


@lru_cache(None)
def physical(length):
    """Columns are normalized orbit sums at fixed U(1) holonomy in Z_N."""
    return np.asarray([np.eye(N)[sum(g) % N] for g in links(length)]) / N**((length-1)/2)


def labelled_blocks(graph):
    """Map outgoing edge indices to the ordered children produced by the R130 engine."""
    target = E['interact'](graph, EPS)
    old = {u: i for i, (u, _) in enumerate(graph)}
    blocks = []
    j = 0
    while j < len(target):
        v, s = target[j]
        if s in (3, 12) and E['left'](v) in old and E['right'](v) in old:
            i, k = old[E['left'](v)], old[E['right'](v)]
            assert k == (i + 1) % len(graph)
            blocks.append(('merge', i, k))
        elif j+1 < len(target) and E['join'](v, target[j+1][0]) in old and (s, target[j+1][1]) in ((1, 2), (8, 4)):
            i = old[E['join'](v, target[j+1][0])]
            blocks.append(('split', i))
            j += 1
        else:
            blocks.append(('keep', old[v]))
        j += 1
    used = [i for _, *indices in blocks for i in indices]
    assert sorted(used) == list(range(len(graph)))
    return target, blocks


def tiling(graph):
    """Each active domain has a name and two expansions, coarse and fine."""
    _, blocks = labelled_blocks(graph)
    tiles = []
    for kind, i, *rest in blocks:
        name, label = graph[i]
        if kind == 'keep':
            tiles.append((name, (graph[i],), None))
            continue
        if kind == 'merge':
            second = graph[rest[0]]
            name = E['join'](name, second[0])
            label = 3 if label == 1 else 12
        child_labels = (1, 2) if label == 3 else (8, 4)
        coarse = ((name, label),)
        fine = ((E['left'](name), child_labels[0]), (E['right'](name), child_labels[1]))
        tiles.append((name, coarse, fine))
    return tiles


def flip_named(graph, chosen):
    current = {u: label for u, label in graph}
    out = []
    for name, coarse, fine in tiling(graph):
        if fine is None:
            out.extend(coarse)
        else:
            is_coarse = current.get(name) == coarse[0][1]
            out.extend(coarse if (is_coarse != (name in chosen)) else fine)
    return rooted(tuple(out))


def local_coins():
    cases = 0
    for n in range(1,4):
        for word in product(range(16), repeat=n):
            graph = E['named'](word)
            active = {u for u, _, fine in tiling(graph) if fine is not None}
            assert flip_named(graph, active) == rooted(E['interact'](graph, EPS))
            assert E['equal'](E['backward'](E['forward'](graph, EPS), EPS), graph)
            cases += 1
    graph = E['named']((1,2,12))
    a,b = [u for u, _, fine in tiling(graph) if fine is not None]
    corners = [flip_named(graph, mask) for mask in (set(),{b},{a},{a,b})]
    coin = np.exp(-1j*np.pi/4) * np.array([[1,1j],[1j,1]]) / np.sqrt(2)
    matrix = np.zeros((4,4), complex)
    for col, x in enumerate(corners):
        assert {u for u,_,fine in tiling(x) if fine is not None} == {a,b}
        assert flip_named(flip_named(x,{a}),{b}) == flip_named(flip_named(x,{b}),{a})
        for mask in (set(),{b},{a},{a,b}):
            row = corners.index(flip_named(x,mask))
            matrix[row,col] = np.exp(-1j*np.pi/2)*1j**len(mask)/2
    near(matrix, np.kron(coin,coin))
    near(matrix.conj().T @ matrix, np.eye(4))
    return dict(exhaustive_named_words=cases, mixed_orbit_size=len(corners),
                probabilities_on_mixed_input=[0.25]*4)


def raw_transition(graph):
    target, blocks = labelled_blocks(graph)
    splits = sum(b[0] == 'split' for b in blocks)
    merges = sum(b[0] == 'merge' for b in blocks)
    f = E['transport'](target, 2)
    assert E['equal'](f, E['forward'](graph, EPS))
    # Transport Q assigns the tail frame and outgoing link to its named midpoint.
    assert [v for v, _ in f] == [E['join'](E['right'](u), E['left'](target[(i+1) % len(target)][0]))
                                  for i, (u, _) in enumerate(target)]
    assert E['equal'](E['backward'](f, EPS), graph)
    lookup = {g: i for i, g in enumerate(links(len(f)))}
    counts = np.zeros((len(lookup), len(links(len(graph)))), dtype=int)
    for j, g in enumerate(links(len(graph))):
        for samples in product(range(N), repeat=splits):
            out, noise = [], iter(samples)
            for kind, i, *other in blocks:
                if kind == 'split':
                    a = next(noise)
                    out.extend([a, (g[i]-a) % N])
                elif kind == 'merge':
                    out.append((g[i]+g[other[0]]) % N)
                else:
                    out.append(g[i])
            counts[lookup[tuple(out)], j] += 1
    # Markov pushforward and quantum amplitudes use different normalizations.
    assert np.all(counts.sum(axis=0) == N**splits)
    assert np.all(counts.sum(axis=1) == N**merges)
    near(counts.sum(axis=1) / (N**splits * counts.shape[1]), 1/counts.shape[0])
    lift = counts / N**((splits+merges)/2)
    old, new = physical(len(graph)), physical(len(f))
    near(lift @ old, new)
    near(lift.T @ new, old)
    return f, [splits, merges], lift


def geometry_checks():
    words = ((3, 0, 0), (12, 0, 0), (1, 2, 0), (8, 4, 0), (1, 2, 12), (8, 4, 3))
    cases = []
    for word in words:
        for k in range(len(word)):
            graph = E['named'](word[k:] + word[:k])
            for t in range(2):
                graph, counts, _ = raw_transition(graph)
                cases.append((len(graph), counts))
    # Every change of frames on all used lengths permutes link states and fixes the physical columns.
    frame_count = 0
    for length in sorted({3} | {length for length, _ in cases}):
        states = np.asarray(links(length))
        powers = N**np.arange(length-1, -1, -1)
        basis = physical(length)
        for frame in states:
            dest = ((states + frame - np.roll(frame, -1)) % N) @ powers
            assert len(set(dest)) == len(states)
            near(basis[dest], basis)
            frame_count += 1
    graph = E['named']((1, 2, 12))
    _, _, mixed = raw_transition(graph)
    # Even equal raw dimensions do not make a simultaneous merge and split unitary.
    rank = int(np.linalg.matrix_rank(mixed))
    assert mixed.shape == (27, 27) and rank == 9
    h = np.exp(2j*np.pi*np.arange(N)/N)
    psi = (1 + h) / np.sqrt(2*N)
    near(np.vdot(psi, psi), 1)
    near(np.vdot(psi, h*psi), 0.5)
    for length in (2, 3, 4):
        state = physical(length) @ psi
        wilson = np.array([h[sum(g) % N] for g in links(length)])
        near(np.vdot(state, wilson * state), 0.5)
        near(np.sum(abs(state[wilson == 1])**2), 2/3)
    # Check the two-parameter bijection of the reviews, retaining the relative coordinate.
    storage = {((a+b) % N, a) for a,b in links(2)}
    assert len(storage) == N*N and all((r,(c-r) % N) in links(2) for c,r in storage)
    return dict(named_steps=len(cases), frame_assignments=frame_count, mixed_raw_rank=rank,
                mixed_raw_dimension=len(mixed), physical_dimension=N, wilson_mean=0.5,
                initial_holonomy_zero_probability="2/3", relative_register_size=N)


def histories(initial, steps, coherent):
    # Keep amplitudes as Gaussian integers. Each coherent step contributes 1/sqrt(2).
    paths = {((), rooted(initial)): 1}
    for _ in range(steps):
        following = defaultdict(complex)
        for (record, graph), amplitude in paths.items():
            idle, moved = alternatives(graph)
            moves = ((idle, 1), (moved, 1j)) if coherent else ((moved, 1),)
            for out, weight in moves:
                following[record + (len(out),), out] += amplitude * weight
        paths = following
    records = sorted({r for r, _ in paths})
    endpoints = sorted({g for _, g in paths})
    by_record = {r: i for i, r in enumerate(records)}
    by_graph = {g: i for i, g in enumerate(endpoints)}
    vectors = np.zeros((len(records), len(endpoints)), dtype=complex)
    for (r, g), a in paths.items():
        vectors[by_record[r], by_graph[g]] += a
    return records, vectors, 2**steps if coherent else 1


def projected_vectors(initial, record, angle=np.pi/4):
    # Independent class-operator route: build rectangular unitary-step restrictions
    # between forward cones and project on length after each actual forward step.
    current = [rooted(initial)]
    state = np.ones(1, dtype=complex)
    for observed in record:
        outputs = sorted({y for x in current for y in alternatives(x)})
        rows = {x:i for i,x in enumerate(outputs)}
        kernel = np.zeros((len(outputs), len(current)), dtype=complex)
        for j, x in enumerate(current):
            active = [u for u, _, fine in tiling(x) if fine is not None]
            assert len(active) <= 1
            for n in range(len(active)+1):
                for chosen in combinations(active,n):
                    after_i = flip_named(x, set(chosen))
                    out = rooted(E['transport'](after_i,2))
                    weight = (1j*np.sin(angle))**n * np.cos(angle)**(len(active)-n)
                    kernel[rows[out],j] += np.exp(-1j*angle*len(active))*weight
        near(kernel.conj().T @ kernel, np.eye(len(current)))
        state = (kernel @ state) * [len(x) == observed for x in outputs]
        current = outputs
    return state


def interference(gram, events):
    value = 0
    for size in range(1, len(events)+1):
        for subset in combinations(events,size):
            ix = sorted(set().union(*subset))
            value += (-1)**(len(events)-size) * gram[np.ix_(ix,ix)].sum().real
    return value


def history_checks():
    x = E['named']((1,2,0))
    # One a-bit and one b-bit throughout imply at most one active tile.
    # The two branches below differ from the local-coin convention only by
    # one common phase per step, including when the interaction is idle.
    records, vectors, denominator = histories(x, 8, True)
    gram = vectors @ vectors.conj().T
    near(gram, gram.conj().T)
    assert gram.sum().real == gram.trace().real == denominator and gram.sum().imag == 0
    assert np.linalg.eigvalsh(gram / denominator).min() > -TOL
    a = (3,3,3,2,2,2,2,2)
    b = (2,2,2,2,3,3,3,2)
    i,j = records.index(a), records.index(b)
    for ix in (i,j):
        near(projected_vectors(x, records[ix]), vectors[ix]/np.sqrt(denominator))
    cross = int(2*gram[i,j].real)
    assert cross == -4 and denominator == 256
    # Switch the local interaction continuously between idling and exact ADD.
    scans = []
    for angle in (0, np.pi/8, np.pi/4, np.pi/2):
        va, vb = (projected_vectors(x, rec, angle) for rec in (a,b))
        value = float(2*np.vdot(va,vb).real)
        scans.append(0.0 if abs(value) < TOL else round(value,12))
    near([scans[0], scans[2], scans[3]], [0, -1/64, 0])
    d = np.diag(np.diag(gram))
    others = [k for k in range(len(records)) if k not in (i, j)]
    events = [{i}, {j}, set(others[::2]), set(others[1::2])]
    assert sum(map(len,events)) == len(records)
    assert interference(gram, events[:2]) == cross
    for triple in combinations(events,3):
        assert interference(gram,triple) == 0
    assert interference(gram,events) == 0
    for eta in (0,0.25,0.5,1):
        recorded = (1-eta)*d + eta*gram
        assert interference(recorded, events[:2]) == eta*cross
        near(recorded.sum()/denominator, 1)
    # Link-state projectors commute with length detection for this holonomy-preserving lift.
    h = np.exp(2j*np.pi*np.arange(N)/N)
    psi = (1+h)/np.sqrt(2*N)
    near((abs(psi)**2).sum(), 1)
    near((2*gram[i,j].real / denominator)*abs(psi[0])**2, -1/96)
    records_det, deterministic, _ = histories(x,8,False)
    assert deterministic.shape == (1,1) and deterministic[0,0] == 1
    return dict(word=[1,2,0], steps=8, length_histories=len(records), endpoints=vectors.shape[1],
                selected=[a,b], numerator_diag=[int(gram[i,i].real),int(gram[j,j].real)],
                union_numerator=int(gram[np.ix_([i,j],[i,j])].sum().real),
                I2_numerator=cross, denominator=denominator, I3=0, I4=0,
                I2_with_holonomy_zero="-1/96", classical_I2=0,
                angle_scan_pi_units=["0", "1/8", "1/4", "1/2"], angle_scan_I2=scans,
                normalized=True, positive_semidefinite=True, deterministic_length_path=records_det[0])


def peer_controls():
    rng = np.random.default_rng(7)
    a,b = rng.random((2,300000))
    c=(a+b)%1
    first = rng.random(len(c))
    second = (0.3-rng.random(len(c)))%1
    amplitudes = rng.normal(size=12)+1j*rng.normal(size=12)
    amplitudes = amplitudes.reshape(4,3).sum(axis=1)
    kernel = np.outer(amplitudes,amplitudes.conj())
    events = [{i} for i in range(4)]
    i2=interference(kernel,events[:2])
    near(i2,28.587342666265975)
    near(interference(kernel,events[:3]),0)
    near(interference(kernel,events),0)
    near(np.linalg.eigvalsh(np.array([[1,2],[2,1]])/6), [-1/6,1/2])  # R008
    old = run_path(str(HERE.parent / 'R139_ARRIGHI_DISCRETE_DYNAMICS/verify.py'))['check']()
    assert (old['probability_fine_coherent'],old['probability_fine_dephased']) == (1, 0.5)
    return dict(R139_replay=[1, 0.5], R008_negative_eigenvalue="-1/6", seed=7, U1_merge_KS=round(float(stats.kstest(c,'uniform').statistic),10),
                U1_split_KS=round(float(stats.ks_2samp(first,second).statistic),10),
                random_I2=round(float(i2),10), cyclic24_frobenius_defect=round(np.sqrt(576-24),10))


if __name__ == '__main__':
    print(json.dumps(dict(R130_sha256=sha256(ENGINE.read_bytes()).hexdigest(), finite_group='Z3',
                          H0_H3=geometry_checks(), local_coins=local_coins(), H4_H5=history_checks(),
                          reviewer_baselines=peer_controls()), indent=2))
