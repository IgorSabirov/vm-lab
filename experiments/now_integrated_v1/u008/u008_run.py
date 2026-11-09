"""U008 finite causal channel experiment; exact finite enumeration, no RNG.

Reuses pinned NOW Cell/Config and paid production. Explicitly replaces the
transfer/contact event mechanism; it is not a rerun of the legacy Engine.
"""
import argparse, collections, copy, hashlib, heapq, itertools, json, os
import platform, resource, signal, sys, time, zipfile
from pathlib import Path

def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def save(p, x):
    p=Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x, ensure_ascii=False, sort_keys=True)+'\n');tmp.replace(p)

BASE_HASHES={
 'nowexp/state.py':'ca8b0e6cbb9cb108940ef0a6627bfe1a8c5ce992128d7158cfa4e823882c24dc',
 'nowexp/local_instruments.py':'f90e7a1ceb756fe71285d16e14658c8fb32f1625dacc3d0b30d186ad3d1952d6',
 'nowexp/engine.py':'691459011781be7b13e1f75990abff2685fe7a118f67f1ae64b3c8a9213eb594',
 'nowexp/task_probe.py':'e3ea3095bdcb16f7de4a0173d8768a7db9111348d2d94360cc54a3aa04e22dc7'}

def bind_base(path):
    base=Path(path).resolve()
    for p,h in BASE_HASHES.items():
        if hashlib.sha256((base/p).read_bytes()).hexdigest()!=h: raise RuntimeError('G0 mismatch: '+p)
    sys.path.insert(0,str(base))
    global Cell, Config, produce, capable, use, withhold
    from nowexp.state import Cell, Config
    from nowexp.local_instruments import produce, capable, use, withhold

def all_cases():
    cases=[]
    def add(panel, f=10, m=5, ready=8, arm='A1', bits=(0,0), **kw):
        cases.append(dict(panel=panel, fuel=f, material=m, ready=ready, arm=arm,
                          bits=list(bits), tie='strict', bypass=False, **kw))
    for f,m,r,bits,arm in itertools.product([9,10,11],[4,5,6],[8,13,14],itertools.product([0,1],repeat=2),['A0','A1','A2','A3','A4']):
        add('primary',f,m,r,arm,bits)
    for bits in itertools.product([0,1],repeat=2):
        for arm in ['A1','A2','A3']:
            add('bypass',arm=arm,bits=bits);cases[-1]['bypass']=True
        for tie in ['strict','ready_first']:
            add('tie_at_probe',ready=9,bits=bits);cases[-1]['tie']=tie
        for arm in ['A1','A2']:
            add('after',arm=arm,bits=bits,after=True)
        for perturb in ['no_child_apparatus','no_child_fuel','tamper','wrong_ack','stale_repair','sham_repair']:
            add(perturb,bits=bits,perturb=perturb)
    for i,c in enumerate(cases):c['id']=f'U008_{i:04d}'
    return cases

