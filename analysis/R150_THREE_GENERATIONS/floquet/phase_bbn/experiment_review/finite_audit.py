"""E1–E4 and E6 controls on the published R150 files; R150_BENCH points to network_bench."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import numpy as np
from scipy.linalg import null_space, orth
from scipy.special import expit

BENCH=Path(os.environ['R150_BENCH']).resolve()
sys.path.insert(0,str(BENCH.parent/'formation'))
from check import graph
from word_rule import F_word, state_to_word, word_to_state
sys.path.insert(0,str(BENCH))
from graph import target_x
T=.08
HBAR=6.582119569e-22
H=1.66*math.sqrt(3.36)*T*T/(1.22089e22*HBAR)


def operator_rows():
    rows=[]
    for L in range(3,16,2):
        events=[]
        companion=[]
        for t in range(L):
            w=state_to_word((t,(L+1)//2,(t+(L-1)//2)%L),L)
            out=word_to_state(F_word(w))
            if any((s,w[(i+1)%L])==(8,4) for i,s in enumerate(w)):
                events.append(('merge',t,out[0]))
            if 12 in w: events.append(('split',t,out[0]))
            if 3 in w: companion.append(('split_first',t,out[0]))
            if any((b,w[(i+1)%L])==(1,2) for i,b in enumerate(w)):
                companion.append(('merge_first',t,out[0]))
        assert events==[('merge',0,2),('split',1,1)]
        assert companion==[('split_first',0,2),('merge_first',1,1)]
        F,V,p=graph(L,0)
        G,W,q=graph(L,np.pi)
        D=np.diag([1.,1.]+[-1.]*(L-2))
        A=np.zeros_like(F)
        A[2,0]=1.
        rule=F-2*A
        np.testing.assert_allclose(D@rule@D,G,atol=1e-14)
        Wrule=D@W
        np.testing.assert_allclose(rule@Wrule,Wrule*np.exp(1j*q),atol=1e-13)
        C=A+A.T
        for label,x in [('x4',4),('one_percent',target_x(L,.01))]:
            E=-x*np.cos(p)
            Ep=-x*np.cos(q)
            bath=expit(E-Ep[:,None])
            def h(B,op):
                return (abs(B.conj().T@op@V)**2*bath).sum(axis=0)
            np.testing.assert_allclose(h(Wrule,C),h(W,D@C),atol=1e-14)
            np.testing.assert_allclose(h(Wrule,A),h(W,D@A),atol=1e-14)
            picks=[0,1,1+(L-1)//2]
            values={}
            for name,B,op in [('symmetric_closing',W,C),('symmetric_rule',Wrule,C),('directed_rule',Wrule,A)]:
                hh=h(B,op); values[name]={'h':hh[picks].tolist(),'sum':hh.sum(),'strength_uniform':float((abs(B.conj().T@op@V[:,1])**2).sum())}
            J=x*T/2
            record={'L':L,'events':events,'simultaneous_first_channel':companion,'scale':label,'x':x,'J_MeV':J, 'vertices':values,'band_bound_MeV':4*J}
            # An inverse estimate ONLY under the attempt-frequency and extra attenuation hypotheses.
            record['inverse_E_MeV']={key:T*math.log(J/HBAR*val['h'][1]/H) for key,val in values.items()}
            rows.append(record)
    return rows


def gauss_counterexample():
    """Three sites and links. Basis bits 0..2 encode matter occupancy, 3..5 encode link Z."""
    I=np.eye(64)
    def flip(j): return I[:,np.arange(64)^(1<<j)]
    def z(j): return np.diag([1-2*((int(i)>>j)&1) for i in range(64)])
    X=[flip(3+i) for i in range(3)]
    Z=[z(3+i) for i in range(3)]
    gens=[z(i)@X[i]@X[(i-1)%3] for i in range(3)]
    W=Z[0]@Z[1]@Z[2]
    bare=np.zeros_like(I)
    for i in range(64):
        if (i&1) != ((i>>1)&1): bare[i^3,i]=1
    hop=bare@Z[0]
    proj=I.copy()
    for g in gens:
        proj=proj@(I+g)/2
        for op in (hop,X[0]): np.testing.assert_array_equal(op@g,g@op)
    np.testing.assert_array_equal(hop@W,W@hop)
    np.testing.assert_array_equal(X[0]@W,-W@X[0])
    return {'physical_dimension':np.linalg.matrix_rank(proj).item(),
            'physical_hop_rank':np.linalg.matrix_rank(proj@hop@proj).item(),
            'physical_link_flip_rank':np.linalg.matrix_rank(proj@X[0]@proj).item()}


def profiles():
    rr=BENCH/'results'
    x=np.loadtxt(rr/'binding_response.csv',delimiter=',',skiprows=1)
    t=x[:,0]; m=x[:,1:].T; d=m[1:2]; q=null_space(d)
    A=m[[0,2,3]]@q
    P=orth(A.T); hot=np.eye(10)[:,[3,4,5]]
    # Exact D/H matching inside the three-knot space leaves two directions.
    B=hot@null_space(d@hot)
    cos=np.linalg.svd(P.T@q.T@B,compute_uv=False)
    def case(name):
        return np.genfromtxt(rr/(name+'.csv'),delimiter=',',names=True)
    def profile(name):
        a=case(name)
        return np.interp(np.log(t),np.log(a['Tgamma_MeV'][::-1]),a['deltaBD_MeV'][::-1])
    direct=profile('direct')
    examples={}
    for name in ['coupled','mediated','algebraic_feedback','fast_feedback']:
        vec=profile(name)
        # Remove the physically declared direct amplitude, then restrict to the D-matched subspace.
        scale=(d@vec).item()/(d@direct).item()
        delta=vec-scale*direct; y=q.T@delta
        examples[name]={'linear_fit':scale,'eta':float(np.linalg.norm(P.T@y)**2/(y@y)),
                        'delta_ln_y':(m@delta).tolist()}
    c=case('coupled'); med=case('mediated')
    time_axis,Tgrid=c['background_t_s'],c['Tgamma_MeV']
    t1,t2=np.interp([.7,.08],Tgrid[::-1],time_axis[::-1])
    tt=np.r_[t1,time_axis[(time_axis>t1)&(time_axis<t2)],t2]
    temp=np.interp(tt,time_axis,Tgrid)
    actual_rates=np.interp(tt,time_axis,c['Gamma_r_reference_s_inv'])
    # Calibrate one Arrhenius example to the archived H at 80 keV.
    # Its integrated relaxation exponent is a conditional illustration.
    H80=np.interp(.08,Tgrid[::-1],c['H_s_inv'][::-1])
    lograte=math.log(H80)+4.*(1/.08-1/temp)
    overlap={'time_at_700_and_80_keV_s':[t1,t2],
             'relaxation_exponent_bare_graph':np.trapezoid(actual_rates,tt),
             'relaxation_exponent_tau50':(t2-t1)/50.,
             'relaxation_exponent_activated4':np.trapezoid(np.exp(lograte),tt)}

    np.testing.assert_array_equal(c['Tgamma_MeV'],med['Tgamma_MeV'])
    dp=c['p_periodic']-med['p_periodic']
    aux={}
    for nm in ('direct','mediated','coupled','refit_direct'):
        arr=case(nm)
        aux[nm]={str(pt):[float(np.interp(pt,arr['Tgamma_MeV'][::-1],arr[k][::-1]))
                           for k in ('drive_MeV','deltaBD_MeV','p_periodic')] for pt in (.7,.08)}
    # Uniform B change: derivative on archived finite-difference (also stored half-step).
    records=json.loads((rr/'paired_runs.json').read_text())
    y=records['off']['result']['Yp']
    summary=json.loads((rr/'analysis.json').read_text())
    return {'hot_principal_cosines_squared':(cos*cos).tolist(),'hot_mean_eta':float(np.mean(cos*cos)), 'overlap':overlap,
            'profiles':examples,'uniform_BD_lever_Yp_per_keV':m[0].sum()*y*.001,
            'uniform_direct_Yp_per_keV':summary['uniform_central_per_MeV'][0]*y*.001,
            'half_uniform_direct_Yp_per_keV':summary['half_uniform_central_per_MeV'][0]*y*.001,
            'max_graph_p_coupled_minus_mediated':float(np.max(abs(dp))),
            'T_at_max_MeV':float(c['Tgamma_MeV'][np.argmax(abs(dp))]),
            'feedback_interaction_ln':summary['feedback_interaction_ln'],'temperatures':aux}


if __name__=='__main__':
    print(json.dumps(dict(vertices=operator_rows(),gauss=gauss_counterexample(),profiles=profiles()),indent=2))
