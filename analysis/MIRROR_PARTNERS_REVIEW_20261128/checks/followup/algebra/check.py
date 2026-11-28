import importlib.util,json
from pathlib import Path
from itertools import product
src=Path(__file__).resolve().parents[2] / 'original_audit' / 'dynamics' / 'source_engine.py'
spec=importlib.util.spec_from_file_location('e',src);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
def M(x):return tuple((e.mirror_name(u),s) for u,s in reversed(x))
def B2(x):return tuple((u,((s&1)<<1)|((s&2)>>1)|((s&4)<<1)|((s&8)>>1)) for u,s in x)
def Cp(x):return M(B2(x))
def chi(x):return sum(int((s&5)==5)-int((s&10)==10) for _,s in x)
def q(x):return sum(((s>>0)&1)+((s>>2)&1)-((s>>1)&1)-((s>>3)&1) for _,s in x)
res={}
for n in range(1,7):
 row=dict(states=0,MFM_not_inverse=0,BFB_not_inverse=0,C_self_named=0,C_self_cyclic_word=0)
 wits={}
 for w in product(range(4),repeat=n):
  x=e.named(w);c=e.reflected_swap(x)
  checks={
   'MFM_not_inverse':not e.equal(M(e.forward(M(x))),e.backward(x)),
   'BFB_not_inverse':not e.equal(e.swap_bits(e.forward(e.swap_bits(x))),e.backward(x)),
   'C_self_named':e.equal(c,x),
   'C_self_cyclic_word':e.cyclic(e.word(c))==e.cyclic(w),
  }
  row['states']+=1
  for k,v in checks.items():
   row[k]+=v
   if v and k not in wits:
    wits[k]={'word':w,'x':repr(x),'MFM_word':e.word(M(e.forward(M(x)))),'BFB_word':e.word(e.swap_bits(e.forward(e.swap_bits(x)))),'inverse_word':e.word(e.backward(x))}
 res[str(n)]={'counts':row,'witnesses':wits}
res['L3to6']={k:sum(res[str(n)]['counts'][k] for n in range(3,7)) for k in res['3']['counts']}
for w in ((5,), (1,), (5,0,0),(1,0,0)):
 x=e.named(w);y=Cp(x)
 res['C2_word_witness_'+str(w)]={'original':w,'partner':e.word(y),'chi_x':chi(x),'chi_partner':chi(y),'q_x':q(x),'q_partner':q(y),'word_quotients_equal':e.cyclic(w)==e.cyclic(e.word(y))}
# Full transformations retain their exact operator expressions at every tested ring.
eps=(1,)
formula=dict(states=0,MFM_formula_fail=0,BFB_formula_fail=0)
for n in range(1,5):
 for w in product(range(4),repeat=n):
  x=e.named(w);rhs=e.transport(e.interact(x,(-1,)),1,True);formula['states']+=1
  formula['MFM_formula_fail']+=not e.equal(M(e.forward(M(x))),rhs)
  formula['BFB_formula_fail']+=not e.equal(e.swap_bits(e.forward(e.swap_bits(x))),rhs)
res['formula_check']=formula
z=e.interact(e.named((0,3)))
res['compound_named_C_fixed_example']={'construction':'I(named((0,3)))','state':repr(z),'word':e.word(z),'C_fixed_named':e.equal(e.reflected_swap(z),z)}
x=e.named((0,3));res['F_reachable_fixed_examples']=[]
for t in range(4):
 res['F_reachable_fixed_examples'].append({'t':t,'length':len(x),'word':e.word(x),'C_fixed_named':e.equal(e.reflected_swap(x),x),'state':repr(x)})
 x=e.forward(x)
Path(__file__).with_name('results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'L3to6':res['L3to6'],'formula_check':formula,'first_short_MFM_witness':res['1']['witnesses'].get('MFM_not_inverse'),'C2_witness':res['C2_word_witness_(5,)']},ensure_ascii=False,indent=2))
