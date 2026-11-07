"""Bounded independent audit of the prose R125-v2 preflight. Python stdlib only.
Not the neighbor's missing script and not a full distributed protocol engine.
"""
from fractions import Fraction as F
from pathlib import Path
import argparse, csv, hashlib, itertools, json, math, os, platform, sys, time

HERE=Path(__file__).resolve().parent

def encode(x):
    if isinstance(x,F):return str(x)
    raise TypeError(type(x).__name__)

def save(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,default=encode,indent=2)+'\n')

def allocate_divisible(requests,stock):
    total=sum((d for _,d in requests),F(0))
    factor=min(F(1),stock/total) if total else F(0)
    return {i:d*factor for i,d in requests}

def hamilton(requests,stock,tie='id'):
    total=sum(d for _,d in requests);seats=min(stock,total)
    if not total:return {i:0 for i,_ in requests}
    quota={i:F(seats*d,total) for i,d in requests}
    alloc={i:int(q) for i,q in quota.items()}
    keys={i:(i if tie=='id' else position) for position,(i,d) in enumerate(requests)}
    ranked=sorted(quota,key=lambda i:(-(quota[i]-alloc[i]),keys[i]))
    for i in ranked[:seats-sum(alloc.values())]:alloc[i]+=1
    return alloc

def dhondt(requests,stock):
    demand=dict(requests);alloc={i:0 for i in demand}
    for _ in range(min(stock,sum(demand.values()))):
        possible=[i for i in demand if alloc[i]<demand[i]]
        chosen=min(possible,key=lambda i:(-F(demand[i],alloc[i]+1),i))
        alloc[chosen]+=1
    return alloc

