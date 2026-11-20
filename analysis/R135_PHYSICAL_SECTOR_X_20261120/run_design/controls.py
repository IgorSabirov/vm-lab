"""Check design inputs and evaluate analytic/software controls only; print portable JSON."""
import hashlib
import importlib.util
import json
from fractions import Fraction
from math import exp, log, pi, sqrt
from pathlib import Path

import mpmath as mp
import numpy as np

from cumulants import combine, estimate, partitions
from measure_field import count_windows

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CFG = json.loads((HERE / "PROTOCOL.json").read_text())


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b, tol=1e-10):
    check(abs(a-b) <= tol, f"{a} != {b} (absolute tolerance {tol})")


def budget():
    inputs = CFG["budget_control"]
    energy, latent = inputs["delta_rho_Tgamma4"], inputs["latent_Tc4"]
    rho = inputs["s_hot_Tc3"] - inputs["p_Tc4"]
    k = 7/8*(4/11)**(4/3)
    c = 1/(k*pi**2/15)
    ref = json.loads((HERE/"LATE_TRANSFER.json").read_text())
    d, n0 = ref["heating"], ref["N_post"]
    delta = d*(1+k*n0)/k
    close(n0+delta, ref["N_pre"])
    close((1+d)**(-.75), ref["eta_CMB_over_eta_BBN"])
    close(d*(1+k*n0)*pi**2/15, energy)
    rows = []
    for eps in inputs["eps_grid"]:
        xi = (energy/(latent*eps))**.25
        rows.append(dict(eps=eps, xi_min=xi, late_equivalent=c*rho*xi**4))
    cap = inputs["illustrative_delta_N_cap"]
    return dict(rows=rows, early_coeff=120/(7*pi**2), late_coeff=c, delta_reservoir=delta,
                xi_max_example=(cap/(c*rho))**.25, eps_min_example=c*rho*energy/latent/cap,
                equivalent_residual_at_eps1=rows[0]["late_equivalent"]-delta)


def coordinates():
    p=CFG["T1"]
    def values(t):
        q=p["q0_model"]*exp(-t)
        x=(p["x0"]**4 + (p["q0_model"]**2-q*q)/1.2)**.25
        xc=sqrt((q+sqrt(q*q+4))/2)
        return log(x/xc), x, q
    low, high=p["root_interval"]
    check(values(low)[0] > 0 > values(high)[0], "Missing transverse crossing")
    for _ in range(60):
        mid=(low+high)/2
        if values(mid)[0]>0:
            low=mid
        else:
            high=mid
    t=(low+high)/2
    _,x,q=values(t)
    close(t,1.124782411,p["root_abs_tol"])
    cp=2.4*x**3
    xc_prime=x/(4*x*x-2*q)
    sigma=q*q/x
    direct=q*q/(2.4*x**4)+xc_prime*q/x
    close(direct,(sigma+cp*xc_prime*q/x)/cp)
    q_star=sqrt(1.2*(1.01**4-1))
    close(.6+.5*q_star**2, .6*1.01**4)
    check(0<q_star<1 and -(1-q_star)*q_star/2.4 < 0,"fixed-boundary control")
    engine=module_at("r130_engine",ROOT/"analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py")
    words=json.loads((HERE/p["words_source"]).read_text())["dynamics"]["cases"]["binary"]["words"]
    orbits=[]
    for w in words:
        z=engine.named(tuple(map(int,w)))
        trace=[]
        for i in range(p["orbit_steps"]+1):
            s=tuple(bit for _,bit in z)
            n=len(s)
            count=sum(all(s[(j+k)%n]==v for k,v in enumerate((2,1,2,1))) for j in range(n))
            trace.append([i,n,count])
            if i<p["orbit_steps"]:
                z=engine.forward(z,tuple(p["eps"]))
        orbits.append(trace)
    return dict(t_cross=t,x_cross=x,q_cross=q,dy_at_cross=direct,fixed_boundary_q=q_star,
                orbit_columns=["n","L","N2121"], orbits=orbits)