class World:
    def __init__(self, case):
        self.case=case;self.now=0;self.queue=[];self.seq=0;self.log=[];self.current=None
        self.cfg=Config(task_probe=True,separate_apparatus=True,thresholds={})
        self.nodes={k:Cell(k,i,fuel=f,precursor=case['material'] if k=='P' else 0,
                           fuel_capacity=64,precursor_capacity=64)
                    for i,(k,f) in enumerate([('P',case['fuel']+1),('C',2),('D',0)])}
        for k,n in self.nodes.items():
            n.apparatus=[dict(identity=k+':port',made_by='initial',generation=n.generation,
                              template=1,material_units=1,roles=['link_send','link_recv'])]
        for kind,roles in [('writer',['write','catalyze']),('reader',['read','catalyze','repair'])]:
            self.nodes['P'].apparatus.append(dict(identity='P:seed:'+kind,made_by='initial',generation=0,
                template=1,material_units=1,functional_type=kind,roles=roles))
        self.nodes['P'].decoded=dict(zip(['A','B'],case['bits']))
        self.channels={k:dict(ends=ends,connector=k+':initial',epoch=0,history=[])
                       for k,ends in [('main',['P','C']),('side',['P','C']),('next',['C','D'])]}
        # side is a physically present dummy edge excluded from the routing table.
        if case['bypass']:self.channels['backup']=dict(ends=['P','C'],connector='backup:initial',epoch=0,history=[])
        self.routes={('P','C'):['main']+(['backup'] if case['bypass'] else []),('C','D'):['next']}
        self.transit={};self.assembly={};self.hold={'fuel':0,'material':0}
        self.nonce={};self.child_payload=None;self.child_output=None;self.forward_output=None
        self.checksum_ok=False;self.pre_h=False;self.damage_id=None;self.repair_times=[]
        self.y={k:0 for k in ['Y_R','Y_H','Y_T','Y_V','Y_F','Y_T2']}
        self.supply_schedule=[] # no donor or damage-triggered replenishment
        self.initial=self.totals();self.initial_hash=digest(self.snapshot())
        self.schedule(0,'probe',{'pre':True},'P')

    def schedule(self,t,kind,data=None,owner='P',parents=None):
        priority=0 if kind=='damage' else 1 if kind=='probe' else 3
        if kind=='repair_done':priority=0 if self.case['tie']=='ready_first' else 2
        self.seq+=1
        e=dict(event_id=f'e{self.seq:04d}',parent_event_ids=parents if parents is not None else ([self.current['event_id']] if self.current else []),
               event_type=kind,coordinate_time=t,proper_time=t,carrier_id=owner,data=data or {})
        heapq.heappush(self.queue,(t,priority,self.seq,e))

    def snapshot(self):
        return dict(time=self.now,nodes={k:n.to_dict() for k,n in self.nodes.items()},channels=self.channels,
                    transit=self.transit,assembly=self.assembly,hold=self.hold,nonce=self.nonce,
                    child_payload=self.child_payload,child_output=self.child_output,forward_output=self.forward_output,
                    queue=[e for _,_,_,e in sorted(self.queue)],y=self.y,pre_h=self.pre_h)

    def totals(self):
        f=sum(n.fuel+n.spent_fuel+n.unavailable_fuel for n in self.nodes.values())+self.hold['fuel']
        m=sum(n.precursor+n.material_waste+n.unavailable_material+sum(a['material_units'] for a in n.apparatus)
              for n in self.nodes.values())+self.hold['material']
        m+=sum(c['connector'] is not None for c in self.channels.values())
        for p in list(self.transit.values())+list(self.assembly.values()):
            f+=p.get('fuel',0);m+=p.get('material',0)+sum(a['material_units'] for a in p.get('apparatus',[]))
        return {'fuel':f,'material':m}

    def audit(self):
        if self.totals()!=self.initial:raise AssertionError(('balance',self.totals(),self.initial))
        ids=[]
        for n in self.nodes.values():
            assert min(n.fuel,n.precursor,n.spent_fuel,n.unavailable_fuel,n.unavailable_material,n.material_waste)>=0
            ids += [a['identity'] for a in n.apparatus]
        for p in self.transit.values():ids += [a['identity'] for a in p.get('apparatus',[])]
        assert len(ids)==len(set(ids)), 'apparatus duplicated'
        for _,_,_,e in self.queue: assert e['coordinate_time']>=self.now

    def note(self,reason):self.current['failure_reason']=reason

    def route(self,src,dst):
        key=(src,dst) if (src,dst) in self.routes else (dst,src)
        for name in self.routes.get(key,[]):
            c=self.channels[name]
            if c['connector'] is not None and src in c['ends'] and dst in c['ends']:return name
        return None

    def send(self,src,dst,body,apparatus=None,fuel=0):
        n=self.nodes[src]
        if not capable(n,'link_send'):self.note('missing_link_port');return False
        if n.fuel<1+fuel:self.note('send_or_gift_fuel');return False
        n.pay(1,'probe' if body['type'] in ['query','ack'] else 'transfer')
        name=self.route(src,dst)
        if name is None:self.note('no_route');return False
        n.fuel-=fuel
        moved=apparatus or []
        for a in moved:n.apparatus.remove(a)
        pid=self.current['event_id']+':packet';c=self.channels[name]
        self.transit[pid]=dict(src=src,dst=dst,body=copy.deepcopy(body),apparatus=moved,fuel=fuel,
                              channel=name,epoch=c['epoch'],sent_at=self.now)
        self.current.update(channel_id=name,repair_epoch=c['epoch'],payload_id=body['id'],payload_hash=digest(body),delivery_status='SENT')
        self.schedule(self.now+1,'deliver',{'packet':pid},dst)
        return True

    def configure(self):
        c=self.case
        self.schedule(4 if not c.get('after') else 16,'damage',{},'P')
        self.schedule(5,'produce',{},'P');self.schedule(6,'reserve_repair',{},'P')
        self.schedule(17 if c.get('after') else 6.1,'repair_start',{},'P')
        self.schedule(9,'probe',{'pre':False},'P')
        self.schedule(13,'target',{},'P');self.schedule(15,'function',{},'C');self.schedule(16,'forward',{},'C')
        if c.get('perturb')=='stale_repair':self.schedule(7,'damage',{'repeat':True},'P')

    def dispatch(self,e):
        c=self.case;arm=c['arm'];kind=e['event_type'];d=e['data'];p=self.nodes['P'];child=self.nodes['C']
        if kind=='damage':
            if arm=='A0':return
            name='side' if arm=='A4' else 'main';ch=self.channels[name]
            if ch['connector'] is not None:p.material_waste+=1
            ch['connector']=None;ch['epoch']+=1;ch['history'].append(e['event_id']);self.damage_id=e['event_id']
            e.update(channel_id=name,repair_epoch=ch['epoch'])
        elif kind=='produce':
            produce(p,arm!='A3',self.cfg)
        elif kind=='reserve_repair':
            f,m=min(1,p.fuel),min(1,p.precursor);p.fuel-=f;p.precursor-=m
            self.hold=dict(fuel=f,material=m)
        elif kind=='repair_start':
            name='side' if arm=='A4' else 'main';ch=self.channels[name]
            enabled=arm in ['A1','A4']
            if not enabled or ch['connector'] is not None or c.get('perturb')=='sham_repair':
                p.unavailable_fuel+=self.hold['fuel'];p.unavailable_material+=self.hold['material'];self.hold=dict(fuel=0,material=0)
                self.note('repair_disabled_or_unneeded');return
            if not capable(p,'repair') or not capable(p,'write') or p.route_template!=['write','read']:
                self.note('repair_apparatus_or_template');return
            if self.hold != dict(fuel=1,material=1):self.note('repair_reserve_shortfall');return
            p.spent_fuel+=1;p.costs['repair']=p.costs.get('repair',0)+1;use(p,'repair')
            self.hold=dict(fuel=0,material=0)
            assembly_id=e['event_id']+':connector'
            self.assembly[assembly_id]=dict(material=1,channel=name,epoch=ch['epoch'])
            ready=19 if c.get('after') else c['ready']
            self.schedule(ready,'repair_done',{'assembly':assembly_id},'P',parents=[e['event_id'],self.damage_id])
        elif kind=='repair_done':
            a=self.assembly.pop(d['assembly']);ch=self.channels[a['channel']]
            e.update(channel_id=a['channel'],repair_epoch=a['epoch'])
            if a['epoch']!=ch['epoch'] or ch['connector'] is not None:
                p.material_waste+=a['material'];self.note('stale_repair_epoch');return
            ch['connector']=d['assembly'];ch['history'].append(e['event_id']);self.repair_times.append(self.now)
            self.y['Y_R']=1 # structural completion only; never sets H/T/F
        elif kind=='probe':
            pre=d['pre'];nonce=('pre:' if pre else 'post:')+e['event_id']
            self.nonce[nonce]=dict(created=self.now,deadline=self.now+3,pre=pre)
            self.send('P','C',dict(type='query',id=nonce,nonce=nonce,pre=pre))
        elif kind=='deliver':
            packet=self.transit.pop(d['packet']);ch=self.channels[packet['channel']];body=packet['body']
            e.update(channel_id=packet['channel'],repair_epoch=packet['epoch'],payload_id=body['id'],payload_hash=digest(body),delivery_time=self.now)
            if packet['epoch']!=ch['epoch'] or ch['connector'] is None:
                src=self.nodes[packet['src']];src.unavailable_fuel+=packet['fuel'];src.material_waste+=sum(a['material_units'] for a in packet['apparatus'])
                self.note('stale_or_broken_delivery');return
            dest=self.nodes[packet['dst']];dest.fuel+=packet['fuel'];dest.apparatus.extend(packet['apparatus'])
            e['delivery_status']='DELIVERED'
            if body['type']=='query':
                nonce=body['nonce']
                if not body['pre'] and c.get('perturb')=='wrong_ack':nonce+=':wrong'
                self.send('C','P',dict(type='ack',id='ack:'+body['id'],nonce=nonce,pre=body['pre']))
            elif body['type']=='ack':
                n=self.nonce.get(body['nonce'])
                if n is None or not self.now<n['deadline']:self.note('invalid_ack_nonce_or_deadline');return
                if n['pre']:self.pre_h=True
                else:self.y['Y_H']=1
            elif body['type']=='payload':
                self.y['Y_T']=1
                if c.get('perturb')=='tamper':body['bits'][0]^=1
                valid=body['checksum']==digest({'id':body['id'],'bits':body['bits']})
                if not valid:self.note('payload_integrity');return
                self.y['Y_V']=1;self.child_payload=copy.deepcopy(body)
                child.memories={'received':copy.deepcopy(body)}
            elif body['type']=='forward':
                if body['checksum']==digest({'id':body['id'],'value':body['value']}):
                    self.y['Y_T2']=1;self.forward_output=body['value']
        elif kind=='target':
            if not self.y['Y_H']:self.note('no_received_post_ack');return
            if not capable(p,'write') or set(p.decoded)!={'A','B'}:self.note('target_apparatus_or_content');return
            bits=[p.decoded['A'],p.decoded['B']];pid='new:'+e['event_id']
            body=dict(type='payload',id=pid,bits=bits,checksum=digest({'id':pid,'bits':bits}))
            moved=[a for a in p.apparatus if a.get('made_by')=='P'][-2:]
            if c.get('perturb')=='no_child_apparatus':moved=[]
            gift=0 if c.get('perturb')=='no_child_fuel' else 3
            self.send('P','C',body,moved,gift)
        elif kind=='function':
            if self.child_payload is None:self.note('child_no_valid_record');return
            if not capable(child,'read') or not capable(child,'write'):self.note('child_no_work_apparatus');return
            if not child.pay(2,'child_read_write'):self.note('child_fuel');return
            use(child,'read');use(child,'write');a,b=self.child_payload['bits'];self.child_output=a^b
            child.memories['output']=self.child_output
            self.y['Y_F']=1 # correctness independently assessed by observer
        elif kind=='forward':
            if self.child_output is None:self.note('child_no_output');return
            pid='child:'+e['event_id'];body=dict(type='forward',id=pid,value=self.child_output,
                  checksum=digest({'id':pid,'value':self.child_output}))
            self.send('C','D',body)
        else:raise ValueError(kind)

    def run(self,until=30):
        while self.queue and self.queue[0][0]<=until:
            _,_,_,e=heapq.heappop(self.queue);self.now=e['coordinate_time'];self.current=e
            before=self.snapshot();balances={k:(n.fuel,n.precursor,n.spent_fuel) for k,n in self.nodes.items()}
            e['local_preconditions']={k:dict(fuel=n.fuel,material=n.precursor,apparatus=[a['identity'] for a in n.apparatus]) for k,n in self.nodes.items()}
            self.dispatch(e);self.audit()
            self.log.append(dict(**e,state_hash_before=digest(before),state_hash_after=digest(self.snapshot()),
                                 resource_changes={k:[n.fuel-balances[k][0],n.precursor-balances[k][1],n.spent_fuel-balances[k][2]] for k,n in self.nodes.items()},balance=self.totals()))
        self.current=None

