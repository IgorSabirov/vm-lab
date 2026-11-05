# Independent technical review: temporal observability and access-seed semantics

User instruction (Russian): «С токенами, рангами и циклами дружит Копилот.
Сформулируй текущие вопросы и запроси у Копилота.»

Repository: IgorSabirov/vm-lab (private; user explicitly authorizes this review).
Source commit: 0b536c51dbef17f0fd0c92f7aae3ab679ad6279c.
Revision 3 incorporates the user's latest peer report and the complete attached
verify_composition_seed.py (272 lines, 9112 bytes), reproduced in the appendix.
It supersedes revision 2, which was prepared but never sent to Copilot.
The relevant definitions and claims are included below. Do not assume access
to the repository, conversation, external files, or a running VM.

Please answer in Russian. Independently check the mathematical claims; do not
agree with either our conclusions or the neighboring reviewers by default.
For each question give: confirmed / corrected / refuted / underdetermined;
then a short derivation or explicit counterexample and exact assumptions.
Prioritize Q0 (the latest code), Q1, Q2, Q4. Q3 is a supporting algebra check. Q5 concerns a proposed
verification method, not permission to run a new experiment. No tools or
numerical runs are requested. Do not claim to have enumerated tables or run
software. Pseudocode for a narrowly relevant verifier is welcome, if needed.
Do not introduce a new scientific architecture or choose the project's goal.

The scientific background is the origin and endogenous continuation of
organization. This is not a request to derive consciousness or time from
token counts. We want to separate: (i) observability/completeness of access,
(ii) physical availability of an operation, (iii) regeneration of that
availability. A fixed law is not an external physical controller. Our user
explicitly wants the principle behind the rank result, not numerology about 3.

## Q0. Latest peer code: exact finite abstraction and changed execution rules

The complete script is appended as source for inspection, NOT for execution.
We have read it but have NOT independently rerun its census. Distinguish a
correct enumeration algorithm from independently reproduced numerical output.

All models track a pointer x and a reserve q of separate tokens excluding
that pointer. Let r=f(x,a), U be the set of used access labels. Each event
also updates U'=U union {a}. These are three DIFFERENT execution rules:

A (one-role aliasing): start x=s,q=0; guard a in supp(q) union {x};
  x'=r, q'=q+e_a.
B / peer V1 (two distinct participants, copy instrument): start x=s,q=e_a0;
  guard q_a>=1; x+a -> r+2a; x'=r, q'=q+e_a.
C / peer V2 (two distinct participants, COPY RESULT): start x=s,q=e_a0;
  guard q_a>=1; x+a -> 2r+a; x'=r, q'=q+e_r.

C is NOT the diagnostic POINTER REASSIGNMENT variant in Q2 below: that
variant keeps x+a->r+2a but sets x'=a. The two have the same reserve
increment q'=q+e_r and different pointer updates. Do not conflate them.

Latest success: after a positive number of steps x=s, supp(q)=X and U=X.
For A there are 3 possible seeds per table; for B/C there are 9 ordered
(s,a0) seeds per table, including distinct initial types. Absolute success
counts are therefore not a controlled comparison from identical seeds.

Reported static totals among all 4^9=262144 labeled partial tables:
weak associative 31789; strict 442; full3 43526; weak AND full3 635;
strict AND full3 1; SCC-all 114968; strict AND SCC-all 4.
full3 means 3 distinct pointer states AND 3 distinct access labels in a
closed 3-step path. SCC means x->f(x,a) for any defined a, as in the code.
The old 208472 SCC number is withdrawn for this predicate.

Reported fixed-a orbits, visit all states before first repeat/undefined:
weak+full3: 264 tables / 276 ordered (x0,a) pairs;
all strict: 51 tables / 72 pairs.
Closed fixed-a 3-cycles: weak+full3 0/0; strict 3 tables / 18 pairs.
Do not confuse visiting the third state with having a defined next step.

