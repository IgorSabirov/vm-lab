"""Finite port graphs, oriented ADD rings, and operations on integer name codes."""
from collections import defaultdict
from functools import lru_cache
from fibonacci import encode, decode, concat, nat, read_nat

K = 22
# Within a name, 0..2 are atoms, 3=L, 4=R, 5=join, 6 introduces atom >=3.
def atom(i):
    if type(i) is not int or i < 0:
        raise ValueError('invalid atom')
    return encode((i,) if i < 3 else (6,)+nat(i-3), K)


def span(w, i):
    """Exclusive end of one prefix term, without recursive parsing."""
    arity_debt = 1
    while arity_debt:
        if i >= len(w):
            raise ValueError('truncated name')
        t, i = w[i], i+1
        if t <= 2:
            arity_debt -= 1
        elif t == 5:
            arity_debt += 1
        elif t == 6:
            _, i = read_nat(w, i)
            arity_debt -= 1
        elif t not in (3, 4):
            raise ValueError('invalid name constructor')
    return i


@lru_cache(maxsize=8192)
def children(n):
    w = decode(n, K)
    if not w or span(w, 0) != len(w):
        raise ValueError('expected one name')
    if w[0] in (3, 4):
        return w[0], (encode(w[1:], K),)
    if w[0] == 5:
        j = span(w, 1)
        return 5, (encode(w[1:j], K), encode(w[j:], K))
    return -1, (w[0] if w[0] <= 2 else 3+read_nat(w, 1)[0],)


def project(n, side):
    tag, args = children(n)
    if tag == 5:
        return args[side]
    return concat(encode((3+side,), K), n, K)


def join(a, b):
    ta, xa = children(a)
    tb, xb = children(b)
    if (ta, tb) == (3, 4) and xa == xb:
        return xa[0]
    return concat(concat(encode((5,), K), a, K), b, K)


def addresses(n):
    """Leaves (atom, dyadic address); reject nonnormal input before A1."""
    work = [(n, 0, 0)]
    while work:
        term, path, depth = work.pop()
        tag, args = children(term)
        if tag == -1:
            yield args[0], path, depth
        elif tag == 5:
            if depth or join(*args) != term:
                raise ValueError('unreduced name')
            work.extend((u, 0, 0) for u in args)
        else:
            work.append((args[0], path+((tag-3)<<depth), depth+1))


def check_names(names, *, internal_disjoint=True):
    # A prefix collision is nesting of half-open dyadic intervals.
    by_atom = defaultdict(list)
    seen = set()
    for n in names:
        if n in seen:
            raise ValueError('duplicate vertex')
        seen.add(n)
        for a, p, d in addresses(n):
            by_atom[a].append((p, d, n))
    for intervals in by_atom.values():
        depth = max(d for _, d, _ in intervals)
        end, owner = 0, None
        for a,b,n in sorted((p << (depth-d), (p+1) << (depth-d), n) for p,d,n in intervals):
            if a < end and (internal_disjoint or n != owner):
                raise ValueError('A1: overlapping descendants')
            if b > end:
                end, owner = b, n


def ring_code(records, channels=2):
    if channels not in (1, 2) or not records:
        raise ValueError('expected a nonempty C1/C2 ring')
    check_names(n for n, _ in records)
    if any(type(s) is not int or not 0 <= s < 4**channels for _, s in records):
        raise ValueError('invalid state')
    rows = [decode(n, K)+(6+s,) for n, s in records]
    first = min(range(len(rows)), key=rows.__getitem__)
    return encode(sum(rows[first:]+rows[:first], ()), K)


def read_ring(code, channels=2):
    records = []
    w = decode(code, K)
    i = 0
    while i < len(w):
        end = span(w, i)
        if end == len(w) or not 6 <= w[end] < 6+4**channels:
            raise ValueError('missing vertex state')
        records.append((encode(w[i:end], K), w[end]-6))
        i = end+1
    if ring_code(records, channels) != code:
        raise ValueError('noncanonical rotation')
    return records


