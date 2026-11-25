"""Integer Gaussian weights with common denominator 2**t, using the six D3 elements."""
from itertools import product
from collections import Counter
from pathlib import Path
import json
import sympy as sp
from reference_h6 import M,J,I,ref
from populations import scan

class NamedGraphs:
    """Intern atom/projection/join trees exactly. Cyclic order has no distinguished origin."""
    def __init__(self):
        self.nodes=[]; self.by_node={}
    def intern(self,node):
        if node not in self.by_node:
            self.by_node[node]=len(self.nodes); self.nodes.append(node)
        return self.by_node[node]
    def part(self,u,side):
        t=self.nodes[u]
        return t[1+side] if t[0]=='v' else self.intern((('l','r')[side],u))
    def join(self,x,y):
        a,b=self.nodes[x],self.nodes[y]
        return a[1] if a[0]=='l' and b[0]=='r' and a[1]==b[1] else self.intern(('v',x,y))
    def decode(self,u):
        t=self.nodes[u]
        return t if t[0]=='atom' else (t[0],*(self.decode(v) for v in t[1:]))
    def moves(self,g):
        pairs={(1,2):3,(8,4):12}
        split={k:v for v,k in pairs.items()};n=len(g)
        merge={i for i in range(n) if n>1 and (g[i][1],g[(i+1)%n][1]) in pairs}
        ends={(i+1)%n for i in merge};i=next(j for j in range(n) if j not in ends)
        out=[];k=0
        while k<n:
            u,b=g[(i+k)%n]
            if (i+k)%n in merge:
                v,c=g[(i+k+1)%n];out.append((self.join(u,v),pairs[b,c]));k+=2
            elif b in split:
                c,d=split[b];out.extend([(self.part(u,0),c),(self.part(u,1),d)]);k+=1
            else:out.append((u,b));k+=1
        def trans(x):
            return ref['cyclic'](tuple((self.join(self.part(u,1),self.part(v,0)),(b&10)|(c&5))
                                for (u,b),(v,c) in zip(x,x[1:]+x[:1])))
        idle,flip=trans(g),trans(out)
        return [(idle,2,0)] if idle==flip else [(idle,1,-1),(flip,1,1)]

def run(steps=20, check=None):
    graph=NamedGraphs()
    g=tuple((graph.intern(('atom',i)),x) for i,x in enumerate((1,2,0)))
    initial=[0]*12;initial[0]=1
    current={g:(initial,1)}
    basis=[J**p*M**k for p,k in product(range(2),range(3))]
    out=[]
    for t in range(1,steps+1):
        after={}
        for g,(amps,mask) in current.items():
            for h,a,b in graph.moves(g):
                row,mask2=after.get(h,([0]*12,0))
                length=len(h)
                for j in range(6):
                    p,k=divmod(j,3)
                    dest=3*(1-p)+k if length==3 else (3*p+(k+1-2*p)%3 if length==2 else j)
                    x,y=amps[2*j:2*j+2]
                    row[2*dest]+=a*x-b*y;row[2*dest+1]+=a*y+b*x
                next_mask=((mask&1)<<1)|((mask&2)>>1) if length==3 else mask
                after[h]=(row,next_mask|mask2)
        current=after
        # Ranks require only distinct weighted sums (denominator common); verify conservation per step.
        distinct={tuple(row) for row,_ in current.values()}
        real_rows=set(); herm_rows=set(); normalization=sp.zeros(3);zero=sp.zeros(3)
        aniso=0; tagged_rows=set();tagged_norm=sp.zeros(3)
        multiplicity=Counter(tuple(row) for row,_ in current.values())
        populations=dict(nonzero=0,p1_half=0,character_positive=0,holonomy_positive=0,character_max_ratio=0,holonomy_max_ratio=0)
        for row in sorted(distinct):
            k=sum(((row[2*i]+sp.I*row[2*i+1])*u for i,u in enumerate(basis)),zero)
            scan(k,populations,multiplicity[row],t)
            e=(k.H*k).applyfunc(sp.expand)
            normalization+=multiplicity[row]*e
            if t in (12,13):
                even=sum(((row[2*i]+sp.I*row[2*i+1])*basis[i] for i in range(3)),zero)
                odd=k-even
                tagged=(even.H*even+odd.H*odd).applyfunc(sp.expand)
                assert tagged*M==M*tagged
                tagged_rows.add(tuple(tagged))
                tagged_norm+=multiplicity[row]*tagged
            herm_rows.add(tuple(e));real_rows.add(tuple(e.applyfunc(sp.re)))
            aniso+=multiplicity[row]*int(e.applyfunc(sp.re)*M!=M*e.applyfunc(sp.re))
        assert normalization==4**t*I
        if check is not None and t in check:
            expected=check[t]
            for g,(row,_) in current.items():
                named=ref['cyclic'](tuple((graph.decode(u),b) for u,b in g))
                numerator=sum(((row[2*i]+sp.I*row[2*i+1])*u for i,u in enumerate(basis)),zero)
                assert numerator==2**t*expected[named]
            assert len(expected)==len(current)
        record=dict(t=t,ends=len(current),mixed_parity=sum(mask==3 for _,mask in current.values()),real_anisotropic=aniso,
                    rank_herm=sp.Matrix(list(herm_rows)).rank(),rank_real=sp.Matrix(list(real_rows)).rank())
        record['actual_input']=populations
        if tagged_rows:
            # Dropping parity-tag cross terms is a separate coherent-tag control.
            T=sp.Matrix(list(tagged_rows))
            record['parity_dephased_rank']=[T.rank(),T.applyfunc(sp.re).rank()]
            record['parity_dephased_sum']=[str(sp.simplify(z/4**t)) for z in tagged_norm]
            assert record['parity_dephased_rank']==[3,2] and tagged_norm==4**t*I
        out.append(record)
        print(record,file=__import__('sys').stderr,flush=True)
    return out
if __name__=='__main__':
 import sys
 print(json.dumps(run(int(sys.argv[1]) if len(sys.argv)>1 else 20),indent=2))