Reported successful seeds / tables:
  A weak+full3 96/56; A strict 6/3; B strict 0/0;
  C weak+full3 576/225; C strict 48/21; C strict+SCC-all 24/3.
Reported shortest-path histograms (length: number of successful seeds):
  A weak: 3:60,4:24,5:6,6:6; A strict: 5:6;
  C weak: 3:72,4:66,5:294,6:132,7:12;
  C strict: 3:12,4:12,5:18,6:6.

Please inspect the code and answer:
0a. Is (x,supp(q),U) an EXACT finite reachability abstraction for these
    guards, updates and goal, not a heuristic count truncation? There are
    at most 3*8*8=192 abstract states per fixed seed and table. Every guard
    only tests support, q never decreases, and abstract successors depend
    only on this triple. Prove soundness/completeness by lifting paths,
    or give a counterexample. Does BFS then give exact minimum event count,
    with no depth/population cap and no need for Karp--Miller here?
0b. Does the code implement the stated classes, seeds, goals and transitions?
    Check absorbing BOT, strict vs weak associativity, deduplication of
    tables vs ordered seeds, closed-orbit test, positive-length requirement.
    A script implementing the claims does not itself authenticate the
    reported numbers: identify the evidence boundary precisely.
0c. Is supp(q)=X redundant once U=X in all three models, for different
    reasons (A adds every used label; B/C use only already present labels
    and never remove them)? Does this also explain why the earlier goal
    using full c rather than q does not change successful paths here?
0d. Verify B's support invariant for arbitrary initial q and C's ability to
    diversify. In f=x+a+2 mod3, C starting x=0,q=e_0 has the valid accesses
    [0,0,1,2,2], pointer states [0,2,1,1,2,0]. Is this valid? What is assumed
    by duplication and what follows from the algebra?
0e. Why does the A proof 'success => pointer visited all types => SCC-all'
    NOT automatically apply to C with a separate arbitrary a0 seed? If
    possible give an explicit strictly associative NON-SCC-all table and
    successful C seed/path analytically, without enumeration. This would
    explain why 21 successful strict tables need not contradict the 4-table
    SCC classification. Keep the reported exact total 21 unverified unless
    it is independently derived. Distinguish initially supplied access
    type from a type actually produced by a pointer result.
0f. Is there any remaining unbounded-token/aliasing issue for THIS quotient,
    or does it arise only if one adds consumption, thresholds, finite
    resources, or a token-sensitive success criterion?

The last peer conclusion asks whether physical organization can implement C
without its rule being inserted into execution semantics. Separate two
questions: deriving an effective token rule from an explicitly specified
microscopic model versus deriving that microscopic model/its laws from no
assumptions. A fixed microscopic law does not exclude internal production.
No corrective role ('type 2'), probability measure, time arrow or subject
has yet been established by these reachability results.

## Q1. Check the exact small-time full-rank statement

Tensor order S,M,R, each a qubit, hbar=1, standard Pauli XY=iZ, g>0,
epsilon real, g*epsilon != 0. Hamiltonian:

H_epsilon = g P_1^S (X_M + X_R) + epsilon Z_R.

Let Omega=sqrt(g^2+epsilon^2), U0=exp(-i epsilon t Z),
U1=exp[-it(gX+epsilon Z)], uM=exp(-igtX_M). In S blocks,
U=diag(I_M tensor U0, uM tensor U1). Define

W=U0^dagger U1 = aI - i bx X + i by Y + i bz Z,

a=cos(epsilon*t)cos(Omega*t)
  +(epsilon/Omega)sin(epsilon*t)sin(Omega*t),
bx=(g/Omega)cos(epsilon*t)sin(Omega*t),
by=(g/Omega)sin(epsilon*t)sin(Omega*t),
bz=sin(epsilon*t)cos(Omega*t)
  -(epsilon/Omega)cos(epsilon*t)sin(Omega*t),
v(t)=(bx,-by,-bz).

