# G8 run report — inheritance of a chromatin mark and renewal of its reader–writer apparatus

**Date:** 6 November 2026  
**Status:** pilot computational test of an explicitly declared G8-derived subcase; not an exact reproduction of Figure 7D and not a biological experiment.

## 1. Question and verdict

The run tested five separable situations: (1) removal of the sequence-specific initiator while reader–writer feedback remains; (2) disabling reader–writer activity; (3) partial loss of the initial mark; (4) complete loss of the initial mark; and (5) renewal of the writer-enzyme pool by a separately declared, pre-existing synthesis apparatus.

**Result:** the G8 mechanism can maintain a marked domain after removal of its external sequence-specific initiating signal, provided reader–writer feedback and a suitable contact geometry remain. However, the generic one-dimensional contact kernel produces pronounced spreading (“flooding”) rather than a confined domain. Disabling the reader–writer mechanism eliminates the mark; complete erasure of the only seed is absorbing when sequence-specific recruitment is off. A finite writer-enzyme pool can be replenished by a preloaded apparatus, but the apparatus itself is not produced. Therefore the fifth test does **not** establish autonomous reproduction or a closed genetic invariant.

A separate schematic-compaction stress test shows that (i) a strongly confined contact matrix can sustain a local domain and (ii) the preloaded synthesis apparatus can improve multi-generation persistence relative to its disabled control. This is only a qualitative construction: its contact matrix and synthesis law are choices made for this test, not the polymer-derived matrix or calibrated apparatus kinetics of the paper.

## 2. Source model and fidelity boundary

The source paper is Abdulla, Vaillant & Jost, “Painters in chromatin: a unified quantitative framework to systematically characterize epigenome regulation and memory,” *Nucleic Acids Research* 50 (2022), 9083–9104, DOI: 10.1093/nar/gkac702. The authors use a two-state nucleosome model (unmodified U / modified M), Gillespie stochastic dynamics, and reader–writer feedback. Their generic simulations use 201 nucleosomes and 500 trajectories per condition. For the replication scenario, an extant M mark is diluted with probability 1/2 at each generation, with `T_cyc = 55/k0`. Figure 7D combines this replication dilution with finite enzyme availability and a polymer-derived three-dimensional contact matrix; the paper's central conclusion is that compaction plus enzyme limitation can maintain a confined domain with limited spreading.

The public `Painter_Model.py` does not run Figure 7D as-is: defaults include N=100, T=300, Tcyc=50, ts=20000, Ntot=10, and delta=0; the line assigning the finite-enzyme occupancy `delta=ps` is commented out. This was checked in the public source. The paper's 3D polymer-derived contact matrix from Supplementary Fig. S9A was not available here as a numerical matrix. Therefore this run is deliberately labelled a subcase, not a reproduction of Figure 7D.

### Simulated rate law

After the initiator is switched off, `rho_s(i)=0`. With the allosteric boost set to `r=0`, the simulated rates are:

- mark removal: `r_MU(i) = k0` for each M site;
- mark writing on a U site: `r_UM(i) = k * epsilon * P(E) * sum_{j != i} M_j * P_c(i,j)`.

Here `P(E)` is the finite-enzyme occupancy term from the model's fast-binding approximation. The 1D run uses `P_c(i,j)=1/|i-j|` (`gamma=1`). Parameters: N=201, central seed=9 M nucleosomes, `k/k0=2`, `epsilon=0.9`, `N_e=9`, `k_b/k_u=1`, and `T_cyc=55/k0`. Six replication intervals were simulated.

The initial 9-site seed is the explicit initial condition of this test, not a claim that Figure 7D uses this exact seed width.

## 3. Scenarios

