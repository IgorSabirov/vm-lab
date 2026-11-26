"""From the directory with the included R140 fixtures, run python experiments.py."""
import json
from collections import Counter, defaultdict
from fractions import Fraction as F
from itertools import product
from math import log2
import numpy as np
import sympy as sp
import previous as p
import check_h6 as h


def ring(n):
    eye=np.eye(n,dtype=int)
    t=np.roll(eye,-1,axis=0)
    d=t-eye
    source=-np.diag(np.diag(d))
    assert np.array_equal(d+source,t) and np.array_equal(source,eye)
    return d,t


def test_ports():
    total=0
    for n, alphabet in ((2,16),(3,16),(4,3),(5,3),(6,3)):
        _,t=ring(n)
        for w in product(range(alphabet),repeat=n):
            g=h.graph_ops['named'](w)
            a,b=(np.array(w)&mask for mask in (5,10))
            for _ in range(n):
                a=t@a
                g=h.graph_ops['transport'](g,2)
                assert tuple(a+b)==tuple(s for _,s in g)
                total+=1
            assert tuple(a+b)==w
    return total


def prob_info(positive,negative):
    return sum(0.5*x*log2(2*x/(a+b)) for a,b in zip(positive,negative)
               for x in [a,b] if x>0)


def timeline():
    # Independent columns for each logical arm at the cut; denominators doubled per step.
    arms=[]
    for arm in (False,True):
        state=p.geometry_step({p.start:[h.ONE,h.ZERO]})
        arms.append({g:(v[::-1] if arm else v) if (len(g)==2)==arm else [h.ZERO,h.ZERO] for g,v in state.items()})
    output=[]
    for step in range(1,9):
        if step>1:
            arms=[p.geometry_step(s) for s in arms]
            if step==2:
                for s in arms:
                    for g in s:
                        if len(g)==2:s[g]=s[g][::-1]
        named=[]; lens=defaultdict(lambda:[F(0)]*4)
        for g in arms[0]:
            va,vb=arms[0][g],arms[1][g]
            aa=sum(h.dot(v,v) for v in va); bb=sum(h.dot(v,v) for v in vb)
            cross=h.ZERO
            for a,b in zip(va,vb):
                cross=h.add(cross,h.mul((a[0],-a[1]),b))
            row=[F(n,4**step) for n in (aa+bb,2*cross[0],-2*cross[1],aa-bb)]
            named.append(row)
            lens[len(g)]=[a+b for a,b in zip(lens[len(g)],row)]
        # Equivalent to equal unit norms and orthogonal logical columns after normalization.
        assert list(map(sum,zip(*named)))==[1,0,0,0]
        order=sorted(lens)
        mat=sp.Matrix([lens[l] for l in order])
        plus=[float(lens[l][0]+lens[l][2]) for l in order]
        minus=[float(lens[l][0]-lens[l][2]) for l in order]
        output.append(dict(step=step,graphs=len(named),named_rank=sp.Matrix(named).rank(),
                           length_rank=mat.rank(),lengths=order,
                           length_coefficients=[[str(v) for v in lens[l]] for l in order],
                           info_pmY_bits=prob_info(plus,minus)))
    assert dict(zip(order,mat.tolist()))=={l:list(map(sp.Rational,r)) for l,r in p.by_length(p.effects()).items()}
    return output


def binary_test():
    all_rows=[]; examples=[]
    for n in range(2,9):
        d,_=ring(n); groups=defaultdict(list)
        for w in product(range(2),repeat=n):
            if w!=min(w[i:]+w[:i] for i in range(n)): continue
            def gram(word):
                pr=np.diag(word)
                b=pr@d@pr
                return sp.Matrix(b@b.T)
            k=gram(w)
            det=int((sp.eye(n)+k).det())
            counts=tuple(sum((w[i],w[(i+1)%n])==(a,b) for i in range(n)) for a,b in product(range(2),repeat=2))
            traces=[int((k**j).trace()) for j in range(1,n+1)]
            # Newton identities for the elementary symmetric functions.
            elem=[F(1)]
            for j in range(1,n+1):
                elem.append(sum((-1)**(r-1)*elem[j-r]*traces[r-1] for r in range(1,j+1))/j)
            assert sum(elem)==det
            assert (sp.eye(n)+gram(w[::-1])).det()==det
            groups[counts].append((''.join(map(str,w)),det,traces))
        collisions=[(c,vals) for c,vals in groups.items() if len({v[1] for v in vals})>1]
        all_rows.append([n,sum(map(len,groups.values())),len(collisions)])
        if collisions and not examples:
            examples=collisions
    match=[(v[0],v[1],v[2]) for _,vals in examples for v in vals]
    return dict(by_length=all_rows,first=match)


