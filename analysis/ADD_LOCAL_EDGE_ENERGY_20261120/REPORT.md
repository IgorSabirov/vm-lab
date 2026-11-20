# ADD local directed edge-energy test (exploratory)

Date: 20 November 2026. This is a symbolic identifiability test, not physical acceptance of sector X.

## 1. ADD rule extracted from R130

The frozen R130 reference is `analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py`, with the rule summary in `analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/REPORT.md`.

For the one-channel C1 alphabet, interaction `I` simultaneously applies the local rewrite:

- split: `3 -> (1,2)`;
- merge: adjacent cyclic pair `(1,2) -> 3`.

The transport `Q` then moves port bits between adjacent vertices; the forward step is `F=Q I`. Ring order is b→a. In the R130 implementation, `Q` creates the next vertex name from the right port of the current vertex and the left port of the next vertex; the outgoing b-bit is taken from the current vertex and the incoming a-bit from the next. The inverse transport uses the same joined names with the complementary bit assignment. The two-channel C2 extension also has `12 <-> (8,4)`; that is not used in this C1 test.

The three local rewrite representatives selected as calibration *cases* are `0` (inert), `12` (merge redex), and `3` (split parent). They identify local event types. They do **not** supply energy labels.

## 2. Frozen local functional family

Let directed edge type be the ordered pair `e_i=(s_i,s_{i+1})`, with cyclic indices and R130 b→a orientation. Define

```
E(w) = sum_i eps[e_i] + sum_i eta[e_(i-1), e_i, e_(i+1)].
```

Thus `eta` reads three consecutive directed edges, i.e. four consecutive vertex labels. This distinction is essential: if `eta` were only a function of three consecutive vertex labels, its sum would be determined by all-shift three-point counts and could **not** distinguish R131/R132.

Coefficients are kept symbolic. There are no independently measured energies for the three calibration cases in R130, so assigning numerical `eps`/`eta` values would invent a calibration. Three words cannot identify the unrestricted table (9 directed edge types and up to 9^3 ordered three-edge motifs) without additional restrictions or measured energy targets.

## 3. Exact results

The script computes exact integer feature-count differences. It does not use `q=N2121/L` in the energy definition or in coefficient selection.

| Pair | Same all-shift three-point counts? | Directed edge counts equal? | Three-edge motif counts differ? |
|---|---:|---:|---:|
| R131/R132 (24 nodes) | yes | yes | yes |
| `120` / `102` (3 nodes) | no | no | yes |
| held-out 24-node pair | yes | yes | yes |

R131/R132:
- words: `111111221212222222112121` and `111112111121222221222212`;
- all directed edge-count contributions cancel exactly;
- `Delta E` is a nonzero linear form in 16 ordered `eta`-coefficients (full expression in `CHECKS.json`).

Three-node control:
- words: `120` and `102`;
- the same directed functional family distinguishes them through both `eps` and `eta` terms;
- this requires orientation-sensitive coefficients. If energy is constrained to be invariant under reflection/reversal, the pair is related by reflection and its energy difference vanishes. The ADD update is oriented, but whether physical energy may be parity-odd is an independent physical question.

Held-out pair:
- `111112112111222221221222` and `111111212211222222121122`;
- generated after the functional family was fixed, by lexicographic enumeration of 12-bit halves `h in {1,2}^12`, completing each as `h || (3-h)`, grouping by all directed pair correlations, and selecting the first non-dihedrally-equivalent group with differing `N2121`;
- all-shift three-point counts and directed edge counts agree, while ordered three-edge motif vectors differ;
- the `eta)-feature difference is exactly the negative of the R131/R132 difference for this selected held-out pair.

For each 24-node pair, the energy difference is nonzero for every coefficient vector outside one exact hyperplane in `eta)-parameter space. For the three-node pair it is nonzero outside a second hyperplane in joint `eps)/`eta) space. Hence a generic oriented local functional separates all three controls. This is a statement about the expressive power of the ansatz, not evidence that nature selected such coefficients.

## 4. Gate verdict

**Combinatorial/local-separability test: PASS.** A finite-range, orientation-sensitive energy functional on directed edge triples can distinguish both 24-node witnesses and the three-node control without inserting the global variable `q`.

**Physical X gate: NOT PASSED.** The calculation does not derive coefficients from microscopic X degrees of freedom, provide independent energy labels, establish a conservation/transfer law under `I`, identify a physical state space or measure, or calculate a kinetic law and relaxation time. The three calibration words are event representatives, not an energy calibration dataset.

Therefore this result does not justify closing the contact-energy branch, nor does it authorize a BH1/BBN run. The next physical input must constrain `eps` and `eta` independently (for example, from a specified microscopic X Hamiltonian or a measured transition-energy rule) and state how ADD event energy is balanced. Only then can one calculate `tau_X` and compare it with `H^{-1}`.

## 5. Reproduction

From repository root:

```sh
python analysis/ADD_LOCAL_EDGE_ENERGY_20261120/verify.py
```

Expected machine result: `PASS_SYMBOLIC_LOCAL_SEPARABILITY_NOT_PHYSICAL_ENERGY`.
