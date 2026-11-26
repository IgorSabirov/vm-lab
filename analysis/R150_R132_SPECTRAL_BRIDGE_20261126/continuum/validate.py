#!/usr/bin/env python3
"""Regression against original graph.py construction and independent spectral cutoffs."""
import json
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from replay import dense, continuum, stat, PI

def original_matrix(L, sign, v):
    # Original contacts() graph construction at source commit 7d4f844b.
    step=np.zeros((L,L)); step[1,1]=1; cycle=[0,*range(2,L)]
    for a,b in zip(cycle,cycle[1:]+cycle[:1]):step[b,a]=sign if b==0 else 1.
    c=np.diag([1.,1.]+[0.]*(L-2))
    return step+step.T+v*c

def main():
    emax=0.; fmax=0.; cases=0
    for N in (2,4,6,14,30,60):
        for v in (-2,-.0611924964,0,.0611924964,2):
            for sign,p in ((1,0),(-1,PI)):
                a=original_matrix(N+1,sign,v)
                E=np.linalg.eigvalsh(N*N*(2*np.eye(N+1)-a))
                ep=dense(N,N*N*v,N*v,0,p)
                emax=max(emax,np.max(abs(E-ep)))
                for y in (.3,3,30):
                    fmax=max(fmax,abs(logsumexp(-E/y)-logsumexp(-ep/y)));cases+=1
    cutoff=0.; cutcases=0
    for u,g,h in [(1,2,0),(1,2,2),(5,5,2),(-2,3,2),(0,4,1)]:
        for p in (0,PI):
            for y in (.3,1,3,10,30):
                a=stat(continuum(u,g,h,p,18),y); b=stat(continuum(u,g,h,p,36),y)
                cutoff=max(cutoff,np.max(abs(a-b)));cutcases+=1
    zeros=[]
    for p,t in ((0,0),(PI,4)):
        for u,g in ((1,t+2),(5,t+3),(-2,t-3)):
            h=np.sqrt(u*(g-t));e=continuum(u,g,h,p)
            zeros.append(dict(phi=p,u=u,g=g,h=h,zero_res=min(abs(e))))
    assert emax<1e-8 and fmax<1e-8 and cutoff<1e-9 and max(x['zero_res'] for x in zeros)<1e-8
    data=dict(original_graph_thermal_cases=cases,max_spectrum_error=emax,max_logZ_error=fmax,cutoff_cases=cutcases,max_cutoff_delta=cutoff,zero_locus=zeros)
    Path(__file__).with_name('validation.json').write_text(json.dumps(data,indent=2)+'\n');print(data)
if __name__=='__main__':main()
