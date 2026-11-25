"""Independent checks of the claims. Run from any directory with Python 3."""
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import product, combinations
import json
import math
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
ref = SimpleNamespace(**run_path(str(ROOT.parent / "verify.py")))
EPS = (1,-1)

def step(w, rule):
    dual = rule == 'C2'
    split = {3:(1,2),12:(8,4)} if dual else {3:(1,2)}
    merges = {v:k for k,v in split.items()}
    n = len(w)
    k = int((w[-1],w[0]) in merges)
    ends = k+n
    out = []
    while k < ends:
        p,q = w[k%n],w[(k+1)%n]
        if (p,q) in merges:
            out.append(merges[p,q]); k += 2
        else:
            out.extend(split.get(p,(p,))); k+=1
    # Each eligible rewrite consumes a distinct site or pair.
    active = any(x in split or (x,w[(i+1)%n]) in merges for i,x in enumerate(w))
    a,b = (5,10) if dual else (1,2)
    if rule == 'peer':
        return tuple(((p&2)>>1)|((out[(i+1)%len(out)]&1)<<1) for i,p in enumerate(out)),active
    return tuple((p&b)|(out[(i+1)%len(out)]&a) for i,p in enumerate(out)),active

def counts(w):
    n=len(w)
    pairs=Counter(4*w[i]+w[(i+1)%n] for i in range(n))
    return tuple(pairs.get(k,0) for k in range(16))

def fib(k):
    a,b=0,1
    for _ in range(k): a,b=b,a+b
    return a

def Z(w):
    mask=''.join('1' if x else '0' for x in w)
    if '0' not in mask:
        n=len(mask)
        return fib(2*n-1)+fib(2*n+1)-2
    k=mask.index('0')
    return math.prod(fib(2*len(run)+1) for run in (mask[k:]+mask[:k]).split('0') if run)

def profiles(rule):
    by_h=[set() for _ in range(9)]
    by_p=defaultdict(set); by_pz=defaultdict(set); pzs=set(); joined=set()
    for n in range(3,7):
        for w in product(range(4), repeat=n):
            z=Z(w); seq=[]; v=w
            for h in range(9):
                seq.append((len(v),counts(v)))
                by_h[h].add(tuple(seq))
                if h==4:
                    p=seq[0]; s=tuple(seq)
                    by_p[p].add(s); by_pz[p].add(z); pzs.add((p,z));joined.add((s,z))
                if h<8:v=step(v,rule)[0]
    split={p for p,ss in by_p.items() if len(ss)>1}
    return {'Pi_h':[len(g) for g in by_h],'Pi_Z':len(pzs),'Pi4_Z':len(joined),
            'split_Pi':len(split),'split_also_split_by_Z':sum(len(by_pz[p])>1 for p in split)}

def classes(H,cap):
    """Count directed one-bit edits between the three finite-window classes."""
    ws=list(product(range(16),repeat=3)); cats={}; periods=Counter(); cap_hits=0
    for w in ws:
        v=w; active=False; hit=False
        for _ in range(H):
            v,event=step(v,'C2'); active |= event
            if len(v)>cap:
                cap_hits+=1; hit=True; break
        cl='Q' if not active else ('G' if hit or len(v)>len(w) else 'B')
        cats[w]=cl
        if cl=='B':
            x=ref.named(w); nw=nn=None
            for t in range(1,2*H+1):
                x=ref.forward(x,EPS)
                if not nw and ref.cyclic(ref.word(x))==ref.cyclic(w): nw=t
                if not nn and ref.equal(x,ref.named(w)):nn=t
            periods[str((nw,nn))]+=1
    mat={c:Counter() for c in 'QGB'}
    for w,c in cats.items():
        for i in range(3):
            for b in (1,2,4,8):
                v=list(w);v[i]^=b;mat[c][cats[tuple(v)]]+=1
    return {'counts':Counter(cats.values()),'matrix':mat,'cap_hits':cap_hits,
            'periods_on_B':periods,'class_changes':sum(m[d] for c,m in mat.items() for d in 'QGB' if c!=d)}

