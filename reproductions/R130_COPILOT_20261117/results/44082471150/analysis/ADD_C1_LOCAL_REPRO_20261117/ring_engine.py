"""Independent ordered-ring implementation. No imports from the graph engine."""
from functools import lru_cache


def atom(i):
    return ('atom', i)


def l(n):
    return n[1] if n[0] == 'join' else ('l', n)


def r(n):
    return n[2] if n[0] == 'join' else ('r', n)


def join(x, y):
    if x[0] == 'l' and y[0] == 'r' and x[1] == y[1]:
        return x[1]
    return ('join', x, y)


@lru_cache(None)
def label(n):
    if n[0] == 'atom':
        return 'u'+str(n[1])
    if n[0] == 'join':
        return '('+label(n[1])+','+label(n[2])+')'
    return n[0].upper()+label(n[1])


@lru_cache(None)
def leaves(n):
    if n[0] == 'atom':
        return ((n[1], ''),)
    if n[0] == 'join':
        return leaves(n[1])+leaves(n[2])
    return tuple((a, p+n[0]) for a, p in leaves(n[1]))


def make(w):
    return tuple((atom(i), s) for i, s in enumerate(w))


def normal(n):
    if n[0] == 'atom':
        return n
    if n[0] == 'join':
        return join(normal(n[1]), normal(n[2]))
    return (l if n[0] == 'l' else r)(normal(n[1]))


def validate(x):
    if not x or len({n for n, s in x}) != len(x):
        raise ValueError('empty ring or duplicate active names')
    support = []
    for n, s in x:
        if normal(n) != n:
            raise ValueError('name is not in normal form')
        if type(s) is not int or s not in range(4):
            raise ValueError('invalid C1 state')
        support.extend(leaves(n))
    for i, (a, p) in enumerate(support):
        for b, q in support[i+1:]:
            if a == b and (p.startswith(q) or q.startswith(p)):
                raise ValueError('A1 overlapping descendants')
    return True


def snapshot(x):
    return {'states': sorted([label(n), s] for n, s in x),
            'edges_b_to_a': sorted([label(n), label(x[(i+1) % len(x)][0])]
                                   for i, (n, s) in enumerate(x))}


def q(x, version='A', inverse=False):
    out = []
    for i, (u, s) in enumerate(x):
        v, t = x[(i+1) % len(x)]
        if version == 'A':
            n = join(r(u), l(v))
            bits = (s & 1) | (t & 2) if inverse else (t & 1) | (s & 2)
        elif version == 'P_ring':
            n = join(r(v), l(u)) if inverse else join(r(u), l(v))
            bits = (s & 1) | (t & 2)
        else:
            raise ValueError('no total operator for P_raw')
        out.append((n, bits))
    return tuple(out if version == 'A' else reversed(out))


def flip(x):
    return tuple((n, ((s & 1) << 1) | ((s & 2) >> 1)) for n, s in x)


def interact(x):
    n = len(x)
    starts = {i for i in range(n) if n > 1 and x[i][1] == 1 and x[(i+1) % n][1] == 2}
    ends = {(i+1) % n for i in starts}
    start = next(i for i in range(n) if i not in ends)
    out, offset = [], 0
    while offset < n:
        i = (start+offset) % n
        u, s = x[i]
        if i in starts:
            out.append((join(u, x[(i+1) % n][0]), 3))
            offset += 2
        elif s == 3:
            out.extend(((l(u), 1), (r(u), 2)))
            offset += 1
        else:
            out.append((u, s))
            offset += 1
    return tuple(out)


def forward(x, version='A'):
    return q(interact(x), version)


def backward(x, version='A'):
    return interact(q(x, version, True))


def printed_shape(x):
    """Unrestricted printed edge quantifiers; no bit-clause repair."""
    names = [n for n, s in x]
    vertices = {label(join(r(u), l(x[(i+1) % len(x)][0]))) for i, u in enumerate(names)}
    edges = {(label(join(r(u), l(a))), label(join(r(b), l(u))))
             for u in names for a in names for b in names}
    return {'vertices': sorted(vertices), 'edges_b_to_a': sorted(map(list, edges)),
            'bits_status': 'UNBOUND_X_IN_PRINTED_CLAUSE'}