| ID | Intervention | What is held fixed |
|---|---|---|
| S1 | Sequence-specific initiator removed at t=0; reader–writer feedback active | Initial 9-site mark seed; finite enzyme count 9; 1D `1/d` contact kernel |
| S2 | Reader–writer writing disabled | Same initial seed, turnover and replication dilution remain |
| S3 | Half of the 9 initial marks erased before continuation | Remaining marks and reader–writer feedback act as seed |
| S4 | All initial marks erased | `rho_s=0`; reader–writer feedback has no M seed from which to recruit |
| S5 | Writer-enzyme pool can degrade, be diluted at replication, and be resynthesized | Synthesis uses a preloaded fixed apparatus A and 45 finite precursor tokens; `A` itself is not produced |
| S5-control | Same dynamic enzyme pool, but apparatus A is disabled | No enzyme synthesis; initial enzyme pool is still present |

For S5, the added extension is intentionally explicit rather than attributed to the paper: enzyme synthesis rate is `0.2 * (core_M/9)` per `1/k0`, capped at 9 enzymes; each new enzyme consumes one precursor token; enzymes have a 55/`k0` half-life and are independently diluted with probability 1/2 at replication. Synthesis requires a nonzero core mark. The synthesis apparatus A is fixed and preloaded.

## 4. Operational outputs

The primary local transfer statistic is:

`q_n = fraction of trajectories with >=5 of 9 core sites in state M immediately before division n AND immediately before division n+1.`

This is a finite, local transfer test. It does not mean the line passed every earlier generation. Therefore a second statistic was computed:

`Q_0:n = fraction of trajectories with >=5 of 9 core sites in state M at every pre-division checkpoint from generation 0 through n.`

A weaker seed-survival statistic uses `>=1` central M site instead of `>=5`. The 95% intervals reported in the CSV are Wilson intervals for binomial proportions. The threshold 5/9 is a predeclared diagnostic for this run, not a universal biological threshold. Means, outside-core marks, enzyme counts and remaining precursor tokens are also retained; these are not reduced to the binary q statistic.

## 5. Results: generic one-dimensional contact kernel

At generation 1, after one full internal cycle but before the next replication dilution, S1 has mean 4.11/9 marked core sites, mean 88.32 total M sites, of which 84.21 lie outside the original core. The initial signal persists, but the spatial domain spreads widely. The adjacent-generation majority statistic is `q_1=0.17`; only 1% of trajectories pass the majority criterion continuously from generation 0 through generation 6 (`Q_0:6=0.01`, 95% Wilson interval 0.002–0.054). By contrast, at least one core mark persists across all six checkpoints in 95% of trajectories (`Q_seed,0:6=0.95`, 0.888–0.978). This is persistent seed-level memory, not preservation of the original localized domain.

S3 (50% initial loss) behaves similarly: the mean core count is 4.46 at the initial checkpoint and 4.03 after the first internal cycle; by generation 6, the cumulative majority-line fraction is 1%, while the cumulative seed-level fraction is 96%. Partial erasure does not restore a majority domain in this 1D setting, although a residual seed usually remains and spreading continues.

S2 loses the marks by the first generation: with reader–writer activity disabled, the only remaining process is mark removal plus replication dilution. S4 remains all-U throughout: with no residual M seed and no sequence-specific recruitment, the all-U state is absorbing under this rate law. This result is conditional on the model's mechanism; it is not a general biological claim that an erased chromatin state can never be re-established by any other pathway.

S5 does not rescue the localized domain under the 1D kernel. At generation 6, the mean enzyme pool is 0.20 and mean precursors remaining are 37.01; the cumulative majority-line fraction is 0, and the cumulative seed-level fraction is 1%. The no-A control reaches zero cumulative seed-level survival by generation 4. Thus the preloaded apparatus delays loss relative to the no-synthesis control but cannot compensate for the spreading/weakening core in this chosen 1D geometry. The pool of writer enzymes is renewed only by an externally pre-existing A.

### Key 1D values