def depth(u):
    if u[0]=='atom': return 0
    return 1+max(depth(a) for a in u[1:])

def named_branches():
    x=ref.named((1,2,12));y=ref.named((0,3,12));q=ref.named((0,2,13));q0=q
    c0=x[2][0];p=ref.left(c0);v=ref.right(c0);period=None
    for t in range(1,73):
        x=ref.forward(x,EPS);y=ref.forward(y,EPS);q=ref.forward(q,EPS)
        p=ref.right(p);v=ref.left(v)
        expected=ref.join(p,v)
        for seq in (x,y):
            (actual,) = (u for u, label in seq if label == 12)
            assert actual == expected and depth(actual) == t + 2
        assert len(y)==t+4 and len(x)==len(q)==3
        if period is None and ref.equal(q,q0): period=t
    return {'same_name_on_active_and_growing_until':72,'depth12_at_72':depth(expected),'quiet_named_period':period}

def charges(w):
    counts=[sum(bool(x&bit) for x in w) for bit in (1,2,4,8)]
    return tuple(counts+[sum((x&5)==5 for x in w),sum((x&10)==10 for x in w)])

def quiet_audit():
    groups={}; total=0; quiet=0; sector=Counter()
    sizes={}
    for n in range(1,5):
        qn=0
        for w in product(range(16),repeat=n):
            a1,b1,a2,b2,aa,bb=charges(w)
            criterion=not ((a1-aa)*(b1-bb) or (a2-aa)*(b2-bb))
            v=w; event=False
            for _ in range(n):
                v,event=step(v,'C2')
                if event:break
            assert criterion == (not event)
            assert charges(step(w,'C2')[0])==charges(w)
            if n==3 and (a1,b1,a2,b2)==(1,1,1,1):
                sector['quiet' if criterion else 'active']+=1
            if n==3:quiet+=int(criterion)
            qn+=int(criterion)
            total+=1
        formula=16**n-2*(4**n-3**n)**2+(4**n-2*3**n+2**n)**2
        assert qn==formula
        sizes[n]=qn
    for w in ((1,2,12),(0,3,12),(0,2,13)):groups[str(w)]=charges(w)
    return {'all_words_n1_to_4':total,'counts_by_n':sizes,'quiet_at_n3':quiet,'sector_one_each_at_n3':sector,'four_plus_two_charges':groups}

def c1_counts():
    out=Counter()
    for n in range(1,9):
        for w in product(range(4),repeat=n):
            m=sum(x==1 and w[(i+1)%n]==2 for i,x in enumerate(w)); s=w.count(3)
            out['words']+=1;out['balanced']+=int(m==s);out['balanced_active']+=int(s==m and s>0)
            out['one_each']+=int(s==m==1)
    return out

def named_transport():
    ncases=0; conflicting=0
    for n in range(3,7):
        for w in product(range(4),repeat=n):
            x=ref.named(w)
            tau=tuple((x[i][0],(w[(i+1)%n]&1)|(w[(i-1)%n]&2)) for i in range(n))
            assert ref.equal(ref.transport(ref.transport(x)),tau)
            if any(sum(bool(s&bit) for s in w)!=sum(bool(v&bit) for v in step(w,'peer')[0]) for bit in (1,2)):conflicting+=1
            ncases+=1
    return {'named_pass':ncases,'peer_full_step_changes_channel_counts':conflicting}

