"""Independent reconstruction from a prose specification, NOT the missing archive.

Only Python stdlib. Fractions for model states, floats for Lorentz diagnostics.
Use --calibrate for a bounded 64-pair timing; default is the declared 1024 pairs.
"""
from fractions import Fraction as F
from collections import Counter
from pathlib import Path
import argparse, csv, hashlib, itertools, json, math, os, platform, sys, time

HERE=Path(__file__).resolve().parent

def enc(x):
    if isinstance(x,F): return str(x)
    raise TypeError(type(x).__name__)

def save(path,x): path.write_text(json.dumps(x,default=enc,ensure_ascii=False,indent=2)+'\n')

def coin(seed,event,p):
    # Stateless, purpose-labelled random source; no claim to implement Random123.
    n=int.from_bytes(hashlib.sha256(f'wrel-v1|{seed}|{event}'.encode()).digest()[:8],'big')
    return int(n*p.denominator < p.numerator*2**64)

def graph(delay=F(0),tie='arrival_first'):
    if delay<0: raise ValueError('negative extra delay')
    if delay==1 and tie not in ('arrival_first','read_first'):
        raise ValueError('unspecified local instrument at coincident reception/read')
    # A and B are spacelike. All buffers, read, target, receiver are at rest x=0.
    points={'L':(-2,0),'A':(0,-1),'B':(0,1),'QA':(1+delay,0),
            'QB':(1,0),'C':(2,0),'Y':(3,0),'Y2':(4,0)}
    phase={e:0 for e in points};phase['C']=1
    if tie=='read_first': phase['QA']=2
    # Distinct suboperations at the SAME spacetime point are a local instrument
    # convention, not distinct events with a spacetime-derived strict order.
    def earlier(e,f):
        te,xe=points[e];tf,xf=points[f]
        return (tf>te and tf-te>=abs(xf-xe)) or (
            (tf,xf)==(te,xe) and (phase[e],e)<(phase[f],f))
    pred={e:{f for f in points if f!=e and earlier(f,e)} for e in points}
    return points,pred

def ordering(pred,reverse=False):
    done=set();order=[]
    while len(done)<len(pred):
        available=[e for e in pred if e not in done and pred[e]<=done]
        if not available: raise ValueError('causal cycle')
        # Only scheduler tie-breaking changes, never event coordinates or inputs.
        def key(e): return ({'A':1 if reverse else 0,'B':0 if reverse else 1}.get(e,2),e)
        e=min(available,key=key);done.add(e);order.append(e)
    return order

def simulate(seed=0,reverse=False,delay=F(0),tie='arrival_first',cut_A=False,
             ttl=F(10),K=True,rC=F(3,100),rY=F(2,100),cut_Y2=False,
             readable=True,loss_A=False,loss_Y2=False,forced=None,sA=0,sB=0):
    points,pred=graph(delay,tie);order=ordering(pred,reverse)
    initial={'C':rC,'Y':rY};balances=dict(initial);ledger=[];buffer={};state={}
    def debit(node,amount,event):
        if balances[node]<amount: return False
        balances[node]-=amount
        ledger.append({'node':node,'event':event,'debit':amount})
        return True
    for e in order:
        if e=='L': state['lambda']=forced[0] if forced else coin(seed,'L',F(1,2))
        elif e in ('A','B'):
            i=1 if e=='A' else 2
            eta=forced[i] if forced else coin(seed,e+':noise',F(1,4))
            state[e]=state['lambda'] ^ eta ^ (sA if e=='A' else sB)
        elif e in ('QA','QB'):
            src=e[-1]
            if src=='B' or not(cut_A or loss_A): buffer[src]=(state[src],points[e][0])
        elif e=='C':
            av={k:v for k,(v,arrival) in buffer.items() if 0<=2-arrival<=ttl}
            state['available']=sorted(av)
            state['u']=int(K and av.get('A')==1 and av.get('B')==1
                           and debit('C',F(2,100),'correction'))
        elif e=='Y':
            state['health']=min(F(1),F(1)-F(1,10)*3+F(1,5)*state['u'])
            state['F']=int(state['health']>=F(4,5))
            state['sent']=bool(state['F'] and debit('Y',F(1,100),'send'))
            state['payload']=state['u'] if state['sent'] else None
        elif e=='Y2':
            state['received']=state['payload'] if state['sent'] and not(cut_Y2 or loss_Y2) and readable else None
            state['T']=int(state['received'] is not None)
            state['S']=state['F']*state['T']
    # Compare an independently updated stock with the sum of recorded debits.
    residual={n:balances[n]-(initial[n]-sum((x['debit'] for x in ledger if x['node']==n),F(0))) for n in balances}
    state.update(rC=balances['C'],rY=balances['Y'],ledger_residual=residual)
    return state,order,ledger