def simulate(case):
    w=World(case);w.nodes['P'].route_template=['write','read'];w.run(3)
    assert w.pre_h and w.child_payload is None and not capable(w.nodes['C'],'write')
    # Paired arms are deep copies of the same pre-intervention physical snapshot.
    before=copy.deepcopy(w.snapshot());before_hash=digest(before)
    w=copy.deepcopy(w);w.configure();w.run()
    target=case['bits'][0]^case['bits'][1]
    if w.child_output is not None:assert w.child_output==target
    if w.forward_output is not None:assert w.forward_output==target
    y=dict(w.y);y['Y_star']=int(all(y[k] for k in ['Y_H','Y_T','Y_V','Y_F']))
    failure=next((k for k in ['Y_H','Y_T','Y_V','Y_F','Y_T2'] if not y[k]),None)
    return dict(case=case,pre_snapshot=before,pre_snapshot_hash=before_hash,outcomes=y,
                first_failed_stage=failure,log=w.log,final_state=w.snapshot(),
                initial_balance=w.initial,final_balance=w.totals(),repair_completion_times=w.repair_times,
                observer_xor_target=target,child_output=w.child_output,forward_output=w.forward_output)

def unit_checks():
    tests=[]
    def case(**kw):
        d=dict(id='test',panel='test',fuel=10,material=5,ready=8,arm='A1',bits=[0,1],tie='strict',bypass=False);d.update(kw);return d
    def check(name,c,expect):
        r=simulate(c)
        assert all(r['outcomes'][k]==v for k,v in expect.items()),(name,r['outcomes'])
        tests.append(name);return r
    check('baseline',case(arm='A0'),{'Y_star':1})
    check('repaired',case(),{'Y_R':1,'Y_star':1,'Y_T2':1})
    check('OFF_single',case(arm='A2'),{'Y_H':0,'Y_star':0})
    check('fuel_boundary',case(fuel=9),{'Y_R':1,'Y_H':1,'Y_T':0})
    check('material_boundary',case(material=4),{'Y_R':0,'Y_H':0})
    check('late',case(ready=14),{'Y_R':1,'Y_H':0})
    check('tie_strict',case(ready=9),{'Y_H':0})
    check('tie_ready_first',case(ready=9,tie='ready_first'),{'Y_star':1})
    check('bypass_OFF',case(arm='A2',bypass=True),{'Y_star':1})
    check('bypass_no_production',case(arm='A3',bypass=True),{'Y_V':1,'Y_F':0})
    check('tamper',case(perturb='tamper'),{'Y_T':1,'Y_V':0})
    check('wrong_nonce',case(perturb='wrong_ack'),{'Y_H':0})
    check('missing_child_work_apparatus',case(perturb='no_child_apparatus'),{'Y_V':1,'Y_F':0})
    check('missing_child_fuel',case(perturb='no_child_fuel'),{'Y_V':1,'Y_F':0})
    check('sham',case(perturb='sham_repair'),{'Y_R':0,'Y_H':0})
    r=check('stale_completion',case(perturb='stale_repair'),{'Y_R':0,'Y_H':0})
    assert any(e.get('failure_reason')=='stale_repair_epoch' for e in r['log'])
    a=simulate(case());b=simulate(case(arm='A2'))
    assert a['pre_snapshot_hash']==b['pre_snapshot_hash'];tests.append('paired_snapshot')
    return {'passed':len(tests),'tests':tests}

