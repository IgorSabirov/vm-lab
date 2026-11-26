"""Exact geometry tests for the masked difference operator and its counting model."""
from collections import defaultdict
from functools import cache
from itertools import product
from math import comb, gcd, prod
import numpy as np
import sympy as sp

@cache
def fib(n):
    return n if n<2 else fib(n-1)+fib(n-2)

def luc(n):
    return fib(n-1)+fib(n+1)

def runs(w):
    i=w.index(0)
    return [len(r) for r in ''.join(map(str,w[i:]+w[:i])).split('0') if r]

def det_integer(matrix):
    """Fraction-free Bareiss for positive definite integral Gram matrices."""
    a=np.array(matrix,dtype=object)
    last=1
    for k in range(len(a)-1):
        pivot=a[k,k]
        assert pivot
        a[k+1:,k+1:]=(pivot*a[k+1:,k+1:]-a[k+1:,k,None]*a[k,None,k+1:])//last
        last=pivot
    return int(a[-1,-1])

def ring(w, links):
    n,m=len(w),len(links[0])
    s=np.zeros((n*m,n*m),dtype=int)
    for k,g in enumerate(links):
        j=(k+1)%n
        s[k*m:(k+1)*m,j*m:(j+1)*m]=g
    p=np.repeat(w,m)
    b=(s-np.eye(n*m,dtype=int))*p[:,None]*p[None,:]
    return det_integer(np.eye(n*m,dtype=int)+b@b.T)

def seam():
    I=np.eye(3,dtype=int);M=I[:,[1,2,0]];trials=0
    examples={}
    for n in range(3,9):
        for w in product(range(2),repeat=n):
            got=[ring(w,[I]*(n-1)+[h]) for h in (I,M,M.T)]
            if all(w):
                l=luc(2*n);expected=[(l-2)**3,(l-2)*(l+1)**2,(l-2)*(l+1)**2]
            else: expected=[prod(fib(2*k+1) for k in runs(w))**3]*3
            assert got==expected
            trials+=3
            word=''.join(map(str,w))
            if word in ('111111','011111','010111','011011'):examples[word]=got
    return {'masks':trials//3,'determinants':trials,'rows_I_M_Minv':examples}

def two_cycles():
    edges=((0,1),(1,2),(2,0),(0,3),(3,4),(4,0))
    rows={}
    for deleted in ((),(1,),(3,),(1,3)):
        kept=sorted(set(range(5))-set(deleted))
        values=[]
        for h1,h2 in product((1,-1),repeat=2):
            D=[]
            for (u,v),h in zip(edges,(1,1,h1,1,1,h2)):
                if u in kept and v in kept:
                    d=[0]*len(kept);d[kept.index(u)]=1;d[kept.index(v)]=-h;D.append(d)
            a=np.array(D,dtype=int)
            values.append(det_integer(np.eye(len(kept),dtype=int)+a.T@a))
        rows[str(deleted)]=values
    assert len(set(rows['(1, 3)']))==1
    assert rows['(1,)'][0]==rows['(1,)'][2]!=rows['(1,)'][3]
    return rows

@cache
def convolution(r,L,q,minimum):
    if r==0:return int(L==0)
    return sum(fib(2*k+1)**q*convolution(r-1,L-k,q,minimum)
               for k in range(minimum,L+1))

def combinatorics():
    ground={}
    for n in range(2,15):
        row=[]
        for cycle in (False,True):
            if cycle and n==2:continue
            bonds=[(i,(i+1)%n) for i in range(n if cycle else n-1)]
            count=0
            for down in product((0,1),repeat=n):
                spin=[1-2*x for x in down]
                E=sum(spin[a]*spin[b] for a,b in bonds)-2*sum(spin)
                pairs=sum(down[a]*down[b] for a,b in bonds)
                boundary=0 if cycle else down[0]+down[-1]
                base=-n if cycle else -n-1
                assert E==base+4*pairs+2*boundary
                count+=int(E==base)
            assert count==(luc(n) if cycle else fib(n))
            row.append(count)
        ground[n]=row
    cases=0
    for n in range(3,13):
        bins=defaultdict(int)
        for w in product((0,1),repeat=n):
            if not 0<sum(w)<n:continue
            ls=runs(w); L=sum(ls)
            for q in (1,2,3):
                bins[L,len(ls),q]+=prod(fib(2*l+1)**q for l in ls)
        for (L,r,q),count in bins.items():
            assert count*r==n*comb(n-L-1,r-1)*convolution(r,L,q,1)
            cases+=1
    z=sp.symbols('x')
    weak=tuple(convolution(3,L,1,0) for L in range(6))
    positive=tuple(convolution(3,L,1,1) for L in range(6))
    gf=(1-z)/(1-3*z+z*z)
    for minimum,f,expected in [(0,gf,weak),(1,gf-1,positive)]:
        coeff=sp.series(f**3,z,0,6).removeO().expand()
        assert tuple(coeff.coeff(z,i) for i in range(6))==expected
    return {'ising_degeneracies_open_ring':ground,'labelled_mask_bins':cases,
            'weak_r3':weak,'positive_r3':positive,'example_n6_L4_r2_q1':6*convolution(2,4,1,1)//2}

def alternating():
    checks={}
    for n in range(2,8):
        size=2*n; full=(1<<size)-1
        counts={};maximal=0;top=[]
        for mask in range(1<<size):
            right=(mask>>1)|((mask&1)<<(size-1))
            left=((mask<<1)&full)|(mask>>(size-1))
            if mask&right:continue
            k=mask.bit_count()
            counts[k]=counts.get(k,0)+1
            if (mask|right|left)==full:maximal+=1
            if k==n:top.append(mask)
        assert sum(counts.values())==luc(2*n) and len(top)==2
        assert set(top)=={sum(1<<i for i in range(j,size,2)) for j in (0,1)}
        assert ring([1]*n,[np.eye(1,dtype=int)]*(n-1)+[np.array([[-1]])])==luc(2*n)+2
        checks[n]={'maximum_size_sets':2,'maximal_by_inclusion':maximal,'total':sum(counts.values())}
    return checks
