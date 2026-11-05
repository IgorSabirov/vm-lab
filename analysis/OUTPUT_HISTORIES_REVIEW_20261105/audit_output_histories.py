#!/usr/bin/env python3
"""Exact n=3 audit of composition tables, seed semantics, and binary output histories.

Definitions:
- X={0,1,2}; each table cell is one of {-1,0,1,2}, where -1 is undefined.
- weak associativity: if both bracketings are defined, their values agree.
- strict_v2 associativity: extend undefined bottom as absorbing and require
  ordinary associativity on X union {bottom}.
- full_3_cycle: three pairwise-distinct states and three pairwise-distinct
  access labels realize x0 --a0--> x1 --a1--> x2 --a2--> x0.
- A: one-role seed (x, empty reserve); actions Q union {x}; reserve gains used access.
- V1: two-role seed (x, {a}); actions Q; reserve gains used access.
- V2: two-role seed (x, {a}); actions Q; reserve gains result r.
- A successful seed returns to its initial pointer and has used all 3 labels.
- V1/V2 successful seed uses same goal. V1 is impossible from a one-label reserve.
- Output-history test is explicitly POST-BOOTSTRAP: after a successful cycle,
  reserve Q=X. We observe O(x) at each state. An action label is a common
  experiment only if it is executable from both states; failure/refusal is
  NOT treated as an observation. Two pointer states are distinguishable iff
  some common finite action word gives different output traces.
- The history test is on pointer states x, not full organization states (x,Q).
"""

from itertools import product, permutations
from collections import deque, Counter

N = 3
BOTTOM = -1
XALL = frozenset(range(N))
TABLES = product(range(BOTTOM, N), repeat=N*N)

def f(tab, x, a):
    return tab[x*N + a]

def weak_assoc(tab):
    for x, y, z in product(range(N), repeat=3):
        l = f(tab, x, y)
        if l != BOTTOM:
            l = f(tab, l, z)
        r = f(tab, y, z)
        if r != BOTTOM:
            r = f(tab, x, r)
        if l != BOTTOM and r != BOTTOM and l != r:
            return False
    return True

def strict_v2_assoc(tab):
    # Bottom is absorbing on either side.
    for x, y, z in product(range(N), repeat=3):
        l = f(tab, x, y)
        if l != BOTTOM:
            l = f(tab, l, z)
        r = f(tab, y, z)
        if r != BOTTOM:
            r = f(tab, x, r)
        if l != r:
            return False
    return True

def full_3_cycle(tab):
    for xs in permutations(range(N)):
        for aa in permutations(range(N)):
            if all(f(tab, xs[i], aa[i]) == xs[(i+1) % N]
                   for i in range(N)):
                return True
    return False

def scc_all3(tab):
    adj = {x: set() for x in range(N)}
    for x in range(N):
        for a in range(N):
            r = f(tab, x, a)
            if r != BOTTOM:
                adj[x].add(r)
    for start in range(N):
        seen = {start}
        todo = [start]
        while todo:
            x = todo.pop()
            for y in adj[x] - seen:
                seen.add(y)
                todo.append(y)
        if len(seen) != N:
            return False
    return True

def seed_list(sem):
    if sem == "A":
        return [(x, frozenset()) for x in range(N)]
    if sem in ("V1", "V2"):
        return [(x, frozenset({a})) for x in range(N) for a in range(N)]
    raise ValueError(sem)

def successors(tab, sem, x, Q):
    if sem == "A":
        actions = set(Q) | {x}
    else:
        actions = set(Q)
    for a in sorted(actions):
        r = f(tab, x, a)
        if r == BOTTOM:
            continue
        if sem == "A":
            Q2 = frozenset(set(Q) | {a})
        elif sem == "V1":
            Q2 = Q
        elif sem == "V2":
            Q2 = frozenset(set(Q) | {r})
        yield a, r, Q2