def history_file():
    d=json.loads((ROOT.parents[1] / 'R140_HAAR_SORKIN' / 'HISTORIES.json').read_text())
    k=len(d['named_endpoints']); sums=[0j]*k; recorded=[0]*k; vectors=[]
    for b in d['branches']:
        v={i:complex(re,im) for i,re,im in b['amplitudes']}
        for i,a in v.items(): sums[i]+=a;recorded[i]+=round(abs(a)**2)
        vectors.append(v)
    def freeze(x):
        return tuple(map(freeze,x)) if isinstance(x,list) else x
    endpoints=[freeze(x) for x in d['named_endpoints']]
    current={((),ref.cyclic(ref.named((1,2,0)))):1}
    maximum=0
    for _ in range(8):
        following=defaultdict(complex)
        for (history,x),amp in current.items():
            w=ref.word(x)
            m=sum(s in (3,12) or (s,w[(i+1)%len(w)]) in ((1,2),(8,4)) for i,s in enumerate(w))
            maximum=max(m,maximum)
            assert m<=1
            branches=[(x,1)] if m==0 else [(x,(1-1j)/2),(ref.interact(x,EPS),(1+1j)/2)]
            for y,c in branches:
                end=ref.cyclic(ref.transport(y,2))
                following[history+(len(end),),end]+=amp*c
        current=following
    rebuilt={(r,e):16*z for (r,e),z in current.items() if z}
    expected={(tuple(row['lengths']),endpoints[i]):complex(re,im)
              for row in d['branches'] for i,re,im in row['amplitudes']}
    assert rebuilt==expected  # binary fractions here are exactly representable
    aa=(3,3,3,2,2,2,2,2); bb=(2,2,2,2,3,3,3,2)
    va=[rebuilt.get((aa,e),0j) for e in endpoints]
    vb=[rebuilt.get((bb,e),0j) for e in endpoints]
    sq=lambda v: Fraction(round(sum((z*z.conjugate()).real for z in v)),256)
    mu_a,mu_b,mu_union=sq(va),sq(vb),sq([a+b for a,b in zip(va,vb)])
    signs=Counter()
    for a,b in combinations(vectors,2):
        cross=2*round(sum((v.conjugate()*b.get(i,0)).real for i,v in a.items()))
        signs[(cross>0)-(cross<0)]+=1
    return {'histories':len(vectors),'ends':k,'coherent_zeros':sum(not a and b>0 for a,b in zip(sums,recorded)),
            'all_exported_amplitudes_rebuilt':True,'max_active_blocks':maximum,
            'witness':list(map(str,(mu_a,mu_b,mu_union,mu_union-mu_a-mu_b))),
            'pair_signs':signs,'TV':str(Fraction(sum(abs(round(abs(a)**2)-b) for a,b in zip(sums,recorded)),512))}

def law_intervention():
    """Toggle I on the same named C1 input with identical transport."""
    state = ref.named((1, 2, 0))
    lengths = {
        "Q_only": len(ref.transport(state)),
        "QI": len(ref.forward(state)),
    }
    assert lengths == {"Q_only": 3, "QI": 2}
    return lengths


def square_test():
    """Compare two coherent lifts of the same two-site deterministic flip."""
    # Each column of B(pi/4) has diagonal d and off-diagonal f.
    d, f = (1 - 1j) / 2, (1 + 1j) / 2
    assert d*d + f*f == 0 and 2*d*f == 1  # B(pi/4)^2 = X
    sites = ref.named((1, 2, 12))
    assert ref.word(ref.interact(sites, EPS)) == (3, 8, 4)
    independent = [d*d, d*f, f*d, f*f]
    global_flip = [d, 0j, 0j, f]
    def weights(vector):
        return [(z.conjugate() * z).real for z in vector]
    assert weights(independent) == [0.25] * 4
    assert weights(global_flip) == [0.5, 0, 0, 0.5]
    return {"local_product_weights": weights(independent),
            "global_flip_weights": weights(global_flip)}


if __name__ == "__main__":
    checks = {
        "transport": named_transport(),
        "balanced_C1": c1_counts(),
        "census10": classes(10, 30),
        "census18": classes(18, 45),
        "named": named_branches(),
        "profiles_R130": profiles("C1"),
        "profiles_peer": profiles("peer"),
        "R140_export": history_file(),
        "quiet_criterion": quiet_audit(),
        "same_input_law_intervention": law_intervention(),
        "two_site_square": square_test(),
    }
    print(json.dumps(checks, indent=2))
