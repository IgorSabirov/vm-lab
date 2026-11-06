"""G8-derived 1D finite-enzyme Painter model experiment.

Reproducible research subcase, not an exact reproduction of Fig. 7D:
- 201 nucleosomes, initial 9-site M core.
- rho_s = 0 after t=0 (sequence-specific initiator removed).
- Pc(i,j)=1/|i-j| (gamma=1), not the polymer-derived 3D-compaction matrix of Fig. 7D.
- k/k0=2, epsilon=0.9, Ne_tot=9, kb/ku=1.
- Tcyc=55/k0; replication erases each extant M mark with probability 1/2.
- Six replication boundaries; 500 independent trajectories per condition.

The fifth condition adds explicit, deliberately transparent HME renewal:
- HME pool E is diluted binomially at replication and degrades with half-life 55/k0.
- Synthesis is catalysed by a pre-existing fixed apparatus A, is proportional to
  the fraction of marked core sites, and consumes one finite precursor token.
- A itself is NOT synthesized by this model. This is a one-level renewal extension,
  not closed autopoiesis.
"""
from __future__ import annotations
import argparse, json, math, hashlib, platform, sys, os
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

N = 201
CORE = 9
CENTER = N // 2
K0 = 1.0
K = 2.0
EPS = 0.9
NE0 = 9
KB_OVER_KU = 1.0
GAMMA = 1.0
TCYC = 55.0
NCYCLES = 6
NTRAJ = 500
THRESHOLD = 5
PARTIAL_KEEP_PROB = 0.5
B0 = 45
KSYN = 0.20
KDEG = math.log(2.0) / TCYC


def make_kernel(n: int, gamma: float = 1.0) -> np.ndarray:
    idx = np.arange(n)
    dist = np.abs(idx[:, None] - idx[None, :]).astype(float)
    out = np.zeros((n, n), dtype=np.float64)
    mask = dist > 0
    out[mask] = 1.0 / np.power(dist[mask], gamma)
    return out


@njit
def enzyme_feedback(nm: int, ne: int, kbku: float) -> float:
    # Effective state-dependent recruitment P(E), equivalent to the fast
    # binding/unbinding approximation used in the public model implementation.
    if nm <= 0 or ne <= 0:
        return 0.0
    x = nm / ne
    a = 1.0 + x + kbku / ne
    disc = a * a - 4.0 * x
    if disc < 0.0:
        disc = 0.0
    return (a - math.sqrt(disc)) / (2.0 * x)