def summarize(rows):
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['case']['panel'],r['case']['arm'])].append(r)
    panels={f'{p}:{a}':dict(n=len(rs),means={k:sum(r['outcomes'][k] for r in rs)/len(rs) for k in rs[0]['outcomes']}) for (p,a),rs in groups.items()}
    main=[r for r in rows if r['case']['panel']=='primary'];pairs=collections.defaultdict(dict)
    for r in main:
        c=r['case'];pairs[(c['fuel'],c['material'],c['ready'],tuple(c['bits']))][c['arm']]=r
    contrasts=[]
    for key,arms in sorted(pairs.items()):
        assert len(arms)==5 and len({r['pre_snapshot_hash'] for r in arms.values()})==1
        assert arms['A2']['outcomes']['Y_H']==0, 'OFF single-channel violation'
        contrasts.append(dict(state=list(key),repair=arms['A1']['outcomes']['Y_star']-arms['A2']['outcomes']['Y_star'],
             production=arms['A2']['outcomes']['Y_star']-arms['A3']['outcomes']['Y_star'],
             versus_intact=arms['A1']['outcomes']['Y_star']-arms['A0']['outcomes']['Y_star']))
    return dict(tasks=len(rows),panels=panels,paired_primary_states=len(pairs),contrasts=contrasts,
                mean_repair=sum(x['repair'] for x in contrasts)/len(contrasts) if contrasts else None,
                failures=dict(collections.Counter(r['first_failed_stage'] or 'none' for r in rows)),
                successful_primary_states=[r['case'] for r in main if r['case']['arm']=='A1' and r['outcomes']['Y_star']],
                scope='Exact declared finite class; no inference about origin of laws/organization; no statistical CI')