def permute(n,output):
    mismatch=0;rows=[];start=time.perf_counter()
    for seed in range(n):
        a,oa,la=simulate(seed);b,ob,lb=simulate(seed,reverse=True)
        different=a!=b or la!=lb;mismatch+=different
        rows.append({'seed':seed,'m_A':a['A'],'m_B':a['B'],'F':a['F'],'T':a['T'],
                     'S':a['S'],'health':str(a['health']),'r_C':str(a['rC']),
                     'r_Y':str(a['rY']),'different':int(different)})
    with output.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return dict(pairs=n,event_executions=2*n*8,mismatches=mismatch,
                success_count=sum(x['S'] for x in rows),seconds_including_csv=time.perf_counter()-start)

def exact_law(sA=0,sB=0,K=True,cut_Y2=False):
    hist=Counter();marg=Counter();joint=Counter()
    for l,a,b in itertools.product([0,1],repeat=3):
        w=F(1,2)*(F(1,4) if a else F(3,4))*(F(1,4) if b else F(3,4))
        z,_,_=simulate(forced=(l,a,b),sA=sA,sB=sB,K=K,cut_Y2=cut_Y2)
        hist[z['S']]+=w;marg[z['B']]+=w;joint[(z['A'],z['B'])]+=w
    return hist,marg,joint

def tv(a,b): return sum((abs(a.get(k,0)-b.get(k,0)) for k in a.keys()|b.keys()),F(0))/2

def flux_step(r,dt=F(1,10),dx=F(1),D=F(1),cap=F(1)):
    # Literal neighbor formula. J is transferred amount per step, not velocity.
    edge=[]
    for a,b in zip(r,r[1:]):
        q=min(D*abs(a-b)/dx*dt,a if a>b else b,cap)
        edge.append(q if a>b else -q)
    out=list(r)
    for i,q in enumerate(edge): out[i]-=q;out[i+1]+=q
    return out,edge