def shortest_success(tab, sem, x0, Q0):
    start = (x0, Q0, frozenset())
    q = deque([(start, 0)])
    seen = {start}
    while q:
        (x, Q, U), d = q.popleft()
        if x == x0 and U == XALL:
            return d
        for a, r, Q2 in successors(tab, sem, x, Q):
            st = (r, Q2, U | {a})
            if st not in seen:
                seen.add(st)
                q.append((st, d+1))
    return None

def reachable_pointer_states_after_bootstrap(tab, x0):
    # Once Q=X, all labels are available and Q remains X in A and V2.
    seen = {x0}
    q = deque([x0])
    while q:
        x = q.popleft()
        for a in range(N):
            r = f(tab, x, a)
            if r != BOTTOM and r not in seen:
                seen.add(r)
                q.append(r)
    return seen

def history_injective(tab, O, start_x):
    """Injectivity on pointer states reachable after bootstrap.

    Pair (x,y) is distinguished if current O differs, or some action
    executable from both takes the pair to an already distinguished pair.
    """
    reachable = sorted(reachable_pointer_states_after_bootstrap(tab, start_x))
    pairs = [(reachable[i], reachable[j])
             for i in range(len(reachable))
             for j in range(i+1, len(reachable))]
    distinguished = {(x,y) for x,y in pairs if O[x] != O[y]}
    changed = True
    while changed:
        changed = False
        for x,y in pairs:
            if (x,y) in distinguished:
                continue
            for a in range(N):
                rx, ry = f(tab,x,a), f(tab,y,a)
                # Same action word must be executable from both.
                if rx == BOTTOM or ry == BOTTOM or rx == ry:
                    continue
                pair = (min(rx,ry), max(rx,ry))
                if pair in distinguished:
                    distinguished.add((x,y))
                    changed = True
                    break
    return len(distinguished) == len(pairs), len(reachable)

def enumerate_successful_seeds(tab, sem):
    out = []
    for x0, Q0 in seed_list(sem):
        d = shortest_success(tab, sem, x0, Q0)
        if d is not None:
            out.append((x0, Q0, d))
    return out

def main():
    all_tabs = list(TABLES)
    weak = [t for t in all_tabs if weak_assoc(t)]
    strict = [t for t in all_tabs if strict_v2_assoc(t)]
    weak_cycle = [t for t in weak if full_3_cycle(t)]
    strict_cycle = [t for t in strict if full_3_cycle(t)]
    strict_scc = [t for t in strict if scc_all3(t)]

    print("STATIC")
    print("all", len(all_tabs), "weak", len(weak), "strict_v2", len(strict))
    print("weak_cycle", len(weak_cycle), "strict_cycle", len(strict_cycle),
          "global_scc3", sum(1 for t in all_tabs if scc_all3(t)),
          "strict_scc3", len(strict_scc))

    Os = list(product((0,1), repeat=N))
    for sem, tabs in (
        ("A", weak_cycle),
        ("A", strict),
        ("V1", strict),
        ("V2", weak_cycle),
        ("V2", strict),
    ):
        total_seeds = 0
        table_count = 0
        hist = Counter()
        table_O = set()
        table_union = set()
        seed_O = 0
        per_O = Counter()
        for ti, tab in enumerate(tabs):
            ss = enumerate_successful_seeds(tab, sem)
            if not ss:
                continue
            table_count += 1
            total_seeds += len(ss)
            hist.update(d for _,_,d in ss)
            for O in Os:
                passing = []
                for x0, Q0, d in ss:
                    ok, nreach = history_injective(tab, O, x0)
                    if ok:
                        passing.append((x0,Q0,d,nreach))
                if passing:
                    table_O.add((ti,O))
                    table_union.add(ti)
                    seed_O += len(passing)
                    per_O[O] += 1
        print(sem, "candidate_tables",len(tabs),
              "successful_tables",table_count,
              "successful_seeds",total_seeds,
              "length_hist",dict(sorted(hist.items())))
        print("  output_history: tables_with_any_O",len(table_union),
              "table_O_pairs",len(table_O),
              "seed_O_passes",seed_O,
              "per_O",dict(sorted(per_O.items())))

if __name__ == "__main__":
    main()