We use 16 linearly independent rank-one projectors P_y=|y><y| spanning
Herm(4) on SM. For each y, a separate preparation/trial uses the instrument
K_y=|x><y| with |x>=|+>_S|0>_M and failure K_f=I-P_y. After success, evolve
for t, then measure the fixed O=X_S X_M (outcomes +/-1). Record success
and failure probabilities on all trials, not only normalized postselection.
Each copy receives one filter and one final readout; this is not sequential
tomography of the same unknown single copy. The unknown normalized input
state rho is arbitrary 8x8 and identical across preparations.

Claimed effective success observable:
K_y^dagger U^dagger O U K_y = -sin(gt) P_y tensor [v(t).sigma_R].

Claimed small-time terms:
bx=gt+O(t^3), by=g*epsilon*t^2+O(t^4),
bz=-epsilon*g^2*t^3/3+O(t^5).

At t_k=k h, k=1,2,3, h>0 sufficiently small:
det[v(kh)^T] = -4*g^4*epsilon^2*h^6 + O(h^8),
det[-sin(gkh)v(kh)^T] = 24*g^7*epsilon^2*h^9 + O(h^11).

This is claimed to supply three independent R directions; together with
q_y=Tr[rho(P_y tensor I)], the outcome map determines all 63 real
parameters of normalized rho. A grid including t=pi/g instead has a zero
fixed-readout row and, with only three time choices, at most 47 parameters.

Questions: are the effective observable, determinant coefficients/orders,
and full-rank inference correct? Identify any hidden assumptions. Explain
why arbitrarily short positive horizons can give exact full rank while
becoming badly conditioned, and why this is not a universal claim that any
three times or just free evolution without the filters give full rank.
If useful, characterize the leading small-h singular-value scales for this
3x3 matrix under fixed nonzero g,epsilon, without pretending an SVD threshold
proves exact rank.

## Q2. Does a single seed actually launch the token model?

Let X be a finite set with a partial binary operation f(x,a)=x tensor a.
A marked current pointer x is one of the tokens counted in c in N^X.
M is a bookkeeping set of labels already used. Initially:
W0=(s,e_s,empty).

The peers' rule (A), permitting the pointer token to serve as its own access,
uses guard c_a>=1 and f(x,a) defined, then sets

r=f(x,a),  W'=(r, c-e_x+e_r+e_a, M union {a}).

The invariant c_x>=1 is supposed to be guaranteed by initialization/update.
The earlier success meant x_final=s, every label used, and c_b>=1 for all b;
Q0 records the latest reserve-based goal and asks whether it is equivalent.

The peers also interpret this as a two-participant reaction
x+a -> r+2a. Under that interpretation, if participants must be distinct
physical tokens, the enabling condition is instead rule (B):
c >= e_x+e_a componentwise (so c_x>=2 when x=a), with the same update.

Our claims to check:
1. Under A the explicit paths below are valid and repeatable; reproduction
   is an input in +e_a. Total population increases by exactly one on every
   event, regardless of the table or existence of a cycle.
2. On any closed pointer path, telescoping gives Delta c=sum_i e_{a_i}.
3. A allows one token in both roles. This is a legitimate abstract unary
   self-application/generation rule, but is not implied by B's two-token
   reaction. Equal stoichiometric increments do not imply equal guards.
4. Under B a one-token seed has no first event. More strongly, with exactly
   one marked pointer involved in every event and a homogeneous seed
   c=n e_s, x=s (any n>=1), all reachable populations obey
   c=m e_s+e_x, m>=0. Therefore only label s can ever be used as an access:
   if x!=s, its unique token cannot also be the distinct access; if x=s,
   no other types exist. An event with a=s changes the invariant to
   (m+1)e_s+e_r. Thus simply adding more tokens of s cannot satisfy success
   requiring all access labels. This claim is restricted to this marked-
   pointer event model, not arbitrary chemical reaction networks.

