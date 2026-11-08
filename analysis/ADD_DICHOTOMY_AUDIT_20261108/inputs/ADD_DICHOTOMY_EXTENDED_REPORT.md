# ADD / R126 — extended E0 dichotomy audit

**Execution:** PASS / finite reconstruction audit  
**Backend:** unchanged `add_backend_smoke_v1.py`  
**Scope:** four-bit C2 state space on a directed two-port ring; not author code; not NOW integration.

## Executive result

The earlier quiet/growth dichotomy remains valid for the **literal Definition-4 bit assignment** implemented by the original backend. It does **not** transfer to the alternative **Fig. 2(a) operational assignment**. Under the latter, an initial E0 state can create a merge after the first half-shift; the split/merge dynamics can then cycle with bounded graph size instead of growing monotonically.

Therefore the mathematically correct status is branch-conditional:

- `literal_Definition_4`: dichotomy supported by the local lemma, exact transfer counts, and the earlier exhaustive L=3 orbit checks.
- `Fig_2(a)_operational`: the no-new-merge lemma is false; richer split/merge dynamics are observed. The full-orbit classification is exhaustive only for L=2 and L=3, not a theorem for all ring lengths.
- Which branch is the intended ADD operator remains unresolved until the source discrepancy is resolved.

## 1. Local reason for the discrepancy

Write the old directed cycle as `u_i -> u_(i+1)` and the new half-edge vertex as `w_i = u_i.r vee u_(i+1).l`. The new directed edges run `w_i -> w_(i-1)`.

The two bit assignments are deliberately kept separate:

```text
literal: h_i = (a_i,   b_(i+1), a2_i,   b2_(i+1))
Fig 2a:  h_i = (a_(i+1), b_i,   a2_(i+1), b2_i)
```

For the literal branch, a channel-1 merge on `w_i -> w_(i-1)` requires `h_i=(1,0,0,0)` and `h_(i-1)=(0,1,0,0)`. Expanding these conditions forces the shared old vertex `u_i` to have `(a1,b1)=(1,1)`, an initial split. Since E0 excludes split vertices, no merge can be created by the half-shift from E0. The analogous channel-2 argument is identical.

For the Fig-2(a) branch, the same merge condition expands to an allowed old triple of the form:

```text
u_(i-1): 01   ;   u_i: 00   ;   u_(i+1): 10
```

in channel 1 (with channel-2 bits zero for this redex). This contains neither an old split nor the forbidden old directed merge `10 -> 01`. It is therefore compatible with E0. This is the precise local mechanism behind the new counterexample.

The Fig-2(a) split condition also changes: a new split can be created by the old directed pair `01 -> 10`, which is not forbidden by E0. Thus both the no-new-merge lemma and the split-persistence mechanism used in the literal-branch proof change.

## 2. Exhaustive first-half-shift classifications

Counts are over labelled cyclic words in the four-bit alphabet, conditioned on E0 (no split vertex and no directed merge edge initially). Categories are post-half-shift motifs:

| L | E0 | Literal: no motif | Literal: split only | Fig 2a: no motif | Fig 2a: split only | Fig 2a: merge only | Fig 2a: both |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 192 | 162 | 30 | 162 | 30 | 0 | 0 |
| 3 | 2,660 | 2,042 | 618 | 1,952 | 660 | 42 | 6 |
| 4 | 36,856 | 25,890 | 10,966 | 24,218 | 11,682 | 812 | 144 |
| 5 | 510,664 | 328,394 | 182,270 | 301,804 | 192,320 | 12,920 | 3,620 |

The literal branch creates no merges in these exhaustive enumerations. Fig 2a creates 48 post-shift merge cases at L=3, 956 at L=4, and 16,540 at L=5 (including cases where split and merge are both present).

The local formula was cross-checked against the graph-level implementation for every E0 configuration at L=2 and L=3 in both branches; all category counts matched exactly.

## 3. Full-orbit exhaustive results for Fig 2a

The full map is `f = sqrt_tau_fig2a o I2`. Each E0 start was iterated until a repeat of the canonical directed state word was found or 40 full steps elapsed. The canonicalization allows directed cycle rotations but **forgets exact Name terms**.

| Initial ring | E0 starts | Period 1 | Period 2 | Period 4 | Active starts | Max L seen | Not repeated by 40 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 192 | 86 | 76 | 30 | 30 | 4 | 0 |
| 3 | 2,660 | 500 | 1,452 | 708 | 708 | 5 | 0 |

For L=3, all 2,660 initial E0 words were periodic immediately in the directed-state-word quotient. The 708 active starts (those encountering a split or merge) lie on period-4 state-word orbits; they do not exhibit persistent size growth within these exhaustive orbits. This is finite evidence for L=2,3 only.

### Explicit C1 bounded-oscillation witness

Initial C1 word, with state tuples ordered `(a1,b1,a2,b2)`:

```text
[00, 01, 00, 10]
```

It is E0. Under Fig 2a, the full trajectory has motif/size pattern:

```text
t:       0       1       2       3       4       5 ...
L:       4       4       3       3       4       4 ...
motif:   --    merge      --    split      --    merge ...
```

The directed state-word period is 4. Exact named-graph equality returns after 20 full steps, so the word-level quotient must not be confused with exact identity of Name terms.

### Explicit C2 branch-discriminator witness