| Scenario | Core M mean at gen 1 | Total M mean at gen 1 | Outside-core M at gen 1 | `Q_0:6` majority | `Q_0:6` seed |
|---|---:|---:|---:|---:|---:|
| S1 initiator off, R–W on | 4.11 | 88.32 | 84.21 | 0.01 | 0.95 |
| S2 R–W off | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| S3 half seed erased | 4.03 | 87.35 | 83.32 | 0.01 | 0.96 |
| S4 full seed erased | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| S5 preloaded A renews HME | 3.47 | 69.92 | 66.45 | 0.00 | 0.01 |
| S5 control, A off | 2.76 | 56.85 | 54.09 | 0.00 | 0.00 |

## 6. Separate schematic-compaction stress test

To check whether the observed flooding was tied to the generic 1D contact kernel, a separate, explicitly schematic matrix was used: `P_c=1` between distinct pairs inside the central 9-site core, and `P_c=0.05/|i-j|` for all other pairs. It is **not** the paper's polymer-derived matrix. The test uses the same core threshold and six generations, 100 trajectories per condition.

With this strong local contact block and a fixed enzyme pool, the cumulative majority-line fraction through generation 6 is 0.93 (95% Wilson interval 0.863–0.966). With a preloaded A and dynamic HME renewal it is 0.64 (0.542–0.727); with A disabled it is 0.00 (upper 95% Wilson bound 0.037). In the A-on case, the mean core mark count at generation 6 is 5.24, the mean enzyme pool is 4.21 and mean precursor tokens remaining are 9.25. The enzyme pool and precursor reserve are finite and decline; A itself remains fixed and external.

This establishes only a property of this constructed toy: a sufficiently strong local contact block plus a pre-existing enzyme-synthesis apparatus can maintain the chosen domain criterion for several generations, and disabling that apparatus changes the result. It does not establish that the paper's actual 3D matrix has these numerical values, that the added synthesis law is biologically calibrated, or that the apparatus reproduces itself.

## 7. Interpretation for C041 / R120 / R121

1. **Initiator vs maintenance:** the S1 result is a model-level witness that a transient sequence-specific initiator can be removed while an internally maintained reader–writer process continues to act. It matches the qualitative distinction made in the supplied literature review, but it is not a numerical replication of the Ragunathan/Audergon experiments.
2. **Trace vs organization:** S1 and S3 retain at least one seed in almost all trajectories while the original localized domain fails the majority criterion in most lineages. Persistence of a nonzero trace is therefore weaker than persistence of the organized domain.
3. **Read/write apparatus:** S2 and S4 show that reader–writer feedback requires both an active apparatus and, in this model with `rho_s=0`, a residual M seed. Neither the reader–writer enzymes alone nor a fully erased seed automatically recreates the state.
4. **Apparatus renewal:** S5 is not autonomous inheritance. It renews one component (HME) using a fixed, initially supplied A. This is exactly the preloaded reader/writer boundary flagged in M4 and R119. To claim `I_H`, the transmission of the profile to a successor carrier must be modeled. To claim `I_G^closed`, A and all other necessary synthesis/maintenance machinery, energy, substrates, waste pathways and carrier reproduction must be included in a closed resource ledger.
5. **Geometry matters:** the 1D kernel exhibits broad spreading; the schematic compaction matrix localizes marks. The direction agrees with the article's claim that 3D organization and enzyme limitation cooperate to confine memory, but the schematic matrix cannot be used as quantitative validation of the paper's Figure 7D.

### What the run does not do

- It does not simulate protein translation, folding, assembly of A, transcriptional regulation of A, chaperones, energy regeneration, waste removal, or a complete cell.
- It does not model quantum degrees of freedom, nuclear spins, electronic holes or proton transfer, and therefore does not test C021/R097.
- It does not estimate the probability of an arbitrary corpus, string, or artifact arising under competing provenance hypotheses.
- It does not compute Kolmogorov complexity or treat compression as a physical measure.
- It does not prove an abstract theorem that every finite system fails (or succeeds) at Level 3.

