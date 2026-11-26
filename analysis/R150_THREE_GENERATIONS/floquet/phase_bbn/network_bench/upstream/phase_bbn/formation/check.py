"""Finite two-boundary and reciprocal formation controls. All toy rates are dimensionless."""
import sys
from pathlib import Path
import json
import math
import numpy as np
from scipy.linalg import expm
from scipy.special import expit, logsumexp
from scipy.special import iv, zeta

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from word_rule import F_word, state_to_word, word_to_state

def graph(L, phi):
    if L < 3 or L % 2 == 0:
        raise ValueError("The self-reflected active layer requires odd L >=3")
    n = L-1
    order = [0,*range(2,L)]
    step = np.zeros((L,L),complex)
    step[1,1] = 1
    h = -1 if phi == np.pi else np.exp(1j*phi)
    for j,t in enumerate(order):
        step[order[(j+1)%n],t] = h if j==n-1 else 1
    u,v=(L+1)//2,(L-1)//2
    for t in range(L):
        w=state_to_word((t,u,(t+v)%L),L)
        out=F_word(w)
        t2,u2,last=word_to_state(out)
        assert len(out)==L and (u2,(last-t2)%L)==(u,v)
        assert abs(step[t2,t])==1
    phases = np.r_[0,(phi+2*np.pi*np.arange(n))/n]
    basis = np.zeros_like(step)
    basis[1,0] = 1
    for j,t in enumerate(order):
        basis[t,1:] = np.exp(-1j*j*phases[1:])/math.sqrt(n)
    assert np.allclose(step@basis,basis*np.exp(1j*phases))
    assert np.allclose(basis.conj().T@basis,np.eye(L))
    return step,basis,phases

def log_partition(L, phi, x):
    return float(logsumexp(x*np.cos(graph(L,phi)[2])))

