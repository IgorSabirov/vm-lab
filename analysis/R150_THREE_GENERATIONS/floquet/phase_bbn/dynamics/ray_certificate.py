"""Induction certificates for length growth. Affine pairs denote a+b*k, k>=0."""
from collections import Counter
from itertools import product
import json
from carrier_audit import sparse_step, BITS


class Unstable(Exception):
    pass


def add(a,b): return a[0]+b[0],a[1]+b[1]
def sub(a,b): return a[0]-b[0],a[1]-b[1]
def shift(a,j): return add(a,(j,0))


def sign(a):
    if a==(0,0): return 0
    if a[0]>0 and a[1]>=0: return 1
    if a[0]<0 and a[1]<=0: return -1
    raise Unstable


def mod(a,n):
    q=a[0]//n[0]
    residue=sub(a,(q*n[0],q*n[1]))
    if sign(residue)<0 or sign(sub(residue,n))>=0: raise Unstable
    return residue


def affine_step(n,key):
    sites=((0,0),*key)
    # Every equality needed by hash lookup must be stable throughout the ray.
    for x in sites:
        for y in sites:
            sign(sub(x,y))
    def mask_at(x):
        return sum(b for y,b in zip(sites,BITS) if sign(sub(y,x))==0)
    pair=((1,2),(8,4))
    cut=int((mask_at(shift(n,-1)),mask_at((0,0))) in pair)
    p=tuple(mod(shift(x,-cut),n) for x in sites)
    def mask(x):
        return sum(b for y,b in zip(p,BITS) if sign(sub(y,x))==0)
    occupied=set(p)
    joins={x for x in occupied if (mask(x),mask(mod(shift(x,1),n))) in pair}
    ends={shift(x,1) for x in joins}
    splits={x for x in occupied if mask(x) in (3,12)}
    size=shift(n,len(splits)-len(joins))
    out=[]
    for x,b in zip(p,BITS):
        j=shift(x,-1) if any(sign(sub(x,y))==0 for y in ends) else x
        delta=sum(sign(sub(y,j))<0 for y in splits)-sum(sign(sub(y,j))<0 for y in ends)
        delta+=int(x in splits and b in (2,4))-int(b in (1,4))
        out.append(mod(shift(j,delta),size))
    return size,tuple(mod(sub(y,out[0]),size) for y in out[1:])


def certificate(s):
    n,k=s
    after,q=sparse_step(s)
    if after!=n+1: return
    key=tuple((x,y-x) for x,y in zip(k,q))
    try: image=affine_step((n,1),key)
    except Unstable: return
    if image==((n+1,1),tuple((a+b,b) for a,b in key)):
        return dict(length=n,positions=key)


def check():
    horizon=48
    families=Counter()
    proofs={}
    for k in product(range(7),repeat=3):
        state=(7,k)
        left=False
        for t in range(horizon+1):
            if state[0]!=7: left=True
            elif left:
                families['returned_after_exit']+=1
                break
            if left and state[0]>7:
                proof=certificate(state)
                if proof:
                    families['certified_escape']+=1
                    proofs[str(k)]={'start_step':t,**proof}
                    break
            state=sparse_step(state)
        else:
            families['no_exit_in_prefix' if not left else 'unclassified']+=1
    return dict(counts=families,rays=proofs,verification_horizon=horizon)


def classify_all():
    from word_rule import backward_word,state_to_word,word_to_state
    cycles=set(); ray_counts=Counter(); seed_counts=Counter(); by_seed={}
    for k in product(range(7),repeat=3):
        state=(7,k)
        path=[]; seen=set()
        for t in range(64):
            if state in seen:
                assert state==path[0]
                cycles.add(frozenset(path))
                seed_counts['periodic']+=1
                by_seed[str(k)]={'period':t,'path':path}
                break
            proof=certificate(state) if state[0]>7 else None
            if proof:
                assert all(v==1 for a,v in proof['positions'])
                tail=tuple(proof['length']-a for a,b in proof['positions'])
                ray_counts[tail]+=1
                seed_counts['escape']+=1
                by_seed[str(k)]={'entry_step':t,'prefix':path,'affine_certificate':proof,'tail':tail}
                break
            seen.add(state); path.append(state)
            previous=state
            state=sparse_step(state)
            backward=backward_word(state_to_word(state[1],state[0]))
            assert (len(backward),word_to_state(backward))==previous
        else: raise AssertionError('unclassified')
    lengths=Counter(len(c) for c in cycles)
    finite_states=sum(map(len,cycles))
    assert finite_states==len(set.union(set(),*cycles))
    assert (len(cycles),finite_states,len(ray_counts))==(64,381,31)
    assert lengths=={1:5,5:6,6:25,7:28} and seed_counts=={'periodic':251,'escape':92}
    from fractions import Fraction
    mean_length=sum(Fraction(sum(L==7 for L,k in c)**2,len(c)) for c in cycles)/343
    mean_word=sum(Fraction(sum(L==7 for L,k in c),len(c)) for c in cycles)/343
    return dict(seeds=seed_counts,cycle_histogram=lengths,finite_states=finite_states,
                uniform_L7_time_average_same_length=str(mean_length),
                uniform_L7_time_average_same_word=str(mean_word),
                tails={str(k):v for k,v in sorted(ray_counts.items())},by_seed=by_seed)


if __name__=='__main__':
    print(json.dumps({'first_exit':check(),'all_orbits':classify_all()},indent=2))