def environment():
    def read(p):
        try:return Path(p).read_text().strip()
        except OSError:return None
    return dict(python=platform.python_version(),platform=platform.platform(),machine=platform.machine(),
                cpu_count=os.cpu_count(),affinity=sorted(os.sched_getaffinity(0)),cpu_quota=read('/sys/fs/cgroup/cpu.max'),
                memory_limit=read('/sys/fs/cgroup/memory.max'),cpuinfo=read('/proc/cpuinfo').split('\n')[:8],
                thread_env={k:os.getenv(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']},
                scientific_dependencies='Python standard library plus pinned pure-Python NOW modules; no BLAS calls')

def main():
    start=time.perf_counter();ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--out',default='output')
    ap.add_argument('--mode',choices=['tests','calibration','main'],required=True);ap.add_argument('--source-commit',default='local')
    ap.add_argument('--forecast');ap.add_argument('--resume',action='store_true');args=ap.parse_args()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('hard wall 120s')));signal.alarm(120)
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024*1024,1024*1024*1024))
    bind_base(args.base);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();cases=all_cases();checks=unit_checks()
    if args.mode=='tests':print(json.dumps(checks));return
    selected=cases if args.mode=='main' else [c for c in cases if (c['panel']=='primary' and c['fuel']==10 and c['material']==5 and c['bits']==[0,0]) or c['panel']!='primary' and c['bits']==[0,0]]
    env=environment();save(out/'ENVIRONMENT.json',env)
    save(out/'SOURCE.json',dict(source_commit=args.source_commit,script_sha256=source_hash,base_commit='da72a3a89176b77ceca75779923029534fd26b99',base_hashes=BASE_HASHES,cases_digest=digest(cases)))
    save(out/'CASES.json',selected);save(out/'CHECKS.json',checks)
    rows=[];timers=[];resumed=0
    for c in selected:
        t=time.perf_counter();path=out/'rows'/(c['id']+'.json')
        if args.resume and path.exists():
            row=json.loads(path.read_text());assert row['case']==c and row['source_hash']==source_hash;resumed+=1
        else:
            row=simulate(c);row['source_hash']=source_hash;save(path,row)
        rows.append(row);timers.append(dict(id=c['id'],panel=c['panel'],seconds=time.perf_counter()-t))
        save(out/'CHECKPOINT.json',dict(mode=args.mode,completed=len(rows),total=len(selected),source_hash=source_hash,last_id=c['id']))
    summary=summarize(rows);save(out/'SUMMARY.json',summary);save(out/'TASK_TIMERS.json',timers)
    # Six views requested by the design, with full trace files retained separately.
    save(out/'TABLES.json',dict(initial=[dict(id=r['case']['id'],case=r['case'],snapshot_hash=r['pre_snapshot_hash']) for r in rows],
         interventions=[dict(id=r['case']['id'],events=[e for e in r['log'] if e['event_type'] in ['damage','produce','reserve_repair','repair_start','repair_done']]) for r in rows],
         channel=[dict(id=r['case']['id'],Y_R=r['outcomes']['Y_R'],Y_H=r['outcomes']['Y_H'],times=r['repair_completion_times']) for r in rows],
         transfer=[dict(id=r['case']['id'],Y_T=r['outcomes']['Y_T'],Y_V=r['outcomes']['Y_V']) for r in rows],
         continuation=[dict(id=r['case']['id'],outcomes=r['outcomes'],first_failure=r['first_failed_stage']) for r in rows],
         balance=[dict(id=r['case']['id'],initial=r['initial_balance'],final=r['final_balance'],nodes=r['final_state']['nodes'],hold=r['final_state']['hold']) for r in rows]))
    forecast=json.loads(Path(args.forecast).read_text()) if args.forecast else None
    core=time.perf_counter()-start
    archive=out/'FULL_OUTPUT.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for p in sorted(out.rglob('*.json')):z.write(p,p.relative_to(out))
    wall=time.perf_counter()-start
    usage=resource.getrusage(resource.RUSAGE_SELF)
    process=dict(mode=args.mode,source_commit=args.source_commit,script_sha256=source_hash,tasks=len(rows),planned=len(selected),resumed=resumed,
        process_body_wall_seconds=wall,core_including_reports_seconds=core,archive_seconds=wall-core,
        task_seconds=sum(t['seconds'] for t in timers),cpu_seconds=usage.ru_utime+usage.ru_stime,max_rss_mib=usage.ru_maxrss/1024,
        environment=env,environment_digest=digest(env),forecast=forecast,
        runtime_gate=('PASS' if forecast['lower_seconds']<=wall<=forecast['upper_seconds'] and digest(env)==forecast['environment_digest'] else 'REVIEW_REQUIRED') if forecast else 'CALIBRATION',
        output_bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),archive_bytes=archive.stat().st_size,
        technical_pass=True,scientific_confirmation=False,timer_scope='main() entry through archive; Python startup/job wrapper excluded and reported separately by worker')
    save(out/'PROCESS.json',process);print(json.dumps(process))

if __name__=='__main__':main()
