# Independent technical review: temporal observability and access-seed semantics

User instruction (Russian): «С токенами, рангами и циклами дружит Копилот.
Сформулируй текущие вопросы и запроси у Копилота.»

Repository: IgorSabirov/vm-lab (private; user explicitly authorizes this review).
Source commit: 0b536c51dbef17f0fd0c92f7aae3ab679ad6279c.
Revision 2 incorporates the user's new peer attachment of 5 November 2026
(uploaded filename Вставленный текст(20261105-155743).txt) before actual sending.
The relevant definitions and claims are included below. Do not assume access
to the repository, conversation, external files, or a running VM.

Please answer in Russian. Independently check the mathematical claims; do not
agree with either our conclusions or the neighboring reviewers by default.
For each question give: confirmed / corrected / refuted / underdetermined;
then a short derivation or explicit counterexample and exact assumptions.
Prioritize Q1, Q2, Q4. Q3 is a supporting algebra check. Q5 concerns a proposed
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
Success means x_final=s, every label has been used, and c_b>=1 for all b.

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

Check these results analytically. Do not claim independent confirmation
of unrelated census totals such as 442 strict tables or 56 successful weak
tables: the peers' code/logs were not provided. Explain any overlooked
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
Recommend at most one minimal verification target that addresses the link
between generated access, independent distinctions, and continued ability
to execute operations. First say whether the present definitions are
sufficient to pose that target. If a new physical assumption is required,
list it as a proposal, not as an adopted model component. No broad new
enumeration, no Monte Carlo, no origin-of-probability claim from an input
death probability lambda, and no inference of an arrow solely from a cycle.

Please close with a compact list: what our previous review got right,
what it got wrong, and what cannot be answered from the supplied definitions.