def diagnostics():
    good=lambda **kw: simulate(forced=(1,0,0),**kw)[0]
    delay=[]
    for delta,tie in [(F(0),'arrival_first'),(F(999,1000),'arrival_first'),
                      (F(1),'arrival_first'),(F(1),'read_first'),(F(1001,1000),'arrival_first')]:
        z=good(delay=delta,tie=tie)
        delay.append(dict(delay=delta,tie=tie,F=z['F'],T=z['T'],S=z['S'],available=z['available']))
    try: good(delay=F(1),tie='undefined');undefined_rejected=False
    except ValueError: undefined_rejected=True
    controls={name:good(**kw) for name,kw in {
        'base':{},'K_off':{'K':False},'cut_A':{'cut_A':True},
        'buffer_expired':{'ttl':F(1,2)},'record_lost':{'loss_A':True},
        'resource_C_insufficient':{'rC':F(1,100)},'cut_Y2':{'cut_Y2':True},
        'Y2_unreadable':{'readable':False},'Y2_loss':{'loss_Y2':True},
        'Y_cannot_send':{'rY':F(0)}}.items()}
    on,m0,joint=exact_law();off,_,_=exact_law(K=False);no_transfer,_,_=exact_law(cut_Y2=True)
    _,m1,_=exact_law(sA=1)
    ns=tv(m0,m1)
    # A can predict the common cause at B after the A channel is cut; prediction
    # is not a surviving causal channel. Direct forced intervention remains null.
    cut_effects=[]
    for l,a,b in itertools.product([0,1],repeat=3):
        z0=simulate(forced=(l,a,b),sA=0,cut_A=True)[0]
        z1=simulate(forced=(l,a,b),sA=1,cut_A=True)[0]
        cut_effects.append((z0['u'],z0['F'],z0['S'])==(z1['u'],z1['F'],z1['S']))
    # Global IID stream order may change a coupling, but not the output law.
    iid_ab=Counter();iid_ba=Counter();different=0
    for u,v in itertools.product([0,1],repeat=2):
        x=u+2*v;y=v+2*u;different+=x!=y;iid_ab[x]+=F(1,4);iid_ba[y]+=F(1,4)
    # Local arbitration occurs at C after both requests arrive.
    def greedy(order):
        budget=F(3,100);out={}
        for e in order:out[e]=min(F(2,100),budget);budget-=out[e]
        return out
    symmetric={e:F(3,200) for e in 'AB'}
    # Independent ledger mutation must be detected, not recomputed away.
    z,_,ledger=simulate(forced=(1,0,0))
    corrupt_residual=z['rC']-(F(3,100)-sum((x['debit']+F(1,100) for x in ledger if x['node']=='C'),F(0)))
    # Counterexample to claimed speed gate and another to positivity.
    after,J=flux_step([F(1,1000),F(0)])
    neg,Jneg=flux_step([F(0),F(1),F(0)],dt=F(1))
    # Positive causal packet control: dx=1, v=1/2, arrival at t=2.
    packet=[dict(t=t,source=F(0),in_transit=F(1) if t<2 else F(0),
                 destination=F(0) if t<2 else F(1)) for t in [F(0),F(1),F(2)]]
    # Source-injection convention explicitly includes the token while in transit.
    checks=dict(permutation=None,deadline=[x['F'] for x in delay]==[1,1,1,0,0],
        undefined_deadline_rejected=undefined_rejected,base_repair=controls['base']['F']==1,
        K_off_fails=controls['K_off']['F']==0,cut_A_fails=controls['cut_A']['F']==0,
        cut_A_causal_influence_zero=all(cut_effects),expired_buffer_fails=controls['buffer_expired']['F']==0,
        lost_record_fails=controls['record_lost']['F']==0,
        insufficient_C_fails=controls['resource_C_insufficient']['F']==0,
        independent_transfer=all(controls[x]['F']==1 and controls[x]['T']==0 and controls[x]['S']==0
            for x in ['cut_Y2','Y2_unreadable','Y2_loss','Y_cannot_send']),
        failed_transfer_still_spends=controls['cut_Y2']['rY']==F(1,100),
        exact_no_signalling=ns==0,exact_controller_delta=on[1]-off[1]==F(5,16),
        ledger=all(all(v==0 for v in z['ledger_residual'].values()) for z in controls.values()),
        corrupt_ledger_rejected=corrupt_residual!=0,
        flux_speed_gate_refuted=after[1]>0 and abs(J[0])*F(1,10)<=1 and F(1,10)<1,
        flux_positivity_refuted=min(neg)<0 and all(abs(q)<=1 for q in Jneg),
        iid_path_law_distinction=different==2 and tv(iid_ab,iid_ba)==0,
        packet_conservation=all(p['source']+p['in_transit']+p['destination']==1 for p in packet))
    return dict(checks=checks,delay=delay,controls=controls,
      exact_probabilities=dict(P_F=on[1],P_T_given_F=F(1),P_S=on[1],delta_K=on[1]-off[1],
          P_S_cut_Y2=no_transfer[1],P_B1_setting_A0=m0[1],P_B1_setting_A1=m1[1],no_signalling_TV=ns,
          P_B1_given_A1=joint[(1,1)]/F(1,2),P_B1_given_A0=joint[(0,1)]/F(1,2)),
      global_iid_control=dict(path_mismatches=different,paths=4,output_TV=tv(iid_ab,iid_ba)),
      allocator=dict(AB=greedy('AB'),BA=greedy('BA'),symmetric=symmetric),
      flux_counterexamples=dict(causality=dict(initial=[F(1,1000),F(0)],after=after,J=J,dt=F(1,10),dx=1,c=1,
                                               gate_left=abs(J[0])*F(1,10),gate_right=1),
                                positivity=dict(initial=[0,1,0],after=neg,J=Jneg,dt=1,dx=1,c=1,total=sum(neg))),
      causal_packet_control=packet,ledger_corruption_residual=corrupt_residual)

