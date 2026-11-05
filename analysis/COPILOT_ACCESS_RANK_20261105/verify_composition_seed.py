#!/usr/bin/env python3
"""Exact n=3 enumeration of partial binary operations and seed semantics.

Each table entry is one of 0,1,2, or BOT=3 (undefined).
Definitions are stated explicitly below; no Monte Carlo is used.
"""
from collections import Counter, defaultdict, deque
from itertools import permutations, product

N = 3
BOT = 3
ALL = (1 << N) - 1
TOTAL = (N + 1) ** (N * N)


def decode(code):
    out = []
    for _ in range(N * N):
        out.append(code % (N + 1))
        code //= N + 1
    return out


def f(t, x, a):
    return t[x * N + a]


def weak_assoc(t):
    """If both bracketings are defined, their values must agree."""
    for x, y, z in product(range(N), repeat=3):
        xy, yz = f(t, x, y), f(t, y, z)
        left = BOT if xy == BOT else f(t, xy, z)
        right = BOT if yz == BOT else f(t, x, yz)
        if left != BOT and right != BOT and left != right:
            return False
    return True


def strict_v2_assoc(t):
    """Associativity after adjoining an absorbing undefined element BOT."""
    for x, y, z in product(range(N), repeat=3):
        xy, yz = f(t, x, y), f(t, y, z)
        left = BOT if xy == BOT else f(t, xy, z)
        right = BOT if yz == BOT else f(t, x, yz)
        if left != right:
            return False
    return True


def has_full_three_step_cycle(t):
    """Three distinct states and three distinct accesses form a 3-cycle."""
    for xs in permutations(range(N)):
        for aa in permutations(range(N)):
            if (f(t, xs[0], aa[0]) == xs[1]
                and f(t, xs[1], aa[1]) == xs[2]
                and f(t, xs[2], aa[2]) == xs[0]):
                return True
    return False


def strongly_connected_all_vertices(t):
    """Directed graph x -> x⊗a for each a with a defined product."""
    graph = [[f(t, x, a) for a in range(N) if f(t, x, a) != BOT]
             for x in range(N)]
    for start in range(N):
        reached, stack = {start}, [start]
        while stack:
            u = stack.pop()
            for v in graph[u]:
                if v not in reached:
                    reached.add(v)
                    stack.append(v)
        if len(reached) != N:
            return False
    return True


def fixed_access_orbit(t, x0, a):
    """Run T_a(x)=x⊗a until first repeated state or undefined edge.

    'Visits all' counts three distinct visited states even when the next
    application is undefined. 'Closed 3-cycle' additionally requires return
    to x0 after the three distinct states.
    """
    x, seen = x0, []
    while x not in seen:
        seen.append(x)
        y = f(t, x, a)
        if y == BOT:
            return len(seen) == N, False
        x = y
    visits_all = len(seen) == N
    closed3 = visits_all and x == x0
    return visits_all, closed3


def one_role_seed(t, x0):
    """One token is both pointer and, when a=x, access.

    q is the pool apart from current pointer. On use of a:
        q' = q + e_a, x' = x⊗a.
    Success: return to x0, all three access types have been used/retained.
    """
    start = (x0, 0, 0)  # pointer, q-support mask, used-access mask
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        (x, qmask, used), depth = queue.popleft()
        if depth > 0 and x == x0 and qmask == ALL and used == ALL:
            return depth
        available = qmask | (1 << x)  # current pointer may double as access
        for a in range(N):
            if not (available & (1 << a)):
                continue
            r = f(t, x, a)
            if r == BOT:
                continue
            nxt = (r, qmask | (1 << a), used | (1 << a))
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    return None


def two_role_copy_tool_seed(t, x0, a0):
    """Two separate roles; reaction x+a -> r+2a; q-support cannot expand."""
    start = (x0, 1 << a0, 0)
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        (x, qmask, used), depth = queue.popleft()
        if depth > 0 and x == x0 and qmask == ALL and used == ALL:
            return depth
        for a in range(N):
            if not (qmask & (1 << a)):
                continue
            r = f(t, x, a)
            if r == BOT:
                continue
            nxt = (r, qmask, used | (1 << a))
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    return None


def two_role_copy_result_seed(t, x0, a0):
    """Two separate roles; reaction x+a -> 2r+a; q' = q+e_r."""
    start = (x0, 1 << a0, 0)
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        (x, qmask, used), depth = queue.popleft()
        if depth > 0 and x == x0 and qmask == ALL and used == ALL:
            return depth
        for a in range(N):
            if not (qmask & (1 << a)):
                continue
            r = f(t, x, a)
            if r == BOT:
                continue
            nxt = (r, qmask | (1 << r), used | (1 << a))
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    return None


