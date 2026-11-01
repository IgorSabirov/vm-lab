# Mathematical audit: can a closed system have an endogenous arrow without an internal organizer?

Date: 2026-11-01. Project source snapshot: IgorSabirov/vm-lab @ afb05513d7c5a0e87d5321dda0ab9ca396254d91.
The user explicitly requests this mathematical consultation. You are a critical mathematical reviewer, not an advocate for a preferred answer. Reply in Russian, with precise statements and proofs/counterexamples. No tools, repository access or browsing are available in this request. Do not invent checked literature or arXiv IDs. New references, if any, must be marked UNVERIFIED.

## Research question and non-negotiable distinctions

We originally tried to obtain an arrow of time from minimal assumptions in closed autonomous systems. Our finite numerical searches did not establish an arrow robust to the chosen controls. That is a negative result in tested model classes, NOT a universal impossibility theorem. We now want either a rigorous no-go theorem in an explicit class, or a counterexample establishing possibility in that same class.

Working hypothesis under discussion: asymmetric initial/final conditions may describe the effective action of an internal organizing structure, instead of explaining where that structure comes from. This is a hypothesis to assess, NOT an assumption to put into the proof. We do not infer a physical organizer merely from the need to specify a mathematical model.

Three proposed regimes: A, no distinct internal functional organizer; B, an internal organizer without mutual maintenance; C, an organizer participating in a mutually sustaining coupling with the organized degrees of freedom. The last phrases are not yet mathematical predicates. We must not define A as 'no laws, no state space, no probability measure': that would make it empty by definition. All laws and all components of an organizer, if present, must belong to the closed whole. No externally timed intervention, reset, measurement selection or noise source is allowed unless explicitly included in that whole. 'Closed' by itself does not imply finite dimension, time-reversal invariance, a stationary ensemble or a particular thermodynamic entropy.

Here 'organizer' must not be confused with the mathematical generator H of time evolution. A nonzero H is not automatically the functional organizer whose necessity we want to test. The objective is a conditional scientific result, not a cosmological or consciousness claim.

Please distinguish four targets throughout:
(a) change/evolution at all;
(b) a continuous state function that increases forever;
(c) a finite epoch of increasing subsystem/coarse-grained entropy;
(d) internally consistent records/causal orientation within individual histories, including equally probable opposite orientations.
Entropy growth alone is not automatically an adequate operational definition of (d). No preferred external '+' direction should be smuggled into a test of internally oriented histories.

## Q1. Finite-dimensional no-go: exact scope and proof

Let H=H† on C^d, d<infinity, independent of t, rho(t)=exp(-iHt)rho0 exp(iHt). Candidate lemma: if F on density matrices is continuous in trace norm and F(rho(t)) is nondecreasing for every t>=0 along this one orbit, then F(rho(t)) is constant on that orbit. Proposed proof: there exist t_n -> infinity with rho(t_n) -> rho0, and for fixed t>=0, F(rho0)<=F(rho(t))<=F(rho(t_n)) for all sufficiently large n.

Prove or correct this, including recurrence assumptions and any exceptional cases. Does F(rho)=S(Tr_E rho) for a fixed finite tensor factor satisfy the hypotheses? Does time-reversal invariance of H play any role? Can adding a finite autonomous internal controller/organizer evade the conclusion for the full system or any continuous function of its reduced state? Distinguish fine-grained von Neumann entropy conservation from this stronger recurrence statement.

For contrast, explicitly assess H=g X tensor X, g>0, initial |00>, hbar=1. Its state is cos(gt)|00>-i sin(gt)|11>. The one-qubit entropy is h_2(sin^2(gt)). Is this a valid closed autonomous example of finite-epoch entropy increase, with a specified low-entanglement preparation, but not an explanation of that preparation? What overly broad no-go claims does it refute, and what does it leave untouched?

## Q2. Invariant-measure lemma, including infinite systems

Let (X,Sigma,mu) be a probability space and T_t a measurable measure-preserving flow. Let F:X->R be measurable and finite mu-almost surely. Suppose there is a common mu-full set on which the entire path t -> F(T_t x), t>=0, is nondecreasing. Candidate conclusion: for mu-almost every x, F(T_t x)=F(x) for every t>=0.

An L1 version follows by integrating nonnegative increments at rational times. Is integrability actually unnecessary, by applying a bounded strictly increasing transform such as arctan(F)? Does monotonicity of the whole path extend equality from rational to all real t without any extra orbit continuity? Please state the exact quantifiers and measurability assumptions. If the full-set/whole-path assumption is weakened, give the corrected version.

Explain what existence of a physically relevant invariant probability measure does and does not establish. A delta measure on a fixed point need not represent the initial states of interest; a quantum invariant state is not automatically a classical invariant probability measure on the chosen space of pure states. Absence of such a measure is not by itself a proof of monotone behavior or of an organizer. Are any of these cautions incorrect?