Are these claims correct? Give the smallest counterexample if not. Clearly
distinguish explicit self-application from an unnoticed change of semantics.
Does a Petri-net/coverability implementation need separate preconditions
even when update vectors coincide? State what must be encoded, without
certifying an unavailable implementation of Karp--Miller.

NEW GENERALIZATION FROM THE FOLLOW-UP (please prioritize this): define the
reserve of separate access tokens q=c-e_x. Under B, the guard is q_a>=1,
and because the output pointer is always r, q'=q+e_a. Therefore supp(q')=
supp(q) for ANY initial reserve, not just a homogeneous seed, and for any
partial/total table of any cardinality. Under A a previously absent reserve
type can appear only by a=x with q_x=0: q'=q+e_x. Thus role aliasing enables
reserve diversification, but is NOT necessary for positive growth of already
present reserve types. Check this stronger invariant and its exact scope.

The neighbors' final prose suggests that avoiding this obstruction requires
either aliasing or copying the result into another access token. Is that
list exhaustive? As a diagnostic counterexample, NOT an adopted model,
keep two distinct participants, the same guard and population update, but
designate a surviving a-token as the NEW POINTER instead: x'=a, not r.
Then q'=q+e_r and a new result type can enter the reserve without a second
copy of r. This changes the role-assignment rule; it does not follow from B.
For f=x+a-1 mod 3 and start x=0,c=(2,0,0), check this proposed path:
  access 0, r=2, new pointer 0, c=(2,0,1);
  access 2, r=1, new pointer 2, c=(1,1,2);
  access 1, r=2, new pointer 1, c=(1,2,2);
  access 0, r=0, new pointer 0, c=(3,1,2).
Each event should have two distinct available participants, all labels are
used, and the pointer returns. Does this show that the obstruction depends
on where the result is assigned, not merely on having two distinct roles?
Explicitly state the additional role reassignment assumption and do not
promote this example to a derived physical mechanism.

Explicit A witness 1, X={0,1,2}, rows x, columns a, '-' undefined:
  [ 1, -, - ]
  [ -, 2, 0 ]
  [ -, 0, 0 ]
Pointer 0 --0--> 1 --1--> 2 --2--> 0.
c: (1,0,0) -> (1,1,0) -> (1,1,1) -> (2,1,1).
The table is claimed weakly associative, not strictly associative.

Explicit A witness 2, f(x,a)=x+a-1 mod 3:
  [ 2, 0, 1 ]
  [ 0, 1, 2 ]
  [ 1, 2, 0 ]
Pointer 0 --0--> 2 --2--> 0 --2--> 1 --1--> 1 --0--> 0.
c: (1,0,0) -> (1,0,1) -> (2,0,1) -> (1,1,2)
   -> (1,2,2) -> (3,1,2).

## Q3. Independently check the strict algebra classification

Strict partial associativity means (x tensor a) tensor b and
x tensor (a tensor b) have identical definedness, and equal values when
defined. The directed graph has edges x -> f(x,a) for every defined pair.
Weak associativity only compares values when both bracketings exist.

We claim that on three labeled elements, strict associativity plus full
strong connectivity leaves exactly four tables: right projection f(x,a)=a,
and the three labeled cyclic-group laws f(x,a)=x+a+k mod 3, k=0,1,2.

Proof sketch to scrutinize:
- Strict associativity collapses every nonempty path to x tensor a=y.
  Strong connectivity includes a nonempty self-return path. Thus every
  row covers all X, hence every row is a total permutation L_x of X.
- L_x L_y=L_{f(x,y)}. The finite image H={L_x} in Sym(X) is a group.
- Fibers of x -> L_x have equal sizes: each permutation L_z of X maps
  the fiber over h bijectively to that over L_z h. Hence |H| divides 3.
- |H|=1 yields L_x=identity and right projection; |H|=3 yields Z3.