def path_quadric():
    records=[]
    for p0,k in product((3,5,7), range(2,7)):
        hist=Counter(sum(a*b for a,b in zip(x,x[1:]))%p0 for x in product(range(p0),repeat=k))
        # For a nontrivial character, the sum is hist[0]-hist[1] since all nonzero
        # fibers have the same size (multiply all even coordinates by a unit).
        r=k//2
        assert len({hist[j] for j in range(1,p0)})==1
        assert hist[0]-hist[1]==p0**(k-r)
        assert hist[0]==p0**(k-1)+(p0-1)*p0**(k-r-1)
        records.append([p0,k,r,hist[0],hist[1],hist[0]-hist[1]])
    return records


def walsh_paths():
    endlist=p.ends
    coeff=np.zeros((256,len(endlist),2),dtype=np.int64)
    for lengths,g,acts in h.exact_paths():
        code=sum((a=='flip')<<i for i,a in enumerate(acts))
        assert not np.any(coeff[code])
        coeff[code,endlist.index(g)]=h.amplitude(acts,(1,)*8)
    spectrum=coeff.copy()
    for j in range(8):
        width=1<<j
        blocks=spectrum.reshape(-1,2*width,len(endlist),2)
        a,b=blocks[:,:width].copy(),blocks[:,width:].copy()
        blocks[:,:width],blocks[:,width:]=a+b,a-b
    expected=(coeff**2).sum(axis=(0,2))
    assert np.array_equal((spectrum**2).sum(axis=(0,2)),256*expected)
    for mask,amps in enumerate(spectrum):
        state={p.start:h.ONE}
        for step in range(8):
            following=defaultdict(lambda:h.ZERO)
            for g,v in state.items():
                for action,target in h.moves(g):
                    factor=h.STEP[1][action]
                    if action=='flip' and mask&(1<<step):factor=h.mul((-1,0),factor)
                    following[target]=h.add(following[target],h.mul(factor,v))
            state=following
        assert np.array_equal(amps,np.array([state[g] for g in endlist]))
        assert (amps**2).sum()==h.DEN**2
    dist=Counter(str(F(int(row[19]@row[19]),h.DEN**2)) for row in spectrum)
    return dict(endpoint19=dict(dist),mean19=str(F(int(expected[19]),h.DEN**2)),
                checked_masks=256,checked_outputs=len(endlist))


def costs(last):
    rows=sp.Matrix([[sp.Rational(x) for x in row] for row in last['length_coefficients']])
    j=rows[:,1:]; gram=j.T*j
    singular=np.linalg.svd(np.array(j,float),compute_uv=False)
    record=[]; max_depth=-1
    eye=sp.eye(5); uniform=sp.ones(5)/5
    chan=9*eye/10+uniform/10
    for m in range(41):
        jm=chan**m*j
        assert jm==(sp.Rational(9,10)**m)*j
        bound=0.0005/(0.9**m*singular[-1])
        if bound<=0.1:max_depth=m
        noisy=chan**m*rows
        plus=[float(a+b) for a,b in zip(noisy[:,0],noisy[:,2])]
        minus=[float(a-b) for a,b in zip(noisy[:,0],noisy[:,2])]
        record.append([m,bound,prob_info(plus,minus)])
    assert uniform*j==sp.zeros(5,3) and (uniform*rows).rank()==1
    # Certify the crossing by exact Sylvester minors, not a float decision.
    def certified(m):
        mat=sp.Rational(9,10)**(2*m)*gram-sp.eye(3)*sp.Rational(1,200)**2
        return [str(mat[:k,:k].det()) for k in (1,2,3)]
    for m in [max_depth,max_depth+1]:
        positive=all(sp.Rational(x)>0 for x in certified(m))
        assert positive==(m==max_depth)
    return dict(gram=[[str(v) for v in row] for row in gram.tolist()],singular=singular.tolist(),
                max_depth=max_depth,bracket=[record[max_depth],record[max_depth+1]],
                gram_tests=[certified(max_depth),certified(max_depth+1)],samples=record)


if __name__=='__main__':
    t=timeline()
    print(json.dumps(dict(ports=test_ports(),time=t,binary=binary_test(),quadric=path_quadric(),
                          walsh=walsh_paths(),cost=costs(t[-1])),indent=2))
