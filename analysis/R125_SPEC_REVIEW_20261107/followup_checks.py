"""Adaptive checks justified by the primary tail-definition mismatch.
Also execute explicit cost/cancellation counterexamples; not a full engine.
Written after the preregistered primary run; no retrospective preregistration.
"""
from fractions import Fraction as F
from pathlib import Path
import itertools,json,time
HERE=Path(__file__).resolve().parent
start=time.perf_counter()
n,k=1024,327;w=[11**n]
for j in range(n):w.append(w[-1]*(n-j)*5//((j+1)*11))
den=16**n
tail=dict(reason='Distinguish symmetric distance from doubled smaller tail; original preregistered check remains unchanged',
 pmf_order=float(F(sum(x for x in w if x<=w[k]),den)),
 double_smaller_inclusive_tail=float(2*min(F(sum(w[:k+1]),den),F(sum(w[k:]),den))),
 absolute_distance_at_least_7_from_mean_320=float(F(sum(x for j,x in enumerate(w) if abs(j-320)>=7),den)),
 symmetric_tail_indices='K <= 313 or K >= 327')
tail['matches_0_661245']=abs(tail['absolute_distance_at_least_7_from_mean_320']-.661245)<5e-7
(HERE/'TAIL_DEFINITION_CHECK.json').write_text(json.dumps(tail,indent=2)+'\n')

stock=F(1);transit=F(0);consumed=F(0);returned=F(0);ledger=[]
def log(event):
 assert stock+transit+consumed==1
 ledger.append(dict(event=event,stock=stock,transit=transit,consumed=consumed,returned=returned))
log('initial')
stock-=F(1,10);consumed+=F(1,10);log('local_operation_cost')
stock-=F(1,2);transit+=F(1,2);log('commit')
transit-=F(1,2);stock+=F(1,2);returned+=F(1,2);log('return_arrives')
cost=dict(ledger=ledger,source_cost_formula=consumed-returned,net_depletion=F(1)-stock,
 irreversible_cost=consumed,net_cash_outflow=(consumed+returned)-returned)
assert cost['source_cost_formula']==F(-2,5) and cost['net_depletion']==F(1,10)

def execute(order,literal):
 old=F(1,2);new=F(0);lost=False
 for event in order:
  if event=='remote_loss':
   lost=True
   if literal:old=F(0)
  else:
   new=min(F(1,2),F(1,2)-old-new)
 return dict(old_reservation=old,new_grant=new,carrier_lost=lost)
orders=list(itertools.permutations(['remote_loss','receiver_request']))
race=[dict(order=o,literal=execute(o,True),causal=execute(o,False)) for o in orders]
assert race[0]['literal']!=race[1]['literal']
assert race[0]['causal']==race[1]['causal']
out=dict(cost=cost,spacelike_cancel_race=race,
 note='The remote loss and receiver request are spacelike in SPEC.md; only the loss notice is allowed to change receiver state',
 elapsed_seconds=time.perf_counter()-start)
(HERE/'FOLLOWUP_CHECKS.json').write_text(json.dumps(out,default=str,indent=2)+'\n')
print(json.dumps(dict(tail=tail,cost_source=str(cost['source_cost_formula']),cost_correct=str(cost['net_depletion']),
 literal_linear_extensions_differ=True,causal_linear_extensions_equal=True,seconds=out['elapsed_seconds']),indent=2))
