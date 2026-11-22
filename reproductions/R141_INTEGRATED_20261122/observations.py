"""Finite spectral readings and the fate of state information after a partial record."""
from ast import literal_eval
from hashlib import sha256
import json

import numpy as np
import sympy as sp


def zeros(path):
    raw=path.read_bytes()
    assert sha256(raw).hexdigest()=='c3ea7085b25c16caafb43db250efefd171b627a34c3097498027751226d61c28'
    rows=json.loads(raw)['roots']
    assert [r['n'] for r in rows]==list(range(1,658))
    t=np.array([float(r['gamma']) for r in rows])
    assert np.all(np.diff(t)>0)
    u=t/(2*np.pi)*(np.log(t/(2*np.pi))-1)+7/8
    gaps=np.diff(u[60:])
    rng=np.random.default_rng(141657)
    sizes=(4,12,36)
    def stat(g):
        return np.mean(np.minimum(g[...,1:],g[...,:-1])/np.maximum(g[...,1:],g[...,:-1]),axis=-1)
    reference=np.empty((2,600,len(sizes)))
    for i in range(reference.shape[1]):
        z=rng.normal(size=(48,48))+1j*rng.normal(size=(48,48))
        q,r=np.linalg.qr(z)
        unitary=q*(r.diagonal()/abs(r.diagonal()))
        for law,mat in enumerate([unitary.T@unitary,unitary]):
            angles=np.sort(np.angle(np.linalg.eigvals(mat)))
            g=np.roll(np.diff(np.r_[angles,angles[0]+2*np.pi]),rng.integers(48))
            reference[law,i]=[stat(g[:m]) for m in sizes]
    results={}
    for j,m in enumerate(sizes):
        n=len(gaps)//m
        observed=stat(gaps[:n*m].reshape(n,m))
        ref=reference[:,:,j]
        results[str(m)]=dict(nonoverlap_windows=n,unused_gaps=len(gaps)-n*m,
            observed_window_median=float(np.median(observed)),all_windows=observed.tolist(),
            single_window_reference_q05_q50_q95=np.quantile(ref,[.05,.5,.95],axis=1).T.tolist(),
            paired_source_auc=float((ref[1,:,None]>ref[0,None,:]).mean()))
    return dict(first_index=61,last_index=657,unfolding='smooth Riemann-von Mangoldt, leading term',
                reference_order=['COE','CUE'],circle_order=48,draws_per_law=600,windows=results)


def operators(corpus_path):
    from corpus import by_length, effects, length_filters, ring, ring_filters
    frozen=json.loads((corpus_path/'spectral/corpus.json').read_text())
    assert ring_filters(sp.Symbol('t'))==frozen['rings'] and length_filters()==frozen['lengths']
    operators={}
    for n in (6,12,24,48):
        d,shift=ring(n)
        j=np.arange(n)
        k=np.fft.fftfreq(n)*n
        U=np.exp(2j*np.pi*np.outer(j,k)/n)/np.sqrt(n)
        phase=np.exp(2j*np.pi*k/n)
        residuals=[]
        separation=[]
        for base in ['010111','011011']:
            p=np.diag(np.array(list(map(int,base*(n//6)))))
            b=p@d@p
            phat=U.conj().T@p@U
            bhat=phat@np.diag(phase-1)@phat
            gram=b@b.T
            transformed=bhat@bhat.conj().T
            residuals.append(float(np.linalg.norm(U.conj().T@gram@U-transformed,2)))
            separation.append(np.linalg.slogdet(np.eye(n)+gram)[1])
        shift_error=np.linalg.norm(U.conj().T@shift@U-np.diag(phase),2)
        assert max(residuals+[shift_error])<1e-11
        operators[str(n)]=dict(shift_error=shift_error,compressed_gram_errors=residuals,
                               logdet_difference=separation[0]-separation[1])
    from corpus import ROOT
    W=sp.Matrix([[sp.Rational(1,j)**n for n in range(1,6)] for j in (2,3,4)])
    readings=by_length(effects())
    coherent=W*sp.Matrix([readings[n] for n in range(1,6)])[:,1:]
    joint=json.loads((ROOT/'donor_replay/followup.json').read_text())['intermediate']['effects_joint']
    marked=sp.zeros(5,4)
    for key,row in joint.items():
        _,n=literal_eval(key)
        marked[n-1,:]+=sp.Matrix([[sp.Rational(x) for x in row]])
    recorded=W*marked[:,1:]
    lam=sp.Symbol('p')
    mixed=(1-lam)*coherent+lam*recorded
    out={}
    for p in map(sp.Rational,('0','1/2','9/10','99/100','1')):
        matrix=mixed.subs(lam,p)
        out[str(p)]=dict(rank=matrix.rank(),singular_values=np.linalg.svd(np.asarray(matrix,float),compute_uv=False).tolist())
    assert out['0']['rank']==3 and out['1']['rank']==2 and recorded[:,0]==sp.zeros(3,1)
    return dict(finite_fourier_intertwiner=operators,mixture_determinant=str(sp.factor(mixed.det())),
                record_probability=out,exact_fixture=frozen)