@njit
def run_one(seed: int, mode: int, dynamic_enzymes: bool, apparatus_on: bool,
            kernel: np.ndarray, n: int, center: int, core: int,
            k0: float, k: float, eps: float, ne0: int, kbku: float,
            tcyc: float, ncycles: int, partial_keep: float,
            b0: int, ksyn: float, kdeg: float, threshold: int):
    """mode: 0 baseline, 1 reader-off, 2 partial mark loss, 3 full mark loss.

    Both pre-division and immediately post-dilution states are recorded. The
    primary q_n uses pre-division states so that a generation has time to
    restore the domain after the preceding dilution before it is evaluated.
    """
    np.random.seed(seed)
    m = np.zeros(n, dtype=np.uint8)
    lo = center - core // 2
    hi = lo + core
    if mode != 3:
        m[lo:hi] = 1
    if mode == 2:
        for j in range(lo, hi):
            if np.random.random() >= partial_keep:
                m[j] = 0
    nm = int(m.sum())
    core_m = int(m[lo:hi].sum())
    s = np.zeros(n, dtype=np.float64)
    for i in range(n):
        acc = 0.0
        for j in range(n):
            if m[j] == 1:
                acc += kernel[i, j]
        s[i] = acc

    ne = ne0
    budget = b0
    t = 0.0
    next_rep = tcyc
    pre_core = np.zeros(ncycles + 1, dtype=np.int16)
    pre_total = np.zeros(ncycles + 1, dtype=np.int16)
    pre_leak = np.zeros(ncycles + 1, dtype=np.int16)
    pre_enz = np.zeros(ncycles + 1, dtype=np.int16)
    pre_budget = np.zeros(ncycles + 1, dtype=np.int16)
    post_core = np.zeros(ncycles + 1, dtype=np.int16)
    post_total = np.zeros(ncycles + 1, dtype=np.int16)
    post_leak = np.zeros(ncycles + 1, dtype=np.int16)
    post_enz = np.zeros(ncycles + 1, dtype=np.int16)
    post_budget = np.zeros(ncycles + 1, dtype=np.int16)
    pre_core[0] = post_core[0] = core_m
    pre_total[0] = post_total[0] = nm
    pre_leak[0] = post_leak[0] = nm - core_m
    pre_enz[0] = post_enz[0] = ne
    pre_budget[0] = post_budget[0] = budget

    gen = 0
    reader_on = mode != 1

    while gen < ncycles:
        delta = enzyme_feedback(nm, ne, kbku) if reader_on else 0.0
        syn_rate = 0.0
        deg_rate = 0.0
        if dynamic_enzymes:
            if apparatus_on and budget > 0 and ne < ne0 and core_m > 0:
                syn_rate = ksyn * (core_m / core)
            if ne > 0:
                deg_rate = kdeg * ne

        total_rate = syn_rate + deg_rate
        for i in range(n):
            if m[i] == 1:
                total_rate += k0
            elif reader_on and delta > 0.0:
                total_rate += k * eps * delta * s[i]

        if total_rate <= 0.0:
            t = next_rep
        else:
            dt = -math.log(max(np.random.random(), 1e-15)) / total_rate
            if t + dt >= next_rep:
                t = next_rep
            else:
                t += dt
                choice = np.random.random() * total_rate
                cum = 0.0
                fired = False
                for i in range(n):
                    rate = k0 if m[i] == 1 else (k * eps * delta * s[i] if reader_on and delta > 0.0 else 0.0)
                    cum += rate
                    if choice < cum:
                        if m[i] == 1:
                            m[i] = 0
                            nm -= 1
                            if lo <= i < hi:
                                core_m -= 1
                            sign = -1.0
                        else:
                            m[i] = 1
                            nm += 1
                            if lo <= i < hi:
                                core_m += 1
                            sign = 1.0
                        for q in range(n):
                            s[q] += sign * kernel[q, i]
                        fired = True
                        break
                if not fired and dynamic_enzymes:
                    if choice < cum + syn_rate:
                        if syn_rate > 0.0 and ne < ne0 and budget > 0:
                            ne += 1
                            budget -= 1
                    else:
                        if deg_rate > 0.0 and ne > 0:
                            ne -= 1

        if t >= next_rep - 1e-12:
            # Capture the generation's pre-division state after a full cycle
            # of internal repair/spreading but before dilution.
            gen += 1
            pre_core[gen] = core_m
            pre_total[gen] = nm
            pre_leak[gen] = nm - core_m
            pre_enz[gen] = ne
            pre_budget[gen] = budget

            # Replication dilution: each present M mark is lost with p=1/2.
            for j in range(n):
                if m[j] == 1 and np.random.random() < 0.5:
                    m[j] = 0
                    nm -= 1
                    if lo <= j < hi:
                        core_m -= 1
            if dynamic_enzymes:
                old_ne = ne
                survivors = 0
                for _ in range(old_ne):
                    if np.random.random() < 0.5:
                        survivors += 1
                ne = survivors
            for i in range(n):
                acc = 0.0
                for j in range(n):
                    if m[j] == 1:
                        acc += kernel[i, j]
                s[i] = acc
            post_core[gen] = core_m
            post_total[gen] = nm
            post_leak[gen] = nm - core_m
            post_enz[gen] = ne
            post_budget[gen] = budget
            next_rep += tcyc

    return (pre_core, pre_total, pre_leak, pre_enz, pre_budget,
            post_core, post_total, post_leak, post_enz, post_budget)


def wilson(k: int, n: int, z: float = 1.959963984540054):
    if n == 0:
        return (math.nan, math.nan)
    phat = k / n
    den = 1 + z*z/n
    center = (phat + z*z/(2*n))/den
    half = z*math.sqrt(phat*(1-phat)/n + z*z/(4*n*n))/den
    return center-half, center+half