def coherent_control(L):
    F,V,_=graph(L,0)
    G,_,_=graph(L,np.pi)
    n=L-1
    s,a=V[:,1],V[:,1+n//2]
    outcome = (F-G)/2
    source = np.zeros((L,L)); source[-1,-1]=1
    assert np.allclose(outcome.conj().T@outcome,source)
    forward = float(np.linalg.norm(outcome@s)**2)
    weights = [np.linalg.norm(outcome@p@s)**2 for p in (source,np.eye(L)-source)]
    return0 = float(abs(s.conj()@F@s)**2)
    returnpi = float(abs(s.conj()@G@s)**2)
    kernelpi = returnpi + float(abs(a.conj()@G@s)**2)
    assert np.isclose(forward,1/n) and np.isclose(returnpi,(1-2/n)**2)
    return dict(P_tag_minus=forward,P_early_edge_given_minus=float(weights[0]/sum(weights)),
                s_return_no_seam=return0,s_return_with_seam=returnpi,
                initial_kernel_weight_after_twist=kernelpi)

def chemical_control(L,x,phi,b):
    # Energies in units of T. b sets the bare binding drive including the reservoir.
    sectors=[graph(L,0),graph(L,phi)]
    E=np.concatenate([-x*np.cos(k[2])-d*b for d,k in enumerate(sectors)])
    generator=np.zeros((2*L,2*L))
    def pair(i,j,strength):
        generator[j,i]=strength*expit(E[i]-E[j])
        generator[i,j]=strength*expit(E[j]-E[i])
    interact=np.eye(L);interact[[0,1]]=interact[[1,0]]
    for d,(_,basis,_) in enumerate(sectors):
        transitions=np.abs(basis.conj().T@interact@basis)**2
        for i in range(L):
            for j in range(i+1,L):pair(d*L+i,d*L+j,transitions[j,i])
    overlap=np.abs(sectors[1][1].conj().T@sectors[0][1])**2
    for i in range(L):
        for j in range(L):pair(i,L+j,overlap[j,i])
    generator[np.diag_indices(2*L)]=-generator.sum(axis=0)
    eq=np.exp(-E-logsumexp(-E))
    flux=generator*eq
    assert np.allclose(flux,flux.T) and np.allclose(generator@eq,0)
    assert np.linalg.matrix_rank(generator,tol=1e-10)==2*L-1
    hazard=generator[L:,:L].sum(axis=0)
    prior=np.zeros(2*L)
    # Equal prior on the fixed state and the uniform long-cycle mode, both unbound.
    prior[0:2]=.5
    final_D=np.r_[np.zeros(L),np.ones(L)]
    evolution=expm(generator)
    assert np.allclose(evolution.sum(axis=0),1) and np.min(evolution)>-1e-13
    forward=evolution@prior
    h=evolution.T@final_D
    posterior=h*prior/(h@prior)
    assert np.isclose(h@prior,final_D@forward)
    assert np.allclose(evolution.T@(1-final_D)+h,1)
    equilibrium_ratio=math.exp(log_partition(L,phi,x)-log_partition(L,0,x))
    assert np.isclose(eq[L:].sum()/eq[:L].sum(),math.exp(b)*equilibrium_ratio)
    if phi==0:
        assert np.allclose(hazard,expit(b)) and np.allclose(posterior,prior)
    return dict(K_over_bare=equilibrium_ratio,initial_capture_hazards_fixed_uniform_alternating=
                [float(hazard[k]) for k in (0,1,1+(L-1)//2)],
                P_bound_after_one_unit=float(h@prior),
                prior_early_fixed=.5,posterior_early_fixed_given_bound=float(posterior[0]))

def center_control():
    # Embed one occupied channel in the actual two-channel graph rule.
    rotate={0:0,1:3,3:2,2:1}
    def G(w):return tuple(rotate[t] for t in w)
    w=(3,0,0)
    a,b=G(F_word(w)),F_word(G(w))
    assert len(a)!=len(b)
    return dict(w=w,GF=a,FG=b)

def overlap_controls(L=7,x=4):
    # Four allowed pairs (r,d). Periodic r=1 enables the three-mode graph sector.
    states=[(r,d) for r in (0,1) for d in (0,1)]
    graph_bias=log_partition(L,0,x)-log_partition(L,np.pi,x)
    def segment(g,gate_r,gate_d):
        g_to_r,g_to_d=(g,g) if np.isscalar(g) else g
        Q=np.zeros((4,4))
        for i,(r,d) in enumerate(states):
            j=states.index((1-r,d))
            Q[j,i]=gate_r*expit((1-2*r)*(graph_bias+g_to_r*d))
            j=states.index((r,1-d))
            Q[j,i]=gate_d*expit((1-2*d)*g_to_d*r)
        Q[np.diag_indices(4)]=-Q.sum(axis=0)
        if g_to_r==g_to_d:
            w=np.exp([graph_bias*r+g_to_r*r*d for r,d in states])
            assert np.allclose(Q*w,(Q*w).T)
        return expm(Q)
    prior=np.array([1.,0.,0.,0.])
    r,d=np.array(states,dtype=float).T
    def protocol(g,stages):
        p=prior
        for a,b in stages:p=segment(g,a,b)@p
        return np.array([r@p,d@p,p[-1]])
    out={}
    g=math.log(2.)
    for key,stages in [('overlap',[(1,1)]),('R_then_D',[(1,0),(0,1)]),
                       ('D_then_R',[(0,1),(1,0)])]:
        base=protocol(0,stages)
        coupled=protocol(g,stages)
        delta=coupled-base
        out[key]=dict(uncoupled=base.tolist(),coupled=coupled.tolist(),delta=delta.tolist())
    assert abs(out['R_then_D']['delta'][0])<1e-12
    assert abs(out['D_then_R']['delta'][1])<1e-12
    assert min(out['overlap']['delta'][:2])>0
    # Directional ablations are driven controls; only the common-g model is equilibrium-consistent.
    coupled=protocol(g,[(1,1)])
    only_to_r=protocol((g,0),[(1,1)])
    only_to_d=protocol((0,g),[(1,1)])
    base=protocol(0,[(1,1)])
    assert np.isclose(only_to_r[1],base[1]) and np.isclose(only_to_d[0],base[0])
    out['directional_ablations']=dict(only_D_to_R=only_to_r.tolist(),only_R_to_D=only_to_d.tolist(),
                  both_minus_single_effects=(coupled-only_to_r-only_to_d+base).tolist())
    # R then D: conditioning alone can change the inferred EARLIER R marginal.
    mid=segment(g,1,0)@prior
    backward=segment(g,0,1).T@d
    p_final=backward@mid
    out['R_then_D_mid_R']=dict(marginal=float(r@mid),
                 conditioned_final_D=float((r*mid)@backward/p_final),
                 conditioned_final_unbound=float((r*mid)@(1-backward)/(1-p_final)))
    assert np.isclose(p_final*out['R_then_D_mid_R']['conditioned_final_D']
                      +(1-p_final)*out['R_then_D_mid_R']['conditioned_final_unbound'], r@mid)
    return out


def thermal_phase_control():
    # Shared z=-i followed by exp(-i gamma P_--), in interaction coordinates.
    # The selected simultaneous split/merge has single-channel lengths 6 and 8.
    values=[]
    for gamma in (0.,np.pi/2,np.pi):
        c=(np.exp(-1j*gamma)-1)/4
        amps=np.array([(1-1j)/2+c,-c,-c,(1+1j)/2+c])
        prob=np.abs(amps)**2
        assert np.isclose(prob.sum(),1.)
        variance=float(prob[1]+prob[2])
        assert np.isclose(variance,.5*np.sin(gamma/2)**2)
        values.append(variance)
    return values


def main():
    table={}
    for L in (3,7,9,15):
        N=L-1
        for x in (1,4,8):
            z0,zp=[math.exp(log_partition(L,p,x)) for p in (0,np.pi)]
            diff=4*N*sum(iv(m*N,x) for m in range(1,32,2))
            assert math.isclose(z0-zp,diff,rel_tol=1e-8,abs_tol=4e-11)
            table[f'L{L}_x{x}']=zp/z0
    return {'length_variance_0_halfpi_pi':thermal_phase_control(),
            'binding_energy_budget':60*float(zeta(3))/math.pi**4*6.1e-10*8/(3.36*.08),
            'overlap_protocols':overlap_controls(),'coherent':coherent_control(7),'mass_basis':'fixed, uniform cycle, alternating cycle',
            'thermal':{f'phi_{name}':chemical_control(7,4,p,0) for name,p in [('zero',0),('pi',np.pi)]},
            'partition_ratios':table,'center_counterexample':center_control()}

if __name__=='__main__':
    print(json.dumps(main(),indent=2))
