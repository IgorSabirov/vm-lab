from itertools import product
from collections import Counter, defaultdict
import json, hashlib

def code_tuple(t):
    z=0
    for x in t: z=z*3+(x+1)
    return z

# Frozen once, before held-out pair selection. These are arbitrary test weights,
# not physically calibrated parameters.
EPS={(a,b): ((code_tuple((a,b))*37+11)%101)-50 for a,b in product((1,2), repeat=2)}
ETA={(a,b,c,d): ((code_tuple((a,b,c,d))*53+19)%211)-105
     for a,b,c,d in product((1,2), repeat=4)}

def edge_counts(w):
    n=len(w); return Counter((w[i],w[(i+1)%n]) for i in range(n))
def eta_counts(w):
    n=len(w); return Counter(tuple(w[(i+j)%n] for j in range(4)) for i in range(n))
def three_counts(w):
    n=len(w); out={}
    for d in range(n):
      for e in range(n):
        out[d,e]=Counter((w[i],w[(i+d)%n],w[(i+d+e)%n]) for i in range(n))
    return out
def energy(w):
    n=len(w)
    return sum(EPS[w[i],w[(i+1)%n]] for i in range(n))+sum(
      ETA[tuple(w[(i+j)%n] for j in range(4))] for i in range(n))
def pair_key(w):
    n=len(w)
    return tuple(tuple(sum((w[i],w[(i+d)%n])==(a,b) for i in range(n))
                       for a in (1,2) for b in (1,2)) for d in range(n))
def orbit(w):
    n=len(w); r=w[::-1]
    return {w[i:]+w[:i] for i in range(n)}|{r[i:]+r[:i] for i in range(n)}
def main():
    groups=defaultdict(list)
    for h in product((1,2),repeat=12):
      w=h+tuple(3-x for x in h)
      groups[pair_key(w)].append(w)
    A=tuple(map(int,'111111221212222222112121'))
    B=tuple(map(int,'111112111121222221222212'))
    known=orbit(A)|orbit(B); selected=[]; used=set()
    for key,ws in sorted(groups.items(),key=lambda kv:kv[0]):
      cand=[w for w in ws if w not in known and w not in used]
      for i,a in enumerate(cand):
        if len(selected)==5: break
        if a in used: continue
        ca=eta_counts(a)
        for b in cand[i+1:]:
          if b in used: continue
          if ca!=eta_counts(b) and not (orbit(a)&orbit(b)):
            cid=hashlib.sha256(repr(key).encode()).hexdigest()[:12]
            selected.append((a,b,len(ws),cid)); used|={a,b}; break
      if len(selected)==5: break
    assert len(selected)==5
    rows=[]
    for idx,(a,b,gsize,cid) in enumerate(selected,1):
      assert three_counts(a)==three_counts(b)
      assert edge_counts(a)==edge_counts(b)
      assert eta_counts(a)!=eta_counts(b)
      ea,eb=energy(a),energy(b)
      rows.append({'pair':idx,'correlation_class':cid,'A':''.join(map(str,a)),
        'B':''.join(map(str,b)),'group_size':gsize,'three_point_equal':True,
        'edge_counts_equal':True,'four_vertex_motif_counts_differ':True,
        'E_A':ea,'E_B':eb,'delta_E':ea-eb,'distinguishes':ea!=eb})
    result={'status':'PASS' if sum(r['distinguishes'] for r in rows)>=4 else 'FAIL',
      'criterion':'at least 4 of 5 held-out pairs have unequal E under one frozen coefficient set',
      'coefficient_rule':'EPS and ETA deterministic motif-tuple hashes frozen before held-out pair selection',
      'EPS':{''.join(map(str,k)):v for k,v in EPS.items()},
      'ETA':{''.join(map(str,k)):v for k,v in ETA.items()},
      'pairs':rows,'pass_count':sum(r['distinguishes'] for r in rows),
      'distinct_three_point_correlation_classes':len({r['correlation_class'] for r in rows}),
      'warning':'Arbitrary frozen integer coefficients; not derived from X and not physical energy calibration.',
      'generation':'lexicographic h in {1,2}^12; form h||(3-h); group by complete directed pair-correlation vector; select five disjoint pairs before evaluating E'}
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