def lorentz():
    nodes=graph()[0];rows=[];maxerr=0.;causal_ok=True;proper_ok=True
    for v in [-.9,-.5,0.,.5,.9]:
        g=1/math.sqrt(1-v*v)
        transformed={e:(g*(float(t)-v*float(x)),g*(float(x)-v*float(t))) for e,(t,x) in nodes.items()}
        for a,b in itertools.combinations(nodes,2):
            t,x=nodes[a];u,y=nodes[b];dt=float(u-t);dx=float(y-x)
            dtp=transformed[b][0]-transformed[a][0];dxp=transformed[b][1]-transformed[a][1]
            s=dx*dx-dt*dt;sp=dxp*dxp-dtp*dtp;err=abs(s-sp);maxerr=max(maxerr,err)
            scale=max(1.,dtp*dtp,dxp*dxp);tol=128*sys.float_info.epsilon*scale
            if abs(s)>tol: causal_ok &= (s>0)==(sp>0)
            if s<0: causal_ok &= (dt>0)==(dtp>0)
        ty,xy=transformed['Y'];proper=math.sqrt(ty*ty-xy*xy)
        proper_ok &= math.isclose(proper,3.,rel_tol=1e-13)
        rows.append(dict(beta=v,t_A=transformed['A'][0],t_B=transformed['B'][0],target_proper_time=proper))
    return dict(rows=rows,max_absolute_interval_error=maxerr,causal_relations_preserved=bool(causal_ok),proper_time_preserved=bool(proper_ok))

def environment():
    def read(p):
        try:return Path(p).read_text().strip()
        except OSError:return None
    cpu=read('/proc/cpuinfo') or ''
    model=next((l.split(':',1)[1].strip() for l in cpu.splitlines() if l.startswith('model name')),None)
    return dict(python=sys.version,platform=platform.platform(),cpu_model=model,
        affinity=sorted(os.sched_getaffinity(0)),cpu_max=read('/sys/fs/cgroup/cpu.max'),
        memory_max=read('/sys/fs/cgroup/memory.max'),memory_current=read('/sys/fs/cgroup/memory.current'),
        workload='single-process stdlib, exact Fractions; float64 scalar Lorentz diagnostics; no BLAS/GPU',
        host_load=read('/proc/loadavg'),hidden_host_parameters='not available',
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--calibrate',action='store_true');args=parser.parse_args()
    start=time.perf_counter()
    if args.calibrate:
        results=[permute(64,HERE/'CALIBRATION_SAMPLE.csv') for _ in range(3)]
        median=sorted(r['seconds_including_csv'] for r in results)[1]
        x=dict(environment=environment(),samples=results,prediction_seconds=median*16+.2,
               lower_seconds=median*8,upper_seconds=max(2.,median*32+.5),hard_limit_seconds=15,
               formula='median(64 paired runs + CSV) * 16 + 0.2 s exact controls/IO; upper max(2, 32*median+0.5)')
        save(HERE/'CALIBRATION.json',x);print(json.dumps(x,indent=2));return
    out=diagnostics();per=permute(1024,HERE/'PERMUTATION.csv');boost=lorentz()
    out['checks']['permutation']=per['mismatches']==0
    out['checks']['lorentz_kinematics']=boost['causal_relations_preserved'] and boost['proper_time_preserved']
    out.update(permutation=per,lorentz=boost,environment=environment(),source_archive_reproduced=False,
               scope='independent reconstruction of prose model and exact counterexamples; no full R125 field simulation')
    out['all_checks_pass']=all(out['checks'].values());out['runtime_seconds']=time.perf_counter()-start
    save(HERE/'CHECKS.json',out)
    print(json.dumps({k:out[k] for k in ['checks','all_checks_pass','permutation','exact_probabilities','flux_counterexamples','runtime_seconds']},default=enc,indent=2))
    assert out['all_checks_pass']

if __name__=='__main__':main()
