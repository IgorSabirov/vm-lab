"""Checks for the R150/CCC+TL/BBN comparison. No network integration is invoked."""
from fractions import Fraction
from pathlib import Path
from cmath import exp
import json
import math
import numpy as np

from r150_extension import abs2, branches, layer
from word_rule import F_word, I_word, transport_word, canon_cycle

ROOT=Path(__file__).parent
def table():
    cases=json.loads((ROOT/'data/summary.json').read_text())['cases']
    out={}
    for solver in ('linx','primat'):
        base=cases['baseline'][solver]
        def response(case):
            r=cases[case][solver]
            return [100*(r[v]/base[v]-1) for v in ('Yp','D_H')]
        early,late=[np.asarray(response(x)) for x in ('early','late')]
        column_matrix=np.column_stack([early/.30,late/.55])
        k=early[0]/late[0]
        out[solver]=dict(early_pct=early.tolist(),late_pct=late.tolist(),
                         half_early_pct=response('early_half'),half_late_pct=response('late_half'),
                         response_slopes=column_matrix.tolist(),det=float(np.linalg.det(column_matrix)),
                         match_helium_linear=float(k),residual_D_pct_point=float((k*late-early)[1]))
    return out

def word_checks():
    outcomes={}
    for name,start in {'A':(0,0,15),'B':(0,6,9)}.items():
        keep={start}
        while True:
            images={canon_cycle(fn(w)) for w in keep for fn in [I_word,transport_word]}
            if images<=keep: break
            keep|=images
        states=sorted(keep); n=len(states)
        def perm(fn):
            M=np.zeros((n,n))
            for j,w in enumerate(states): M[states.index(canon_cycle(fn(w))),j]=1
            return M
        Q,I,F=map(perm,[transport_word,I_word,F_word])
        assert np.array_equal(F,Q@I)
        n0=n-np.linalg.matrix_rank(F-np.eye(n))
        npi=n-np.linalg.matrix_rank(F+np.eye(n))
        outcomes[name]=dict(states=states,n0=int(n0),npi=int(npi))
    assert (outcomes['A']['n0'],outcomes['A']['npi'])==(1,0)
    assert (outcomes['B']['n0'],outcomes['B']['npi'])==(2,1)
    laws=[]
    seed=layer(7,4)[1]
    for model in ('shared','factorized'):
        length_weights={l: Fraction(0) for l in (6,7,8)}
        for state, weight in branches(seed,model):
            length_weights[len(state)]+=Fraction(abs2(weight),4)
        laws.append(list(length_weights.values()))
    assert laws==[[0,1,0],[Fraction(1,4),Fraction(1,2),Fraction(1,4)]]
    outcomes['one_step_lengths']=[[str(x) for x in row] for row in laws]
    assert [sum(p*l for p,l in zip(w,(6,7,8))) for w in laws]==[7,7]
    assert [sum(p*(l-7)**2 for p,l in zip(w,(6,7,8))) for w in laws]==[0,Fraction(1,2)]
    return outcomes

def flavor():
    # Internal basis with two phase-zero states and one pi state.
    e=np.array([1,0,1])/np.sqrt(2)
    P=np.outer(e,e)
    out=[]
    for delta in (0,.7,math.pi):
        U=np.diag([1,1,exp(1j*delta)])
        thermal=np.eye(3)*.32
        assert np.allclose(U@thermal@U.conj().T,thermal)
        pop=np.trace(P@U@P@U.conj().T).real
        assert abs(pop-(1+math.cos(delta))/2)<1e-15
        out.append([delta,float(pop)])
    return out

def clocks():
    results=[]
    for f in (1.,3.,3.66):
        c=f; hbar=f**2; energy=f**2; H=1/f
        omega=c**4/(hbar*energy)
        assert abs(omega-1)<1e-12
        results.append(dict(f=f,universal_omega_over_H=(1/f)/H,
                            restored_dispersion_omega_over_H=omega/H))
    return results

def equilibrium():
    sh,sc,p=1.471,.2928,.01768
    r=sh/sc
    ax=lambda x:(1-x*(1-1/r))**(-1/3)
    return dict(r=r,rho_hot=sh-p,rho_cold=sc-p,a_end=ax(1),
                H_ini_dt_90=(ax(.9)**2-1)/2,H_ini_dt_end=(ax(1)**2-1)/2,
                xi_at_full_release=(.044518075411783944/1.175)**.25,
                eta_factor_4pct=1.04**(-.75))

if __name__=='__main__':
    print(json.dumps(dict(windows=table(),orbits=word_checks(),thermal_counterexample=flavor(),
                          clock_ratios=clocks(),equilibrium=equilibrium()),indent=2))