A closed three-step path with pairwise distinct pointer states and pairwise
distinct access labels is possible only for right projection. In a group,
one of the three labels is the identity and forces a stationary step.
Allowing a longer closed path gives all four tables. Under rule A and the
one-token seed success criterion Q2, only the three groups work, with two
nonidentity seeds each. An identity seed or a projection seed cannot
produce new types. Five steps are claimed necessary and sufficient for
group success (the supplied path is one witness).

Check these results analytically. Do not claim independent reproduction
of census totals merely from reading the now-supplied source code. Explain any overlooked
case, especially whether the successful-seed criterion really forces the
pointer path to visit all types and hence full strong connectivity.

## Q4. The actual bridge to the temporal rank result

The old table-ready observable is
R(x)=({a:f(x,a) defined},{a:f(a,x) defined}).
Full composition profile P(x) records both rows/columns including result
labels and undefinedness; D(x,y) iff P(x)!=P(y). An older, different
definition called a an 'active access' if for some pair defined under a,
D(x,y) != D(f(x,a),f(y,a)). These definitions must not be silently swapped
with 'a token is present and therefore executable'.

In the cyclic-group witness R(x)=(X,X) for every x and stays constant along
all pointer paths. Group translations also preserve full D. Therefore
readiness-only observation cannot become informative through repetition,
although token populations increase under A. Observation of c or of which
tokens are presently available would be a different specified output map.

Please determine precisely what is and is not comparable to Q1. Is the
proper finite-state analog separation of equivalence classes by output
histories under an explicitly defined family of executable operation words,
rather than merely reachability or counts of instruments? When availability
itself depends on W, how must undefined/disabled experiments be handled
without silently granting an external scheduler or unavailable operations?

We do not want an artificially injective readout such as 'observe the entire
state label': that would assume the access being investigated. With only
the supplied definitions, can an endogenous separating readout be derived,
or is an output/record relation genuinely missing? Name the exact missing
specification, if any. Distinguish 'two histories can be told apart by us'
from 'the modeled system has a process producing different internal records'.
Do not conclude that a static law prevents endogenous regulation or records.

FOLLOW-UP CLARIFICATION: repertoire growth is NOT required for temporal
observability. One fixed map T_a and one fixed noninjective readout O may
have an injective history J_a(x)=(O(x),O(T_a x),O(T_a^2 x),...). In the group
example choose a=2, so T_a(x)=x+1 mod 3. If O(x)=1 for x=0 and 0 otherwise,
the three initial states give histories (1,0,0), (0,0,1), (0,1,0). This is
an explicit conditional analogy with Q1; the binary readout O has been
ADDED and its internal realization is not supplied by the group table.
Check this analogy and separate it from the constant-readiness counterexample.
In the peer equation intersection_{k=1}^3 ker(O_kh)={0} for the full quantum
state, each O_kh must mean the full vector of all filter outcomes (including
success information), not one scalar observation: is that qualification
essential? Do not interpret the numeral 3 as a common universal minimum.

## Q5. Which remaining question is worth checking, and how narrowly?

The peers propose comparing, on the same tables, copying x+a->r+2a,
conservative x+a->r+a, and consuming x+a->r. Under conservative population
update c'=c-e_x+e_r, total population stays one from a one-token start, so
simultaneous presence of all three types is impossible by counting alone.
With A-style role aliasing it may still sequentially visit all types.
The consuming rule needs its own explicit guard and update when x=a.

Do these comparisons discover a nontrivial mechanism, or merely distinguish
population balances already imposed by the rules under that success test?
With the new Q0 code included, recommend at most one minimal verification target that addresses the link
between generated access, independent distinctions, and continued ability
to execute operations. First say whether the present definitions are
sufficient to pose that target. If a new physical assumption is required,
list it as a proposal, not as an adopted model component. No broad new
enumeration, no Monte Carlo, no origin-of-probability claim from an input
death probability lambda, and no inference of an arrow solely from a cycle.

Please close with a compact list: what our previous review got right,
what it got wrong, and what cannot be answered from the supplied definitions.


## Appendix: complete supplied source (read only; do not execute)

```python
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
```
