"""Independent sparse four-port dynamics, orbit counts, returns, and gap bound."""
from collections import Counter
from itertools import product
from pathlib import Path
import json
import math
from word_rule import state_to_word, word_to_state, F_word, T_word

BITS=(1,2,4,8)


def sparse_step(state):
    L, key=state
    positions=(0,*key)
    masks=Counter()
    for site,bit in zip(positions,BITS):
        masks[site]+=bit
    pairs=((1,2),(8,4))
    cut=int((masks[L-1],masks[0]) in pairs)
    sites=tuple((p-cut)%L for p in positions)
    occupied={(p-cut)%L:v for p,v in masks.items() if v}
    joins={p for p,v in occupied.items() if (v,occupied.get((p+1)%L,0)) in pairs}
    ends={p+1 for p in joins}
    splits={p for p,v in occupied.items() if v in (3,12)}
    size=L+len(splits)-len(joins)
    final=[]
    for p,bit in zip(sites,BITS):
        j=p-1 if p in ends else p
        q=j+sum(a<j for a in splits)-sum(a<j for a in ends)
        q+=int(p in splits and bit in (2,4))
        final.append((q-int(bit in (1,4)))%size)
    return size,tuple((a-final[0])%size for a in final[1:])


def audit(L):
    keys=set(product(range(L),repeat=3))
    f={}
    for key in keys:
        w=state_to_word(key,L)
        image=F_word(w)
        step=sparse_step((L,key))
        assert step==(len(image),word_to_state(image))
        if step[0]==L: f[key]=step[1]
    keep=set(f)
    while True:
        fixed={w for w in keep if f[w] in keep}
        if fixed==keep: break
        keep=fixed
    seen=set(); counts=Counter(); dims=Counter()
    same_T=0; chi_zero=0; combined=0
    for w in keep:
        tw=T_word(state_to_word(w,L))
        same_T+=word_to_state(tw)==w
        if w in seen: continue
        c=[]; k=w
        while k not in seen:
            c.append(k); seen.add(k); k=f[k]
        assert k==w
        n=len(c); counts[n]+=1
        t,u,last=w
        v=(last-t)%L
        charge=int(u==0)-int(v==0)
        mass=(u+v)%L
        zero=1+int(n%2==0) if charge==0 else 2*int(n%12==0)
        chi_zero+=zero
        combined+=zero if mass==0 else 0
        Tfirst=word_to_state(T_word(state_to_word(w,L)))
        for sign in (1,-1):
            if sign==-1 and n%2: continue
            dims[sign,'size']+=1
            dims[sign,'trace']+=sign**c.index(Tfirst) if Tfirst in c else 0
    assert len(keep)==3*L*(L-1) and same_T==3-(-1)**L
    assert sum(math.gcd(n,2)*freq for n,freq in counts.items())==(5*L-7 if L%2 else 6*L-6)
    assert chi_zero==(3*L-5 if L%2 else (6*L-6 if L%12==0 else 2*L-2))
    assert combined==(4 if L%2 else 2)
    if L%2: assert (dims[1,'trace'],dims[-1,'trace'])==(3,1)
    record=dict(carrier=len(keep),cycles=dict(counts),trace_T=same_T,chi_zero=chi_zero,combined_zero=combined,
                trace_zero_pi=[dims[1,'trace'],dims[-1,'trace']])
    if L==7:
        times=Counter(); last=Counter()
        for k in keys-keep:
            s=(L,k); left=False
            for t in range(1,2049):
                s=sparse_step(s)
                if s[0]!=L: left=True
                elif left:
                    times[t]+=1
                    break
            else:
                last[s[0]]+=1
        record.update(first_return_after_exit=times,unreturned_final_lengths_at_2048=last)
    return record


if __name__=='__main__':
    print(json.dumps({L:audit(L) for L in range(2,26)},indent=2))