## 8. M1–M4 and numerical correction

**M1 accepted:** organization probabilities are expressed as `q_X(p)=P_{X,p}(S_{X,p})` over histories. In this run, the empirical `q_n` and `Q_0:n` are probabilities of explicitly defined core-mark events under the simulation's ensemble. They are not probabilities that a text or corpus has a particular origin.

**M2 accepted:** comparisons of artifact-origin measures require predeclared hypotheses (e.g. H_U, H_P, H_A, H_T), a predeclared invariant class `A_inv`, and likelihood comparisons. This simulation does not calculate those likelihoods and cannot adjudicate corpus provenance.

**M3 accepted:** algorithmic compressibility is a diagnostic against white-noise-like data, not a physical measure of provenance or an origin mechanism. No Kolmogorov-complexity calculation was performed here.

**M4 accepted:** the corpus is an artifact of an externally directed process and is maintained by an external read/write apparatus. Persistent conversation context is a prepared reader, not demonstrated transmission of an invariant to a new carrier. The simulation's fixed A makes the same boundary explicit.

### Consistent numerical bases

Assuming 1 KiB = 1024 bytes and `log10(2)=0.30102999566`:

| Object | Bits | Decimal orders (`log10` of `2^bits`) |
|---|---:|---:|
| Exact 350 KiB string | 2,867,200 | 863,113.204 |
| 87 KiB content framework | 712,704 | 214,545.282 |
| Cosmic attempt budget | 817.194 bits equivalent | 246 |
| Deficit for 87 KiB framework | 711,886.806 | 214,299.282 |

Thus the user's base-conversion correction is right in substance: subtracting 246 decimal orders means subtracting `246*log2(10)=817.194` bits, not subtracting 246 bits. The exact logarithmic values in the first two rows are slightly lower than the rounded values in the proposed table; the qualitative conclusion is unchanged.

## 9. Reproducibility and status

- Main 1D run: 100 trajectories per condition, six replication intervals, deterministic seed base 20261106.
- Schematic compaction run: 100 trajectories per condition, deterministic seed base 20761106.
- The initial attempt at 500 trajectories exceeded the local execution limit and produced no result used here.
- The successful outputs are pilot finite-ensemble calculations. Wilson intervals quantify finite-trajectory sampling uncertainty only; they do not include model uncertainty, contact-matrix uncertainty, or parameter uncertainty.
- Python/NumPy/Numba versions and script hashes are preserved in the metadata files. The generated CSV and compressed raw trajectories are included in the bundle.

Main script SHA-256: `5d4ac451b989f8a6029220d4ac44e0e38f4bd6ff0a6bee9fb9f29d0838b92340`  
Compaction script SHA-256: `be3c9c2c8d366f61554deefca7139589d83233356c2389d411bffd73799a041f`

## 10. Proposed register consequence

R121 should record the biological literature synthesis as an external physical support for (i) sequence transmission, (ii) regulatory-state maintenance/transmission, and (iii) spatial-organization inheritance, while preserving differences among them. This run adds a finite-model demonstration of the boundary between maintenance of a mark, maintenance of a localized domain, renewal of one enzyme pool, and reproduction of the apparatus that renews it.

Recommended status:

- R121: literature synthesis plus model-level finite pilot; no new biological discovery.
- C041: formal target strengthened by a concrete reader–writer maintenance mechanism and a separately exposed apparatus boundary; not yet a physical invariant.
- L04/L05/L07: remain open.
- `I_C`: finite toy profiles can be instantiated for this model, but a cross-realization equivalence class is not established here.
- `I_H`: not obtained; no inter-carrier transfer map was modeled.
- `I_G^closed`: not obtained; A is preloaded and external.

## 11. Files

See the accompanying ZIP for scripts, raw trajectories, summaries, contact matrices, metadata, cumulative-line probabilities and this report.