Test the noncompact example U_t psi(x)=psi(x-t) on L2(R), F(psi)=integral_0^infinity |psi(x)|^2 dx. Determine whether F(U_t psi) is monotone for every normalized psi, or only for a specially prepared ensemble. Identify explicitly the direction built into the dynamics/observable, the spectrum of its self-adjoint generator P, and why this does or does not count as a physical thermodynamic arrow. Do not silently assume that every infinite closed system falls under a finite invariant-measure recurrence argument.

## Q3. Time-symmetric path laws versus arrows within branches

Let Omega be a measurable space of histories on a symmetric time interval, Theta an involution reversing histories, and P a history law with Theta_*P=P. Let Gamma:Omega->Y be an observation map satisfying Gamma Theta = theta Gamma for an involution theta on Y. Then Q=Gamma_*P should satisfy theta_*Q=Q, and every integrable theta-odd J should have expectation zero.

Prove or correct this. In particular, does it prohibit arrow-bearing individual histories, or only a net signed ensemble orientation? Audit the example P=(P_plus + Theta_*P_plus)/2 when histories under P_plus possess a strong arrow. Could an internally defined orientation selector and records consistently label the two branches while preserving the symmetry of the unconditioned whole? What additional assumption would be required to turn the ensemble result into a no-go for branch-level emergence?

For nonsymmetric P, assess a possible 'asymmetry cannot be created by covariant observation' theorem:
D_KL(Gamma_*P || theta_*Gamma_*P) <= D_KL(P || Theta_*P).
State conditions, proof and limits (including infinite relative entropy, conditioning, and a covariant stochastic observation kernel). Would this be a rigorous bookkeeping statement about supplied asymmetry without claiming that the asymmetry must come from an external source or a distinct organizer?

## Q4. Can boundary conditions prove the necessity of an organizer?

The target we would LIKE to test is an implication of the form 'a closed whole displaying an endogenous operational arrow must contain an internal functional organizer M'. We do not know whether it is true. Please do not put the conclusion into the definitions.

Separate (i) boundary conditions sufficient to select arrow-bearing histories, (ii) a mechanism generating effective subsystem boundary conditions through dynamics of the same closed whole, and (iii) explaining all asymmetry of the entire whole without asymmetric law, boundary distribution, conditioning, observable or approximation. Are these genuinely different mathematical problems?

What minimal mathematical data are missing before the necessity implication can be proved or refuted? In particular, propose criteria for M that can be checked independently of whether an arrow was observed (e.g. explicit partition, reciprocal influence, an intervention predicate with a well-defined internal implementation). If no scientifically defensible minimal criterion follows from the information provided, say so instead of inventing one.

Can any theorem from Q1-Q3 distinguish A from B/C, if the latter remain in exactly the same finite closed autonomous class? If it also rules out B/C, it is not yet a theorem of 'A impossible, organizer necessary'. What extra assumption or weaker arrow criterion would make a genuine discriminator conceivable? Explain the risk of calling every interaction, boundary choice, or law an organizer.

## Q5. Adversarial review of the proposed next step

Several peer inferences need a direct TRUE / FALSE / NEEDS ASSUMPTIONS judgment, each with proof or a counterexample:
1. 'We failed to obtain an arrow in finite Hermitian models; therefore isolated systems cannot generate arrows.'
2. 'A time-reversal invariant history law means every individual history has no arrow.'
3. 'If an infinite system has no suitable invariant probability measure, an internal organizer is the only remaining way to obtain an arrow.'
4. 'Taking a subsystem automatically escapes any no-go for continuous state functions on the recurrent finite whole.'
5. 'Symmetrizing a trajectory ensemble and observing cancellation of an odd arrow marker proves that the original marker was an artifact.'
6. 'Autonomous internal control evades recurrence in a finite closed whole.'
7. 'Boundary conditions may encode an organizer's effective influence; therefore boundary conditions alone establish that such an organizer exists.'

End with ONE recommended next mathematical task, stated with class, quantifiers, observable/arrow predicate, and a clear proof-or-counterexample criterion. It should address the substantive open issue rather than merely rename a known entropy-invariance identity. If the honest next task is to specify M or a branch-level arrow predicate before attempting a necessity theorem, say precisely which ambiguity prevents the theorem today. No numerical campaign is requested.

## Output contract

Provide (1) a short verdict, (2) rigorous proofs/counterexamples for Q1-Q3, (3) the logical status of Q4 and the seven claims, (4) one concrete next target. Separate PROVED, COUNTEREXAMPLE, OPEN UNDER STATED ASSUMPTIONS, and UNDEFINED UNTIL SPECIFIED. Do not mistake agreement between language models for proof. We will independently audit your derivations.