def enumerate_allocators(limit=None,write=False):
    all_d=[d for d in itertools.product(range(5),repeat=3) if any(d)]
    if limit is not None:all_d=all_d[:limit]
    count=bad_index=bad_id=transitions=bad_h=bad_d=0;bad_cases=[];mono=[]
    start=time.perf_counter()
    for d in all_d:
        req=list(enumerate(d));hh=[hamilton(req,s) for s in range(10)];dd=[dhondt(req,s) for s in range(10)]
        for s in range(10):
            baseline=hamilton(req,s,tie='index')
            for order in itertools.permutations(range(3)):
                items=[req[i] for i in order];a=hamilton(items,s,'index');b=hamilton(items,s,'id')
                count+=1;bi=a!=baseline;bad_index+=bi;bad_id+=b!=hh[s]
                assert sum(a.values())==min(s,sum(d)) and all(0<=a[i]<=d[i] for i in range(3))
                if bi:bad_cases.append(dict(d=str(d),stock=s,order=str(order),original=str(baseline),permuted=str(a)))
        for s in range(9):
            h=any(hh[s+1][i]<hh[s][i] for i in range(3));v=any(dd[s+1][i]<dd[s][i] for i in range(3))
            transitions+=1;bad_h+=h;bad_d+=v
            if h:mono.append(dict(d=d,stock=s,before=hh[s],after=hh[s+1]))
    if write:
        with (HERE/'INDEX_TIE_FAILURES.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['d','stock','order','original','permuted']);w.writeheader();w.writerows(bad_cases)
        save('MONOTONICITY_FAILURES.json',mono)
    return dict(demand_vectors=len(all_d),permutation_comparisons=count,index_tie_failures=bad_index,
                id_tie_failures=bad_id,stock_transitions=transitions,hamilton_decreases=bad_h,
                dhondt_decreases=bad_d,seconds=time.perf_counter()-start)

def binomial_checks():
    # Exact integer PMF weights at p0=5/16. CP inversion uses float log-PMF.
    n,k=1024,327;weights=[11**n]
    for j in range(n):weights.append(weights[-1]*(n-j)*5//((j+1)*11))
    denominator=16**n;assert sum(weights)==denominator
    p_exact=F(sum(w for w in weights if w<=weights[k]),denominator)
    p_central=min(F(1),2*min(F(sum(weights[:k+1]),denominator),F(sum(weights[k:]),denominator)))
    logs=[math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1) for j in range(n+1)]
    def cdf(p,last):
        lp=math.log(p);lq=math.log1p(-p)
        return math.fsum(math.exp(logs[j]+j*lp+(n-j)*lq) for j in range(last+1))
    def root(last,target):
        lo,hi=0.,1.
        for _ in range(56):
            mid=(lo+hi)/2
            if cdf(mid,last)>target:lo=mid
            else:hi=mid
        return (lo+hi)/2
    return dict(z=7/(2*math.sqrt(55)),clopper_pearson_95=[root(k-1,.975),root(k,.025)],
                p_two_sided_probability_order=float(p_exact),p_double_smaller_inclusive_tail=float(p_central),
                exact_p_definition='sum exact PMF weights <= weight at k',
                interpretation='arithmetic for iid Binomial(n,p); no coverage claim for fixed SHA256 labels')

def lifecycle(branch):
    state=dict(sender=F(1),escrow=F(0),transit=F(0),returning=F(0),receiver=F(0),loss=F(0),consumed=F(0),reserved=F(0))
    rows=[];token=True
    def log(event):
        total=sum(state[k] for k in ['sender','escrow','transit','returning','receiver','loss','consumed'])
        assert total==1 and all(v>=0 for v in state.values())
        rows.append(dict(event=event,**state,total_with_losses_and_consumption=total))
    log('initial');state['sender']-=F(1,2);state['escrow']+=F(1,2);log('allocate')
    state['reserved']+=F(1,2);log('reserve_capacity')
    if branch in ('ack_lost_expiry','ack_lost_no_expiry'):
        log('ack_lost')
        if branch.endswith('no_expiry'):return dict(rows=rows,open_obligations=2,successful_delivery=0)
        state['sender']+=state['escrow'];state['escrow']=F(0);token=False;log('sender_expiry')
        state['reserved']=F(0);log('receiver_local_expiry')
        before=state.copy()
        if token:raise AssertionError('stale ack allowed')
        log('stale_ack_rejected');assert state==before
        return dict(rows=rows,open_obligations=0,successful_delivery=0)
    state['escrow']-=F(1,2);state['transit']+=F(1,2);log('commit_send')
    if branch=='success':
        state['transit']=F(0);state['receiver']+=F(1,2);state['reserved']=F(0);log('arrive')
    elif branch=='loss':
        state['transit']=F(0);state['loss']+=F(1,2);log('loss_at_carrier_reservation_unchanged')
        state['reserved']=F(0);log('later_loss_notice_at_receiver')
    elif branch=='expired_return':
        state['reserved']=F(0);log('receiver_local_expiry')
        state['transit']=F(0);state['returning']+=F(1,2);log('late_arrival_redirected')
        state['returning']=F(0);state['sender']+=F(1,2);log('return_arrives')
    return dict(rows=rows,open_obligations=0,successful_delivery=int(branch=='success'))

def controls():
    cases=[(F(1),[1,1],[F(1,2),F(1,2)]),(F(1),[2,1],[F(2,3),F(1,3)]),
           (F(1,4),[F(1,5),F(2,5),F(3,5)],[F(1,24),F(1,12),F(1,8)]),
           (F(0),[1,1],[F(0),F(0)]),(F(1),[0,0,0],[F(0)]*3),
           (F(1),[F(1,5),F(2,5)],[F(1,5),F(2,5)])]
    table=[]
    for stock,d,expected in cases:
        req=list(enumerate(map(F,d)));a=allocate_divisible(req,stock)
        matches=list(a.values())==expected
        assert matches and all(allocate_divisible(list(p),stock)==a for p in itertools.permutations(req))
        table.append(dict(stock=stock,demand=d,allocation=a,matches=matches))
    receiver=allocate_divisible([(0,F(3,5)),(1,F(2,5))],F(1,2));assert receiver=={0:F(3,10),1:F(1,5)}
    # Physically local loss at (t,x)=(1,0); receiver at x=1, read t=1.5.
    # Literal simultaneous clearing of p_reserved changes a spacelike observable.
    def grant(loss,immediate,t):
        notice=loss and (immediate or t>=2)
        reserved=F(0) if notice else F(1,2)
        return min(F(1,2),F(1,2)-reserved)
    remote=dict(loss_event=[1,0],receiver_read=[F(3,2),1],interval=F(3,4),
      earliest_notice=2,literal_grants=[grant(a,True,F(3,2)) for a in [False,True]],
      causal_grants_before_notice=[grant(a,False,F(3,2)) for a in [False,True]],
      causal_grants_after_notice=[grant(a,False,F(5,2)) for a in [False,True]])
    assert remote['literal_grants']==[0,F(1,2)] and remote['causal_grants_before_notice']==[0,0]
    # Same physical capacity includes outgoing escrow if the node also receives.
    capacity=dict(cap=F(1),free_stock=F(1,2),outgoing_escrow=F(1,2),incoming_reservation=F(1,2),
                  source_occupancy_formula=F(1),physical_occupancy_or_obligations=F(3,2),
                  assumption='free stock and outgoing escrow share the same storage; dual-role node')
    cost=dict(initial=F(1),committed_and_returned=F(1,2),consumed=F(1,10),loss=F(0),commits=1,
              final_resource=F(9,10),source_formula=F(-2,5),irreversible_cost=F(1,10))
    budget=dict(global_resource=10,cost_per_action=1,formula_horizon=10,
                resource_reachable_before_deadline=0,observed_successful_cycles=0)
    return dict(divisible_table=table,receiver=receiver,remote_loss=remote,dual_role_capacity=capacity,
                return_cost=cost,resource_horizon=budget,
                lifecycle={b:lifecycle(b) for b in ['success','loss','expired_return','ack_lost_expiry','ack_lost_no_expiry']},
                liveness=dict(repeated_expired_requests=5,expired_each_within_deadline=True,
                              outstanding_after_each_expiry=0,successful_services=0),
                ulp=dict(residual=2.0**-45,machine_epsilon=sys.float_info.epsilon,
                         units_at_1=(2.0**-45)/math.ulp(1.0),units_at_16=(2.0**-45)/math.ulp(16.0)))

def environment():
    def read(p):
        try:return Path(p).read_text().strip()
        except OSError:return None
    cpu=read('/proc/cpuinfo') or ''
    return dict(python=sys.version,platform=platform.platform(),
       cpu_model=next((s.split(':',1)[1].strip() for s in cpu.splitlines() if s.startswith('model name')),None),
       affinity=sorted(os.sched_getaffinity(0)),cpu_max=read('/sys/fs/cgroup/cpu.max'),memory_max=read('/sys/fs/cgroup/memory.max'),
       workload='single process stdlib; Fraction combinatorics, integer PMF weights, float CP inversion',
       code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--calibrate',action='store_true');args=ap.parse_args();start=time.perf_counter()
    if args.calibrate:
        trials=[enumerate_allocators(limit=12) for _ in range(3)]
        med=sorted(x['seconds'] for x in trials)[1]
        out=dict(environment=environment(),trials=trials,predicted_seconds=med*124/12+.2,
                 upper_seconds=max(2.,med*124/6+.5),hard_limit_seconds=15)
        save('CALIBRATION.json',out);print(json.dumps(out,indent=2));return
    enumeration=enumerate_allocators(write=True);statistics=binomial_checks();control=controls()
    checks=dict(index_count_matches=enumeration['index_tie_failures']==507,
                id_count_matches=enumeration['id_tie_failures']==0,
                hamilton_count_matches=enumeration['hamilton_decreases']==5,
                dhondt_count_matches=enumeration['dhondt_decreases']==0,
                counts_match=enumeration['permutation_comparisons']==7440 and enumeration['stock_transitions']==1116,
                cp_matches=max(abs(a-b) for a,b in zip(statistics['clopper_pearson_95'],[.29084602,.34886862]))<5e-9,
                p_order_matches=abs(statistics['p_two_sided_probability_order']-.637054)<5e-7,
                p_tail_matches=abs(statistics['p_double_smaller_inclusive_tail']-.661245)<5e-7)
    out=dict(enumeration=enumeration,statistics=statistics,controls=control,comparison_checks=checks,
             all_reported_counts_match=all(checks.values()),environment=environment(),
             scope='specified allocator subset and explicit small witnesses; not all 23 neighbor tests or full R125')
    out['runtime_seconds']=time.perf_counter()-start
    save('CHECKS.json',out)
    print(json.dumps({k:out[k] for k in ['enumeration','statistics','comparison_checks','runtime_seconds']},indent=2))
    # A scientific mismatch is recorded, not hidden by forcing a success exit.

if __name__=='__main__':main()
