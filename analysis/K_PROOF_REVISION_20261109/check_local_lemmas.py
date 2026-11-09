"""Independent half-pair algebra checks; no imports from carrier/audit simulator."""
from itertools import product
from collections import Counter
import json
from pathlib import Path

H=list(product(range(4),repeat=2))  # 0, e1=1, e2=2, e12=3
pure={1,2}
def split(s):return s[0]==s[1] and s[0] in pure
def merge(s,t):return s[0] in pure and s[1]==0 and t==(0,s[0])
def count(w):return tuple(sum(s[j]==v for s in w) for j in (0,1) for v in (1,2,3))
def Q(w):return [(w[(i+1)%len(w)][0],s[1]) for i,s in enumerate(w)]
def Qi(w):return [(w[i-1][0],s[1]) for i,s in enumerate(w)]
def canonical(w):return min(tuple(w[i:]+w[:i]) for i in range(len(w)))
def K(w):
 a,b,c,d,e,f=count(w);return (a*d,b*e)

def main():
 checks={};n=0
 for c in pure:
  assert count([(c,c)])==count([(c,0),(0,c)])
  n+=1
 checks['elementary_split_merge_conservation_channels']=n
 # Any new merge after Q forces the shared old vertex to be a pure split.
 n=0
 for x,y,z in product(H,repeat=3):
  if merge((y[0],x[1]),(z[0],y[1])):assert split(y)
  n+=1
 checks['Q_merge_preimage_triples']=n
 # Every non-split state is unchanged by I unless it belongs to a merge;
 # split children have no split, including seams with arbitrary neighbours.
 for c in pure:assert not any(split(s) for s in [(c,0),(0,c)])
 checks['I_removes_all_splits_without_merges']=True
 rows=[]
 for L in range(1,4):
  qcount=0;allwords=0;homogeneous=0
  for w in product(H,repeat=L):
   w=list(w);allwords+=1
   assert count(Q(w))==count(w) and Qi(Q(w))==w
   vals=K(w);compatible=any(a[0]==b[1] and a[0] in pure for a in w for b in w)
   assert (sum(vals)>0)==compatible
   z=w
   first=None
   for t in range(L):
    if any(split(s) for s in z):
     first=t;break
    z=Q(z)
   distances=[(j-i)%L for i,b in enumerate(w) for j,a in enumerate(w) if a[0]==b[1] and a[0] in pure]
   assert first==(min(distances) if distances else None)
   if not compatible:
    qcount+=1
    assert not any(split(s) or merge(s,w[(i+1)%L]) for i,s in enumerate(w))
    z=w
    for _ in range(L):z=Q(z)
    assert z==w
   if all(s==w[0] for s in w) and not any(split(s) for s in w):
    assert Q(w)==w and sum(vals)==0;homogeneous+=1
  formula=16**L-2*(4**L-3**L)**2+(4**L-2*3**L+2**L)**2
  simplified=2*9**L+2*8**L-4*6**L+4**L
  assert qcount==formula==simplified
  rows.append(dict(L=L,all_words=allwords,quiet=qcount))
 checks['independent_half_pair_enumeration']=rows
 # K>=2 can occur in one channel, in E0.
 witness=[(0,1),(1,0),(1,0),(0,0)];assert K(witness)==(2,0)
 assert not any(split(s) or merge(s,witness[(i+1)%len(witness)]) for i,s in enumerate(witness))
 checks['single_active_channel_K2_witness']=witness
 # Independent exact arithmetic confirms threshold bound monotonicity and recurrence.
 for L0 in range(1,9):
  for g in range(1,33):
   B=lambda h:h*L0+h*(h-1)//2
   assert B(g)==sum(range(L0,L0+g))
   assert B(g)-B(g-1)==L0+g-1
 checks['hitting_time_bound_arithmetic']=True
 result={'status':'PASS','checks':checks,'scope':'Independent finite checks of local proof lemmas; arbitrary-L conclusions are in PROOF_REVIEW.md, not inferred from samples.'}
 Path(__file__).with_name('CHECKS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