Initial C2 states:

```text
[(0,0,0,0), (0,0,1,0), (1,0,0,1)]
```

This is E0 and has particle vector `(1,0,1,1)`.

For the **same initial graph**:

- Literal branch: `L = 3,3,4,5,6,7,8,...`; the split count remains 1 in the displayed 12-step trace.
- Fig-2(a) branch: `L = 3,3,2,2,3,3,2,2,...`; merge and split alternate, yielding a bounded cycle in the directed state-word projection.

This is a direct branch discriminator: a seed classified as sustained growth by the literal operator becomes a bounded split/merge oscillator under the Fig-2(a) operator.

## 4. Transfer matrices and quiet fractions

The E0 transfer matrix is 16-state, with transitions allowed when the next vertex is not split and the directed pair is not a merge:

```text
chi_E(lambda) = lambda^14 (lambda^2 - 14 lambda + 2)
lambda_E = 7 + sqrt(47) = 13.855654600401...
N_E(L) = Tr(M_E^L)
       = (7+sqrt(47))^L + (7-sqrt(47))^L
```

The literal one-step quiet class is E0 plus no split on the first literal half-shift. Since the literal branch creates no merge from E0, this is the full no-rewrite class:

```text
chi_Q_literal(lambda) = lambda^13 (lambda - 1) (lambda^2 - 13 lambda + 4)
lambda_Q_literal = (13 + sqrt(153))/2 = 12.684658438426...
kappa_literal = lambda_Q_literal/lambda_E = 0.915486045535...
```

For Fig 2a, a genuinely no-rewrite first half-shift must exclude **both** new splits and new merges. The merge condition depends on three consecutive old vertices, so the transfer construction tracks ordered pairs `(s_(i-1),s_i)` and has 194 pair states and 2,424 directed transitions:

```text
chi_Q_fig2a(lambda) = lambda^187
  (lambda^3 - lambda^2 - 2 lambda - 1)
  (lambda^4 - 13 lambda^3 + 6 lambda^2 + 7 lambda + 4)
```

The dominant eigenvalue is the largest real root of the quartic:

```text
lambda_Q_fig2a = 12.4718523471188...
kappa_fig2a = lambda_Q_fig2a/lambda_E = 0.900127255392...
```

The trace counts were checked against direct enumeration for L=2..5 and also computed for L=6:

| L | E0 | Q literal | Q Fig 2a (no split and no merge after first half-shift) |
|---:|---:|---:|---:|
| 2 | 192 | 162 | 162 |
| 3 | 2,660 | 2,042 | 1,952 |
| 4 | 36,856 | 25,890 | 24,218 |
| 5 | 510,664 | 328,394 | 301,804 |
| 6 | 7,075,584 | 4,165,554 | 3,763,548 |

Both quiet spectral radii exceed 1, so the absolute number of one-step quiet configurations still grows exponentially. Their fraction in the uniform labelled E0 ensemble decays exponentially. The Fig-2a fraction decays faster asymptotically than the literal fraction. This is a statement about the counting ensemble; it is not itself an orbit theorem.

## 5. Four-vector sector result and its limitation

The exact L=12 sector `(4,6,7,7)` was separately rerun with the inherited sector DP:

```text
E0             = 33,483,953,832
Q_literal      =  7,971,639,792
Q_literal/E0   = 0.23807343159043692
```

This number belongs only to the **literal** quiet operator from `sector_statistics.py`. It must not be reused as the Fig-2(a) quiet probability. A pair-state DP for the Fig-2(a) `(4,6,7,7)` sector exceeded the 200-second execution cap; no partial value is reported.

## 6. Verdict and scope

1. The original E0 quiet/growth dichotomy remains a valid mathematical result **for the literal reconstructed half-shift** on the directed cycle with the stated local split/merge rules. The prior structural lemma explains why: E0 forbids a new merge, and literal half-shift maps split children back into a split motif. The previous L=3 exhaustive audit checked 18,620 full transitions with no merge, no split-count decrease, and `Delta L = split_count`.
2. The dichotomy is **not invariant under the Fig-2(a) endpoint assignment**. The explicit E0 merge pattern `01,00,10` falsifies the no-new-merge lemma. The same C2 seed grows without bound in the literal branch over the displayed trace but cycles with bounded L in the Fig-2(a) branch.
3. Because the source-level choice between the two bit assignments remains unresolved, no unconditional ADD source-conformance claim follows.
4. No arbitrary-graph theorem, arbitrary-L Fig-2(a) orbit theorem, full Fig-2(a) four-vector L=12 result, or NOW integration is claimed.

## Reproduction

Place the following files in one directory:

- `ADD_DICHOTOMY_EXTENDED_AUDIT.py`
- `add_backend_smoke_v1.py` (unchanged dependency)
- `sector_statistics.py` (for the separately recorded literal sector result)

Run:

```bash
python -m pip install sympy
python ADD_DICHOTOMY_EXTENDED_AUDIT.py --backend add_backend_smoke_v1.py --json-out ADD_DICHOTOMY_EXTENDED_REPORT.json
python sector_statistics.py --L 12 --particles 4,6,7,7
```

The extended audit ran in about 13.2 seconds in the current Python/SymPy environment. Machine-readable details, all checks and SHA-256 values are in `ADD_DICHOTOMY_EXTENDED_REPORT.json`.
