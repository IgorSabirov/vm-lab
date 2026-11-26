#!/usr/bin/env python3
"""Audit the full R150 network-bench contact matrix against pure hopping."""
from __future__ import annotations
import json
import math
import numpy as np

def contact_matrix(N, lam_over_J, antiperiodic):
    L=N+1
    step=np.zeros((L,L),dtype=float)
    step[1,1]=1.0
    cycle=[0,*range(2,L)]
    sign=-1.0 if antiperiodic else 1.0
    for a,b in zip(cycle,cycle[1:]+cycle[:1]):
        step[b,a]=sign if b==0 else 1.0
    C=np.diag([1.0,1.0]+[0.0]*(L-2))
    return step+step.T+lam_over_J*C

def log_partition(N,T_over_J,lam_over_J,antiperiodic):
    eig=np.linalg.eigvalsh(contact_matrix(N,lam_over_J,antiperiodic))
    top=float(eig[-1])
    return top/T_over_J+math.log(float(np.exp((eig-top)/T_over_J).sum()))

def delta_f_over_J(N,T_over_J,lam_over_J):
    return T_over_J*(log_partition(N,T_over_J,lam_over_J,False)
                     -log_partition(N,T_over_J,lam_over_J,True))

def zero_temperature_gap(N,lam_over_J):
    ep=np.linalg.eigvalsh(contact_matrix(N,lam_over_J,False))[-1]
    ea=np.linalg.eigvalsh(contact_matrix(N,lam_over_J,True))[-1]
    return max(0.0,float(ep-ea))

def golden_max(fn,lo,hi,iterations=240):
    gr=(math.sqrt(5.0)-1.0)/2.0
    c=hi-gr*(hi-lo); d=lo+gr*(hi-lo)
    fc,fd=fn(c),fn(d)
    for _ in range(iterations):
        if fc>fd:
            hi,d,fd=d,c,fc
            c=hi-gr*(hi-lo); fc=fn(c)
        else:
            lo,c,fc=c,d,fd
            d=lo+gr*(hi-lo); fd=fn(d)
    x=.5*(lo+hi)
    return x,fn(x)

def peak(N,lam_over_J):
    log_t,finite_peak=golden_max(
        lambda z:delta_f_over_J(N,math.exp(z),lam_over_J),-18.0,2.0)
    zero_gap=zero_temperature_gap(N,lam_over_J)
    at_zero=zero_gap>=finite_peak-1e-8
    return {"N":N,"lambda_over_J":lam_over_J,
            "sup_DF_over_J":max(zero_gap,finite_peak),
            "supremum_location":"T_to_0_limit" if at_zero else "finite_T",
            "finite_search_max_DF_over_J":finite_peak,
            "zero_T_top_gap_over_J":zero_gap,
            "finite_search_argmax_T_over_J":math.exp(log_t)}

def bisect(fn,lo,hi,iterations=180):
    flo=fn(lo)
    for _ in range(iterations):
        mid=.5*(lo+hi); fm=fn(mid)
        if flo*fm<=0: hi=mid
        else: lo,flo=mid,fm
    return .5*(lo+hi)

def pure_contrast(N,J,T):
    def z(alpha):
        return 1.0+sum(math.exp(-4.0*J/T*math.sin(math.pi*(k+alpha)/N)**2)
                       for k in range(N))
    return 1.0-z(.5)/z(0.0)

def full_contrast(L,J,T,lam):
    N=L-1; v=lam/J
    lp=log_partition(N,T/J,v,False)
    la=log_partition(N,T/J,v,True)
    return 1.0-math.exp(la-lp)

def target_x(L,target):
    N=L-1
    def contrast_x(x):
        z0=1.0+sum(math.exp(-2*x*math.sin(math.pi*k/N)**2) for k in range(N))
        zh=1.0+sum(math.exp(-2*x*math.sin(math.pi*(k+.5)/N)**2) for k in range(N))
        return 1.0-zh/z0
    return bisect(lambda x:contrast_x(x)-target,1e-10,1e4)

