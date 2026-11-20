"""Model, numerical and budget controls for the R135 readiness review."""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys

import mpmath as mp
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import controls as original

PARENT = original.module_at("r131_spectrum", original.ROOT / "analysis/BH1_YANG_MILLS_COMPARISON_20261119/check_r131_r134_sector.py")
GRAPH = original.module_at("r135_graph", HERE.parents[1] / "verify.py")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        out = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        out.writeheader()
        out.writerows(rows)


def feature_screen(out):
    engine = original.module_at("named_engine", GRAPH.ENGINE)
    words = json.loads(GRAPH.WITNESSES.read_text())["dynamics"]["cases"]["binary"]["words"]
    motifs = ["12", "21", "212", "121", "2121"]
    rows = []
    for orbit, word in enumerate(words):
        state = engine.named(tuple(map(int, word)))
        for n in range(9):
            labels = tuple(label for name, label in state)
            row = dict(orbit=orbit, step=n, length=len(labels), alphabet=" ".join(map(str, sorted(set(labels)))))
            row.update({s: PARENT.pattern(labels, tuple(map(int, s))) for s in motifs})
            # Report the classified windows and their coverage separately.
            table = GRAPH.samples(labels, range(4))
            valid = sum(count for window, count in table.items() if max(window) < 3)
            forwards = sum(table[a,(a+1)%3,a,(a+1)%3] for a in range(3))
            backwards = sum(table[(a+1)%3,a,(a+1)%3,a] for a in range(3))
            row.update(ternary_windows=valid, ternary_total=len(labels),
                       masked_plus=forwards+backwards, masked_minus=forwards-backwards,
                       M_plus=forwards+backwards if valid==len(labels) else None,
                       M_minus=forwards-backwards if valid==len(labels) else None)
            rows.append(row)
            if n < 8:
                state = engine.forward(state, (1,-1))
    write_csv(out/"features.csv", rows)
    result = {}
    for motif in motifs:
        pairs = list(zip(rows[1:9], rows[10:18]))
        result[motif] = {
            "count_difference_steps": [r["step"] for r,s in pairs if r[motif]!=s[motif]],
            "density_difference_steps": [r["step"] for r,s in pairs
                                         if Fraction(r[motif],r["length"])!=Fraction(s[motif],s["length"])],
        }
    if [r["2121"] for r in rows] != [2]+[0]*8+[1]+[0]*8:
        raise ValueError("R131 orbit changed")
    return result


def energies(word, u):
    c = [1+(u-1)*((int(label)>>1)&1) for label in word]
    b = mp.matrix(len(c))
    for i in range(len(c)):
        b[i,i], b[i,(i+1)%len(c)] = -1,1
    eig = list(mp.eigsy(b.T*mp.diag(c)*b,eigvals_only=True))
    tol = mp.sqrt(mp.eps)
    nullity = max(1,c.count(0))  # components of a cycle after deleting its zero edges
    if min(eig)<-tol or sum(abs(v)<tol for v in eig)!=nullity or abs(sum(eig)-2*sum(c))>tol:
        raise ValueError("Trace or nullity")
    return [mp.sqrt(v) if v>tol else mp.mpf(0) for v in eig]


def entropy(row, b):
    scaled = [b*w/2 for w in row]
    return 2*mp.fsum(mp.log(2*mp.cosh(t))-t*mp.tanh(t) for t in scaled)


def entropy_difference(freqs,b):
    return entropy(freqs[0],b)-entropy(freqs[1],b)


def panel(out):
    """Frozen 32-word panel; rotations refer to the graph, not to matrix basis order."""
    rng = np.random.Generator(np.random.PCG64(13521))
    seen, rows = set(), []
    with mp.workdps(80):
        while len(rows)<32:
            word = tuple(map(int,rng.permutation(np.repeat([0,1,2],8))))
            canonical = min(word[i:]+word[:i] for i in range(len(word)))
            if canonical in seen:
                continue
            seen.add(canonical)
            weights = [1+((s>>1)&1) for s in word]
            exact = PARENT.moments(weights,6)[-1]
            freqs = energies(word,2)
            if abs(mp.fsum(w**12 for w in freqs)-exact)>mp.mpf("1e-55"):
                raise ValueError("Sixth moment on panel")
            rows.append(dict(word="".join(map(str,word)),u=2,b=1,
                             trace_K6=exact,entropy=mp.nstr(entropy(freqs,1),24)))
    write_csv(out/"panel.csv",rows)


def root_in_bracket(freqs, low, high):
    first = entropy_difference(freqs,low)
    for _ in range(52):
        mid = (low+high)/2
        if first*entropy_difference(freqs,mid)>0:
            low = mid
        else:
            high = mid
    return (low+high)/2