def main(outdir: str, ntraj: int = NTRAJ, seed0: int = 20261106):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    kernel = make_kernel(N, GAMMA)
    scenarios = [
        ("S1_initiator_off_RW_on", 0, False, False),
        ("S2_reader_writer_off", 1, False, False),
        ("S3_partial_50pct_mark_loss", 2, False, False),
        ("S4_full_mark_loss", 3, False, False),
        ("S5_apparatus_renewal_A_preloaded", 0, True, True),
        ("S5_control_apparatus_source_off", 0, True, False),
    ]
    rows = []
    raw = {}
    for s_idx, (name, mode, dynamic, app_on) in enumerate(scenarios):
        arrays = []
        for rep in range(ntraj):
            # A disjoint deterministic seed range per scenario and trajectory.
            res = run_one(seed0 + s_idx*100000 + rep, mode, dynamic, app_on,
                          kernel, N, CENTER, CORE, K0, K, EPS, NE0,
                          KB_OVER_KU, TCYC, NCYCLES, PARTIAL_KEEP_PROB,
                          B0, KSYN, KDEG, THRESHOLD)
            arrays.append(res)
        pre_core = np.stack([a[0] for a in arrays])
        pre_total = np.stack([a[1] for a in arrays])
        pre_leak = np.stack([a[2] for a in arrays])
        pre_enz = np.stack([a[3] for a in arrays])
        pre_budget = np.stack([a[4] for a in arrays])
        post_core = np.stack([a[5] for a in arrays])
        post_total = np.stack([a[6] for a in arrays])
        post_leak = np.stack([a[7] for a in arrays])
        post_enz = np.stack([a[8] for a in arrays])
        post_budget = np.stack([a[9] for a in arrays])
        raw[name] = {"pre_core":pre_core, "pre_total":pre_total, "pre_leak":pre_leak,
                     "pre_enzymes":pre_enz, "pre_budget":pre_budget,
                     "post_core":post_core, "post_total":post_total, "post_leak":post_leak,
                     "post_enzymes":post_enz, "post_budget":post_budget}
        for g in range(NCYCLES + 1):
            # q_n: at least 5/9 core sites immediately before division n
            # and again immediately before the next division n+1.
            if g < NCYCLES:
                maj = (pre_core[:,g] >= THRESHOLD) & (pre_core[:,g+1] >= THRESHOLD)
                seed = (pre_core[:,g] >= 1) & (pre_core[:,g+1] >= 1)
                q_majority = float(np.mean(maj)); k_majority = int(np.sum(maj))
                q_seed = float(np.mean(seed)); k_seed = int(np.sum(seed))
                lo_m, hi_m = wilson(k_majority, ntraj)
                lo_s, hi_s = wilson(k_seed, ntraj)
            else:
                q_majority = q_seed = lo_m = hi_m = lo_s = hi_s = math.nan
            rows.append({
                "scenario":name, "generation":g,
                "mean_core_M_predivision":float(np.mean(pre_core[:,g])),
                "mean_core_M_postdilution":float(np.mean(post_core[:,g])),
                "sd_core_M_predivision":float(np.std(pre_core[:,g], ddof=1)),
                "mean_total_M_predivision":float(np.mean(pre_total[:,g])),
                "mean_outside_core_M_predivision":float(np.mean(pre_leak[:,g])),
                "mean_HME_count_predivision":float(np.mean(pre_enz[:,g])),
                "mean_HME_count_postdilution":float(np.mean(post_enz[:,g])),
                "mean_precursor_remaining_predivision":float(np.mean(pre_budget[:,g])),
                "q_majority_predivision_and_next_transfer":q_majority,
                "q_majority_CI95_low":lo_m,
                "q_majority_CI95_high":hi_m,
                "q_seed_predivision_and_next_transfer":q_seed,
                "q_seed_CI95_low":lo_s,
                "q_seed_CI95_high":hi_s,
                "n_trajectories":ntraj,
            })
    df = pd.DataFrame(rows)
    df.to_csv(out / "G8_SUBCASE_SUMMARY.csv", index=False)
    np.savez_compressed(out / "G8_SUBCASE_RAW.npz", **{
        f"{name}__{field}": arr for name, vals in raw.items() for field, arr in vals.items()
    })
    np.save(out / "G8_KERNEL_1D.npy", kernel)
    script_path = Path(__file__)
    script_sha = hashlib.sha256(script_path.read_bytes()).hexdigest()
    meta = {
        "title": "G8-derived 1D finite-enzyme Painter subcase",
        "not_exact_reproduction_of_Fig7D": True,
        "reason": "Figure 7D uses a polymer-derived 3D contact matrix (Supplementary Fig S9A); this run uses the explicitly declared Pc=1/|i-j|^gamma subcase.",
        "parameters": {
            "N_nucleosomes":N,"core_nucleosomes":CORE,"center_index_zero_based":CENTER,
            "k0":K0,"k_over_k0":K/K0,"epsilon":EPS,"gamma":GAMMA,
            "Ne_total_initial":NE0,"kb_over_ku":KB_OVER_KU,
            "T_cycle_in_1_over_k0":TCYC,"cycles":NCYCLES,
            "partial_loss_keep_probability":PARTIAL_KEEP_PROB,
            "trajectory_count_per_condition":ntraj,
            "primary_domain_threshold_M_of_9":THRESHOLD,
            "apparatus_extension": {
                "enzyme_pool_initial_and_cap":NE0,
                "enzyme_half_life_in_1_over_k0":TCYC,
                "enzyme_synthesis_rate_max_per_1_over_k0":KSYN,
                "precursor_tokens_initial":B0,
                "synthesis_requires_core_mark":True,
                "synthesis_apparatus_A_preloaded_and_fixed":True,
                "A_is_not_reproduced_by_model":True,
                "interpretation":"one-level enzyme renewal with explicit external synthesis apparatus; not closed autopoiesis"
            }
        },
        "scenario_codes": {"S1":0,"S2":1,"S3":2,"S4":3,"S5": "dynamic enzyme pool extension"},
        "seed_base":seed0,
        "python":platform.python_version(),
        "numpy":np.__version__,"numba":__import__('numba').__version__,
        "script_sha256":script_sha,
        "generated_utc":None,
        "notes":[
            "rho_s=0 for all simulated post-initiation times.",
            "S2 sets reader-dependent recruitment Delta_eff=0; marks only undergo turnover and replicative dilution.",
            "S3 randomly erases 50% of the initial 9-site core marks before continuation.",
            "q_n uses pre-division snapshots to allow the full post-dilution generation for restoration.",
            "S4 removes all initial marks; with rho_s=0 and no marks, all-U is absorbing.",
            "S5 explicitly adds HME synthesis/degradation and enzyme dilution; it assumes a fixed preloaded synthesis apparatus A and finite precursor tokens.",
            "No quantum model, protein-folding model, transcription/translation kinetics, or physical energy accounting is included."
        ]
    }
    (out / "G8_SUBCASE_METADATA.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    # Compact per-scenario generation summary for report.
    for name in raw:
        d = df[df.scenario == name]
        raw[name]["summary_rows"] = d
    with open(out / "G8_SUBCASE_RESULT.md", "w", encoding="utf-8") as f:
        f.write("# G8-derived 1D Painter subcase: results\n\n")
        f.write("This is an explicit 1D subcase, not an exact reproduction of the paper's Figure 7D.\n\n")
        f.write("Parameters: N=201, initial core=9 M nucleosomes, rho_s=0 after t=0, Pc=1/|i-j|, gamma=1, k/k0=2, epsilon=0.9, Ne=9, kb/ku=1, Tcyc=55/k0, six replication boundaries, 500 trajectories per condition.\n\n")
        f.write("The fifth condition adds a finite HME renewal module using a preloaded fixed synthesis apparatus A and 45 precursor tokens. A itself is not reproduced.\n\n")
        f.write("## Primary q_n\n\n")
        f.write("q_n = fraction of trajectories with at least 5/9 central M sites immediately before division n AND immediately before the next division n+1. This allows a full generation for repair after the preceding dilution. It is an operational diagnostic for this run, not a universal biological threshold.\n\n")
        for name in raw:
            d = df[(df.scenario == name) & (df.generation < NCYCLES)]
            f.write(f"### {name}\n\n")
            f.write("| n | core M pre-division | core M post-dilution | total M pre-division | outside-core M | HME pre-division | resource left | q_n (majority + next transfer) |\n|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for _, r in d.iterrows():
                f.write(f"| {int(r.generation)} | {r.mean_core_M_predivision:.3f} | {r.mean_core_M_postdilution:.3f} | {r.mean_total_M_predivision:.3f} | {r.mean_outside_core_M_predivision:.3f} | {r.mean_HME_count_predivision:.3f} | {r.mean_precursor_remaining_predivision:.3f} | {r.q_majority_predivision_and_next_transfer:.3f} [{r.q_majority_CI95_low:.3f}, {r.q_majority_CI95_high:.3f}] |\n")
            f.write("\n")
        f.write("## Provenance\n\n")
        f.write(f"Script SHA-256: `{script_sha}`. Seeds are deterministic: base {seed0}, disjoint 100000-wide scenario blocks.\n")
    print(df[df.generation < NCYCLES][["scenario","generation","mean_core_M_predivision","mean_core_M_postdilution","mean_total_M_predivision","mean_outside_core_M_predivision","mean_HME_count_predivision","mean_precursor_remaining_predivision","q_majority_predivision_and_next_transfer","q_seed_predivision_and_next_transfer"]].to_string(index=False))
    print("\nWrote:", out)
    print("script_sha256:", script_sha)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="/mnt/data/G8_SUBCASE_RUN")
    ap.add_argument("--ntraj", type=int, default=NTRAJ)
    ap.add_argument("--seed", type=int, default=20261106)
    args = ap.parse_args()
    main(args.outdir, args.ntraj, args.seed)