def periodic_cycle_root(N,v):
    f=lambda k:math.cos(N*k)-v*math.sin(N*k)/(2*math.sin(k))-1.0
    return bisect(f,1e-12,math.pi/N-1e-12)

def run():
    TREF=.07251310823341744
    lam=-.1*TREF
    J_E2=.1185
    J_L7=target_x(7,.4)*TREF/2.0
    v_E2=lam/J_E2
    peak_rows=[peak(N,v) for v in (0.0,v_E2,-v_E2)
               for N in (2,6,14,30,60)]
    gap_rows=[]
    for N in (14,30,60,100,200,500,1000,2000,5000):
        k=periodic_cycle_root(N,v_E2)
        gap=2*math.cos(k)-2*math.cos(math.pi/N)
        gap_rows.append({"N":N,"k_periodic":k,"top_gap_over_J":gap,
                         "N3_top_gap_over_J":gap*N**3})
    checks={
        "matrix_hermiticity_residual":max(
            float(np.max(np.abs(contact_matrix(N,v_E2,a)
                                -contact_matrix(N,v_E2,a).T)))
            for N in (2,6,14,30,60) for a in (False,True)),
        "lambda_zero_matches_pure_hopping_N6_80keV":abs(
            full_contrast(7,J_E2,.08,0.0)-pure_contrast(6,J_E2,.08)),
        "transfer_root_matches_dense_top_gap_N60":abs(
            (2*math.cos(periodic_cycle_root(60,v_E2))-2*math.cos(math.pi/60))
            -zero_temperature_gap(60,v_E2))
    }
    return {
        "schema":"r150-full-contact-audit-v1",
        "status":"FINITE_MATRIX_AUDIT_REPRODUCED; LARGE_N_SCALING_IS_NUMERICAL_WITH_ASYMPTOTIC_DERIVATION",
        "source_definition":{
            "source":"analysis/R150_THREE_GENERATIONS/floquet/phase_bbn/network_bench/graph.py",
            "step":"signed permutation on cycle [0,2,...,L-1] plus fixed state 1",
            "C":"diag(1,1,0,...,0), one contact on fixed state and one on cycle vertex 0",
            "matrix":"A_phi = step_phi + step_phi.T + (lambda/J) C",
            "partition":"Z_phi = Tr exp(A_phi/(T/J)); common normalization cancels in ratios"},
        "bench_parameters":{
            "TREF_MeV":TREF,"lambda_default_MeV":lam,"J_E2_MeV":J_E2,
            "lambda_over_J_E2":v_E2,"J_L7_isocontrast_target_0p4_MeV":J_L7,
            "lambda_over_J_L7_isocontrast":lam/J_L7},
        "L7_contact_at_80keV":{
            "E2_J":{"pure_hopping_contrast":pure_contrast(6,J_E2,.08),
                    "full_contact_contrast":full_contrast(7,J_E2,.08,lam)},
            "L7_isocontrast_J":{"pure_hopping_contrast":pure_contrast(6,J_L7,.08),
                                "full_contact_contrast":full_contrast(7,J_L7,.08,lam)}},
        "L7_contact_at_TREF":{"L7_isocontrast_J":{
            "pure_hopping_contrast":pure_contrast(6,J_L7,TREF),
            "full_contact_contrast":full_contrast(7,J_L7,TREF,lam)}},
        "peak_table":peak_rows,
        "negative_contact_cycle_gap_asymptotic":gap_rows,
        "asymptotic_candidate":{
            "formula":"N^3 (E_top,periodic - E_top,antiperiodic)/J -> 8*pi^2/abs(lambda/J)",
            "predicted_limit":8*math.pi**2/abs(v_E2),
            "status":"DERIVED_FROM_SMALL_k_EXPANSION_OF_TRANSFER_MATRIX_QUANTIZATION; numerical convergence is slow"},
        "checks":checks}

if __name__=="__main__":
    print(json.dumps(run(),indent=2,sort_keys=True))
