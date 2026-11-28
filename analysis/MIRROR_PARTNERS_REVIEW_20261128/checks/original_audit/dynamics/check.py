import importlib.util,itertools,json,sys
from pathlib import Path
P=Path(__file__).with_name('source_engine.py')
spec=importlib.util.spec_from_file_location('e',P); e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
named,equal,word,forward,backward,interact,transport,r2=(getattr(e,k) for k in ('named','equal','word','forward','backward','interact','transport','r2'))
def M(x):return tuple((e.mirror_name(u),s) for u,s in reversed(x))
def B(x):return tuple((u,((s&1)<<1)|((s&2)>>1)|((s&4)<<1)|((s&8)>>1)) for u,s in x)
def Cp(x):return M(B(x))
def Cmr(x):return M(r2(x))
res={}
for eps in itertools.product((1,-1),repeat=2):
 d={k:0 for k in ('n','MIM_to_Iminus','BIB_to_Iminus','CpI_commutes','CpQ_commutes','Cp2','CpFCp_to_F','MRFMR_to_Fswapeps','T2','TFT_to_Finv','TFTinv_to_Finv','CpT_commutes','CpT2','CpTFCpT_to_Finv')}
 def T(x):return interact(r2(x),eps)
 def Ti(x):return r2(interact(x,eps))
 def CT(x):return Cp(T(x))
 wits={}
 for n in range(1,4):
  for w in itertools.product(range(16),repeat=n):
   x=named(w);d['n']+=1
   obs={
    'MIM_to_Iminus':equal(M(interact(M(x),eps)),interact(x,tuple(-t for t in eps))),
    'BIB_to_Iminus':equal(B(interact(B(x),eps)),interact(x,tuple(-t for t in eps))),
    'CpI_commutes':equal(Cp(interact(Cp(x),eps)),interact(x,eps)),
    'CpQ_commutes':equal(Cp(transport(Cp(x),2)),transport(x,2)),
    'Cp2':equal(Cp(Cp(x)),x),
    'CpFCp_to_F':equal(Cp(forward(Cp(x),eps)),forward(x,eps)),
    'MRFMR_to_Fswapeps':equal(Cmr(forward(Cmr(x),eps)),forward(x,eps[::-1])),
    'T2':equal(T(T(x)),x),
    'TFT_to_Finv':equal(T(forward(T(x),eps)),backward(x,eps)),
    'TFTinv_to_Finv':equal(T(forward(Ti(x),eps)),backward(x,eps)),
    'CpT_commutes':equal(Cp(T(x)),T(Cp(x))),
    'CpT2':equal(CT(CT(x)),x),
    'CpTFCpT_to_Finv':equal(CT(forward(CT(x),eps)),backward(x,eps)),
   }
   for k,v in obs.items():
    d[k]+=not v
    if not v and k not in wits:wits[k]=w
 res[str(eps)]={'counts':d,'first_witnesses':wits}
 print(eps,d,flush=True)
# Reproduce bounded candidate search from first cell.
def pack(a,b):return (a&1)+2*(b&1)+2*(a&2)+4*(b&2)
def unpack(s):return ((s&1)+2*((s>>2)&1),((s>>1)&1)+2*((s>>3)&1))
words=[named(w) for n in (2,3) for w in itertools.product(range(16),repeat=n)]
same=[];exch=[]
for conv in ('direct','swap'):
 for f in itertools.permutations(range(4)):
  for g in itertools.permutations(range(4)):
   p=[]
   for s in range(16):
    a,b=unpack(s);p.append(pack(f[a],g[b]) if conv=='direct' else pack(f[b],g[a]))
   def sigma(x,p=p):return M(tuple((u,p[s]) for u,s in x))
   ok_s=ok_e=True
   for x in words:
    lhs=sigma(forward(sigma(x),(1,-1)))
    if ok_s and not equal(lhs,forward(x,(1,-1))):ok_s=False
    if ok_e and not equal(lhs,forward(x,(-1,1))):ok_e=False
    if not ok_s and not ok_e:break
   if ok_s:same.append((conv,f,g,p))
   if ok_e:exch.append((conv,f,g,p))
res['search']={'candidates':1152,'states_each_max':4352,'same':same,'exchange':exch,'buggy_sigma_word_3_0_0':word(sigma(named((3,0,0)))),'correct_Cp_word_3_0_0':word(Cp(named((3,0,0))))}
print('Search:',res['search'],flush=True)
res['provenance']={'source_path':'analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py','source_commit':'3ae1d270f65dd353672dd15786add8394c419cb2','source_sha256':__import__('hashlib').sha256(P.read_bytes()).hexdigest(),'scope':'Named cyclic rings, unique admissible names, finite exhaustions plus separately stated local algebra; no thermodynamic arrow conclusion'}
Path(__file__).with_name('results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