def spectrum():
    src=module_at("r132_moments",ROOT/"analysis/BH1_YANG_MILLS_COMPARISON_20261119/check_r131_r134_sector.py")
    for u in range(7):
        a,b=[src.moments([1 if t=="1" else u for t in w],6) for w in src.WORDS]
        check(a[:5]==b[:5] and a[5]-b[5]==6*(u-1)**4*(u+1)**2,"moment identity")
    check(108*src.entropy_coefficient(6)==Fraction(691,3225600),"entropy series")
    def differences(digits):
        with mp.workdps(digits):
            spectra=[]
            for w in src.WORDS:
                n=len(w)
                inc=mp.matrix(n)
                for i in range(n):
                    inc[i,i]=-1
                    inc[i,(i+1)%n]=1
                weights=mp.diag([1+(CFG["T2"]["u"]-1)*((int(a)>>1)&1) for a in w])
                eig=mp.eigsy(inc.T*weights*inc,eigvals_only=True)
                check(min(eig)>-mp.eps*1000,"Laplacian spectrum")
                spectra.append([mp.sqrt(max(v,0)) for v in eig])
            def entropy(freq,b):
                return 2*mp.fsum(mp.log(2*mp.cosh(b*v/2))-(b*v/2)*mp.tanh(b*v/2) for v in freq)
            return [float(entropy(spectra[0],b)-entropy(spectra[1],b)) for b in CFG["T2"]["finite_b"]]
    rows=differences(CFG["T2"]["precision_digits"])
    for u,v in zip(rows,differences(CFG["T2"]["high_precision_repeat"])):
        close(u,v,1e-22)
    return dict(b=CFG["T2"]["finite_b"], entropy_difference=rows, b12_at_u2="691/3225600")


def reader_checks():
    witnesses=json.loads((HERE.parent/"CHECKS.json").read_text())
    z=np.exp(2j*pi/3)
    close(estimate(np.ones(81, dtype=int))["connected_even"],0)
    check(len(set(partitions(range(4))))==15,"fourth cumulant partitions")
    connected=[]
    for pair in ("short","R131_24"):
        for row in witnesses[pair]["rows"]:
            field=np.broadcast_to((z**np.array(list(map(int,row["word"]))))[:,None,None], (len(row["word"]),4,4))
            measurement=count_windows(field,1)
            result=measurement["axes"]["x"]
            close(combine([measurement])["raw_even"],sum(measurement["axes"][a]["M_plus"] for a in "xyz")/(3*field.size))
            if pair=="R131_24":
                connected.append(estimate(result["counts"])["connected_even"])
            expected=row["delta_N2121_N1212_Mplus_Mminus"][-2:]
            check([result["M_plus"],result["M_minus"]]==[16*n for n in expected],"spatial orientation")
            check(count_windows(z*field,1)["axes"]["x"]["M_minus"]==result["M_minus"],"center symmetry")
            check(count_windows(field.conj(),1)["axes"]["x"]["M_minus"]==-result["M_minus"],"charge conjugation")
    for invalid in (0j, np.exp(1j*pi/3)):
        field=np.full((4,4,4),invalid)
        check(count_windows(field,1)["axes"]["x"]["accepted"]==0,"cut boundary")
    close(connected[0]-connected[1],2/24)
    return dict(status="PASS_SYNTHETIC_FIELDS",R131_longitudinal_connected_difference=connected[0]-connected[1])


def mixed():
    def output(q):
        return 1+q+q*q
    def four(values):
        a,b,c,d=values
        return output(d)-output(c)-output(b)+output(a)
    additive=[0,.1,.2,.3]
    full=[0,.1,.2,.32]
    for q in full:
        close((1-q)+q,1)
    close(four(additive),.04)
    close(four(full)-four(additive),.0324)
    return dict(additive=four(additive),full=four(full),residual=four(full)-four(additive))


def main():
    for path,sha in CFG["baseline_sha256"].items():
        check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,"Changed input: "+path)
    ids=set()
    for row in CFG["jobs"]:
        check(row["id"] not in ids and set(row["parents"])<=ids,"Invalid stage ordering")
        ids.add(row["id"])
    out=dict(protocol=CFG["version"],status="REFERENCE_CONTROLS_ONLY",
             budget=budget(),T1=coordinates(),T2=spectrum(),G4=reader_checks(),T3=mixed())
    print(json.dumps(out,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