counts = Counter()
# Store exact selected classes as integer table codes for seed passes.
weak_cycle_codes, strict_codes, strict_scc_codes = [], [], []
# Orbit counters: table counts and ordered (x0,a) counts.
orbit = defaultdict(lambda: [set(), 0, set(), 0])
# Seed counters: successful ordered seeds and distinct successful tables.
seed = defaultdict(lambda: [0, set(), Counter()])

for code in range(TOTAL):
    t = decode(code)
    w = weak_assoc(t)
    s = strict_v2_assoc(t)
    cyc = has_full_three_step_cycle(t)
    scc = strongly_connected_all_vertices(t)

    counts['weak'] += w
    counts['strict'] += s
    counts['full3'] += cyc
    counts['weak_full3'] += (w and cyc)
    counts['strict_full3'] += (s and cyc)
    counts['scc_all3'] += scc
    counts['strict_scc_all3'] += (s and scc)

    if w and cyc:
        weak_cycle_codes.append((code, t))
    if s:
        strict_codes.append((code, t))
    if s and scc:
        strict_scc_codes.append((code, t))

    # The orbit counts requested in the discussion.
    classes = []
    if w and cyc:
        classes.append('weak_full3')
    if s:
        classes.append('strict')
    if s and scc:
        classes.append('strict_scc_all3')
    for x0, a in product(range(N), repeat=2):
        visits_all, closed3 = fixed_access_orbit(t, x0, a)
        for cl in classes:
            if visits_all:
                orbit[cl][0].add(code)
                orbit[cl][1] += 1
            if closed3:
                orbit[cl][2].add(code)
                orbit[cl][3] += 1

# Seed search in the specified table classes.
for code, t in weak_cycle_codes:
    for x0 in range(N):
        d = one_role_seed(t, x0)
        if d is not None:
            seed['one_role_weak_full3'][0] += 1
            seed['one_role_weak_full3'][1].add(code)
            seed['one_role_weak_full3'][2][d] += 1
    for x0, a0 in product(range(N), repeat=2):
        d = two_role_copy_result_seed(t, x0, a0)
        if d is not None:
            seed['v2_weak_full3'][0] += 1
            seed['v2_weak_full3'][1].add(code)
            seed['v2_weak_full3'][2][d] += 1

for code, t in strict_codes:
    for x0 in range(N):
        d = one_role_seed(t, x0)
        if d is not None:
            seed['one_role_strict'][0] += 1
            seed['one_role_strict'][1].add(code)
            seed['one_role_strict'][2][d] += 1
    for x0, a0 in product(range(N), repeat=2):
        d = two_role_copy_tool_seed(t, x0, a0)
        if d is not None:
            seed['v1_strict'][0] += 1
            seed['v1_strict'][1].add(code)
            seed['v1_strict'][2][d] += 1
        d = two_role_copy_result_seed(t, x0, a0)
        if d is not None:
            seed['v2_strict'][0] += 1
            seed['v2_strict'][1].add(code)
            seed['v2_strict'][2][d] += 1

for code, t in strict_scc_codes:
    for x0, a0 in product(range(N), repeat=2):
        d = two_role_copy_result_seed(t, x0, a0)
        if d is not None:
            seed['v2_strict_scc_all3'][0] += 1
            seed['v2_strict_scc_all3'][1].add(code)
            seed['v2_strict_scc_all3'][2][d] += 1

print('STATIC COUNTS')
for k in ['weak', 'strict', 'full3', 'weak_full3', 'strict_full3', 'scc_all3', 'strict_scc_all3']:
    print(f'{k}: {counts[k]}')

print('\nFIXED-ACCESS ORBITS: visit all 3 before repeat/undefined; closed 3-cycle')
for cl in ['weak_full3', 'strict', 'strict_scc_all3']:
    tab, pairs_count, cyc_tabs, cyc_pairs = orbit[cl]
    print(f'{cl}: visits_all={len(tab)} tables/{pairs_count} ordered pairs; '
          f'closed3={len(cyc_tabs)} tables/{cyc_pairs} ordered pairs')

print('\nSEED SEARCH: success means return to x0, all 3 carrier types present, all 3 access types used')
for k in ['one_role_weak_full3', 'one_role_strict', 'v1_strict', 'v2_weak_full3', 'v2_strict', 'v2_strict_scc_all3']:
    num, tabs, lens = seed[k]
    print(f'{k}: {num} successful seeds / {len(tabs)} tables; shortest-length histogram={dict(sorted(lens.items()))}')