def transfer(rows, inverse, channels):
    a = 1 if channels == 1 else 5
    b = 2*a
    own, other = (a,b) if inverse else (b,a)
    pairs = zip(rows, rows[1:]+rows[:1])
    return [(join(project(x,1),project(y,0)), (s & own) | (t & other))
            for (x,s),(y,t) in pairs]


def scatter(rows, channels):
    split = {3:(1,2)} if channels == 1 else {3:(1,2),12:(8,4)}
    merge = {p:s for s,p in split.items()}
    # Cut away from an interacting edge (possible since pairs are disjoint).
    if len(rows)>1 and (rows[-1][1],rows[0][1]) in merge:
        rows = rows[-1:]+rows[:-1]
    output = []
    i = 0
    while i < len(rows):
        x,s = rows[i]
        if i+1 < len(rows) and (s, rows[i+1][1]) in merge:
            y,t = rows[i+1]
            output.append((join(x,y), merge[s,t]))
            i += 2
        elif s in split:
            output.extend((project(x,j),t) for j,t in enumerate(split[s]))
            i += 1
        else:
            output.append((x,s))
            i += 1
    return output


def step(code, channels=2, inverse=False):
    rows = read_ring(code, channels)
    if inverse:
        out = scatter(transfer(rows, True, channels), channels)
    else:
        out = transfer(scatter(rows, channels), False, channels)
    return ring_code(out, channels)


def graph_code(vertices, edges):
    """Finite port graph. A vertex=(name code, state), endpoint=(name code, port).
    Canonical order by numeric name, then sorted undirected endpoint pairs.
    """
    vs = sorted(vertices)
    check_names((n for n,_ in vs), internal_disjoint=False)
    index = {n:i for i,(n,_) in enumerate(vs)}
    es = []
    occupied = set()
    for edge in edges:
        if len(edge) != 2:
            raise ValueError('edge must have two ports')
        pair = []
        for n,p in edge:
            if n not in index or (n,p) in occupied:
                raise ValueError('dangling or multiply occupied port')
            occupied.add((n,p))
            pair.append((index[n],p))
        es.append(sorted(pair))
    tokens = list(nat(len(vs)))
    for n,s in vs:
        tokens.extend(decode(n,K)+nat(s))
    tokens.extend(nat(len(es)))
    for pair in sorted(es):
        for v,p in pair:
            tokens.extend(nat(v)+nat(p))
    return encode(tokens,K)


def read_graph(code):
    w = decode(code,K)
    count,i = read_nat(w,0)
    vs, es = [], []
    for _ in range(count):
        j = span(w,i)
        s,k = read_nat(w,j)
        vs.append((encode(w[i:j],K),s))
        i = k
    count,i = read_nat(w,i)
    for _ in range(count):
        pair = []
        for _ in range(2):
            v,i = read_nat(w,i)
            p,i = read_nat(w,i)
            if v >= len(vs):
                raise ValueError('unknown vertex')
            pair.append((vs[v][0],p))
        es.append(tuple(pair))
    if i != len(w) or graph_code(vs,es) != code:
        raise ValueError('noncanonical graph')
    return vs, es


def ring_to_graph(code,channels=2):
    rows = read_ring(code,channels)
    edges = [((n,1),(rows[(i+1)%len(rows)][0],0)) for i,(n,_) in enumerate(rows)]
    return graph_code(rows,edges)


def graph_to_ring(code,channels=2):
    vs,es = read_graph(code)
    if not vs or len(es) != len(vs):
        raise ValueError('not a complete port ring')
    successor = {}
    for first,second in es:
        (v,a),(u,b) = sorted((first,second),key=lambda item:item[1])
        if (a,b) != (0,1):
            raise ValueError('expected one b-to-a edge')
        successor[u] = v
    states = dict(vs)
    start = vs[0][0]
    order = []
    current = start
    while True:
        order.append((current,states[current]))
        current = successor[current]
        if current == start: break
    if len(order) != len(vs):
        raise ValueError('disconnected cycles')
    return ring_code(order,channels)