def spectral_run(digits):
    with mp.workdps(digits):
        mixed_word = [0,3,2,1]
        for u in [0,1,2]:
            energies(mixed_word,u)
        weights=[1+((s>>1)&1) for s in mixed_word]
        if weights != [1,2,2,1] or PARENT.moments(weights,2) != [12,58]:
            raise ValueError("Mixed word traces")
        rows, roots = [], []
        for u in range(7):
            freqs = [energies(w,u) for w in PARENT.WORDS]
            theory = mp.mpf(691)*(u-1)**4*(u+1)**2/29030400
            ratios = []
            for k in (3,4,5,6,7,8):
                b = mp.mpf(2)**(-k)
                delta = entropy_difference(freqs,b)
                ratios.append(delta/b**12)
                rows.append(dict(u=u,b=float(b),delta_S=mp.nstr(delta,24),ratio_b12=mp.nstr(ratios[-1],24),
                                 theory=mp.nstr(theory,24)))
            extrapolated = (4*ratios[-1]-ratios[-2])/3
            if abs(extrapolated-theory) > mp.mpf("1e-6")*max(abs(theory),mp.mpf("1e-30")):
                raise ValueError(f"Small-b extrapolation at u={u}: {extrapolated} vs {theory}")
            if u == 2:
                bs = [mp.mpf(2)+mp.mpf(j)/32 for j in range(65)]
                values = [entropy_difference(freqs,b) for b in bs]
                for x,y,fx,fy in zip(bs,bs[1:],values,values[1:]):
                    if fx==0:
                        roots.append(float(x))
                    elif fx*fy < 0:
                        roots.append(float(root_in_bracket(freqs,x,y)))
                if values[-1]==0:
                    roots.append(float(bs[-1]))
        return rows,roots


def budget():
    base = original.CFG["budget_control"]
    branches = []
    for latent in (1.175,1.025):
        for eps in base["eps_grid"]:
            branches.append(dict(latent=latent,eps=eps,xi_min=(base["delta_rho_Tgamma4"]/(latent*eps))**0.25))
    # Decoupled neutrino thermometer, reversible hot X before the late normalization.
    w = math.log(35)
    s35 = 6.9829-1.0348/w
    p35 = (1.7469-0.79281/w)/(1-0.30484/w)
    e35 = s35-p35
    factor = (e35/(1.471-.01768))*(1.471/s35)**(4/3)
    late = original.budget()["rows"][0]["late_equivalent"]
    return dict(late_latent_thresholds=branches,example_Tx_over_Tc=35,
                high_T_s=s35,high_T_p=p35,high_T_rho=e35,
                reversible_ratio_to_hot_Tc_per_decoupled_nu=factor,
                conditional_high_T_equivalent_at_eps1=late*factor)


def t3_decision(levels, floor=1e-6):
    """Three refinement levels, each holding five positive D/H abundances."""
    v=np.asarray(levels,dtype=float)
    if v.shape!=(3,5) or not np.isfinite(v).all() or np.any(v<=0):
        raise ValueError("Three levels and five positive finite abundances required")
    residual=(v[:,3]-v[:,4])/v[:,0]
    # Fix the absolute zero-region tolerance before inspecting integration errors.
    unstable_observable=np.any(abs(np.diff(v,axis=0))>0.1*floor*v[-1])
    unstable_residual=np.any(abs(np.diff(residual))>0.1*max(floor,abs(residual[-1])))
    if unstable_observable or unstable_residual:
        return "FAIL_CONVERGENCE"
    return "RESOLVED" if abs(residual[-1])>floor else "BELOW_NUMERICAL_FLOOR"


def center_control():
    from cumulants import combine
    from measure_field import count_windows

    rng = np.random.default_rng(13590)
    center = np.exp(2j*np.pi/3)
    strata = [center**rng.integers(0,3,size=(8,8,8)),
              np.broadcast_to((center**(np.arange(8)%2))[:,None,None],(8,8,8))]
    def contrast(rotation):
        values = [combine([count_windows(field*rotation,1)])["connected_even"] for field in strata]
        return values[1]-values[0]
    initial = contrast(1)
    if abs(initial)<1e-6 or any(abs(contrast(center**i)-initial)>1e-12 for i in (1,2)):
        raise ValueError("Center invariance of synthetic D4")
    return float(initial)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    out=parser.parse_args().output
    out.mkdir(exist_ok=True,parents=True)
    for path,sha in original.CFG["baseline_sha256"].items():
        if hashlib.sha256((original.ROOT/path).read_bytes()).hexdigest()!=sha:
            raise ValueError("Changed source "+path)
    features=feature_screen(out)
    rows,roots=spectral_run(80)
    repeat,other=spectral_run(100)
    if not roots or roots!=other:
        raise ValueError("Root repeat")
    with mp.workdps(70):
        for a,b in zip(rows,repeat,strict=True):
            if abs(mp.mpf(a["ratio_b12"])-mp.mpf(b["ratio_b12"]))>mp.mpf("1e-21"):
                raise ValueError("Spectral precision repeat")
    write_csv(out/"spectrum.csv",rows)
    panel(out)
    stable=np.ones((3,5))
    resolved=stable.copy()
    resolved[:,3]+=2e-6
    drift=stable.copy()
    drift[0,:]*=1.01
    cases=[t3_decision(a) for a in (stable,resolved,drift)]
    if cases!=["BELOW_NUMERICAL_FLOOR","RESOLVED","FAIL_CONVERGENCE"]:
        raise ValueError("T3 decision control")
    summary=dict(scope="SOFTWARE_AND_CONDITIONAL_CONTROLS",features=features,
                 sign_change_brackets_roots_u2=roots,budget=budget(),T3_controls=cases,
                 synthetic_D4_center_invariance= center_control())
    (out/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    main()
