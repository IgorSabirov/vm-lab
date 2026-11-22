"""Independent finite-graph, circle-translation, and single-spectrum discrimination controls."""
from collections import defaultdict
from itertools import product
import math

import numpy as np
from scipy.stats import rankdata


def ring_block_det(length):
    # Gram block for a run of ones: diagonal 1,2,...,2 and off-diagonals -1.
    last, current = 1,2
    for _ in range(1,length):
        last,current = current,3*current-last
    return current


def rings(n):
    groups=defaultdict(set)
    necklaces=0
    for chars in product('01',repeat=n):
        w=''.join(chars)
        if '0' not in w or '1' not in w or min(w[i:]+w[:i] for i in range(n))!=w:
            continue
        necklaces+=1
        pivot=w.index('0')
        runs=[len(run) for run in (w[pivot:]+w[:pivot]).split('0') if run]
        ones=sum(runs)
        pairs=ones-len(runs)
        groups[ones,pairs].add(math.prod(ring_block_det(length) for length in runs))
    return dict(nonconstant_necklaces=necklaces, distinct_averaged_matrices=len(groups),
                averaging_groups_with_distinct_dets=sum(len(g)>1 for g in groups.values()),
                max_distinct_dets_in_group=max(map(len,groups.values())))


def translation(n):
    # Exact fractional translations exist in the finite Fourier space of this circle.
    x=2*np.arange(n)/n-1
    k=2*np.pi*np.fft.fftfreq(n,d=2/n)
    centers=np.log([2,3,5,7])-1
    delta=.037
    def coefficients(shifts):
        d=(x[:,None]-centers-shifts+1)%2-1
        psi=np.exp(-d*d/(2*.05**2)) @ np.sqrt(np.log([2,3,5,7]))
        return np.fft.fft(psi)/np.sqrt(n)/np.linalg.norm(psi)
    def eig(c):
        return np.linalg.eigvalsh(np.diag(k)+np.outer(c,c.conj()))
    base=coefficients(np.zeros(4))
    spectrum=eig(base)
    errors={}
    for name, shifted in [('joint_unitary',base*np.exp(-1j*k*delta)),
                          ('joint_resampled',coefficients(np.full(4,delta))),
                          ('attachment_delta_0_37cell',coefficients(np.full(4,.37*2/n))),
                          ('only_p2_resampled',coefficients([delta,0,0,0]))]:
        errors[name]=float(np.max(np.abs(eig(shifted)-spectrum)))
    return errors


def circular_gap_power(samples=400, n=48):
    """One independent circular spectrum per draw; windows within a draw are nested."""
    rng=np.random.default_rng(141022)
    scores=np.empty((2,samples,4))
    for i in range(samples):
        z=rng.normal(size=(n,n))+1j*rng.normal(size=(n,n))
        q,r=np.linalg.qr(z)
        u=q*(np.diag(r)/abs(np.diag(r)))
        for beta,matrix in enumerate((u.T@u,u)):
            angles=np.sort(np.angle(np.linalg.eigvals(matrix)))
            gaps=np.diff(np.r_[angles,angles[0]+2*np.pi])*n/(2*np.pi)
            gaps=np.roll(gaps,rng.integers(n))
            ratios=np.minimum(gaps,np.roll(gaps,-1))/np.maximum(gaps,np.roll(gaps,-1))
            # One gap: use closeness to mean spacing. Other columns use adjacent ratios.
            scores[beta,i]=[-abs(gaps[0]-1),*[np.mean(ratios[:m]) for m in (3,11,35)]]
    def auc(a,b):
        m=len(a)
        return (rankdata(np.r_[a,b])[m:].sum()-m*(m+1)/2)/(m*m)
    aucs=[]
    for i in range(4):
        a,b=scores[:,:,i]
        # Bootstrap complete pairs of spectra, preserving their shared Haar source.
        boots=[]
        for _ in range(300):
            idx=rng.integers(samples,size=samples)
            boots.append(auc(a[idx],b[idx]))
        aucs.append([auc(a,b),*np.quantile(boots,[.025,.975])])
    return dict(N=n, draws_per_law=samples, window_gaps=[1,4,12,36], auc_CI95=aucs)


def controls():
    return dict(rings={str(n):rings(n) for n in (6,8,10,12,14)},
                translation_delta=.037, translation={str(n):translation(n) for n in (31,63,127,255)},
                circular_gap_power=circular_gap_power())
