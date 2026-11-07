"""Targeted audit of the user's unmodified embedded code, not a new engine."""
import argparse
import json
from pathlib import Path
import time
from fractions import Fraction as F
import neighbor_multi as n


class TraceSim(n.Sim):
    def __init__(self, cfg):
        self.trace = []
        super().__init__(cfg)

    def handle(self, now, kind, payload):
        super().handle(now, kind, payload)
        self.trace.append(dict(t=now, kind=kind, payload=payload.copy(),
            sender_states={tid:t.state for tid,t in self.V.tokens.items()},
            return_reserved={tid:t.return_reserved for tid,t in self.V.tokens.items()}))


def calibration():
    start=time.perf_counter()
    out=[n.run_scenario(), n.run_scenario(lease=F(3,2)),
         n.run_scenario(lease=F(10),loss_token='r1',loss_time=F(7,2))]
    elapsed=time.perf_counter()-start
    return dict(mode='calibration',scenarios=3,scenario_seconds=elapsed,
                event_count=sum(x['event_count'] for x in out),environment=n.environment())


def audit():
    start=time.perf_counter()
    pre=TraceSim(dict(req_delay=F(3),alloc_time=F(1)))
    pre_summary=pre.run()
    alloc=next(e for e in pre.trace if e['kind']=='allocate')
    first_req=min(e['t'] for e in pre.trace if e['kind']=='req_arrive')
    premature=alloc['t']<first_req and all(v=='WAIT_ACK' for v in alloc['sender_states'].values())

    notice=TraceSim(dict(probes=[('V_return_reserved','r1',F(19,4))]))
    notice_summary=notice.run()
    cargo=next(e for e in notice.trace if e['kind']=='cargo_arrive' and e['payload']['token']=='r1')
    receipt=next(e for e in notice.trace if e['kind']=='valid_notice_V' and e['payload']['token']=='r1')
    dx=abs(notice.W['W1'].x-notice.V.x)
    dt=receipt['t']-cargo['t']
    ftl=dt<dx
    control=n.run_scenario(notice_delay=F(1),probes=[('V_return_reserved','r1',F(19,4))])

    requests=[('r1','W1',F(1,2)),('r2','W1',F(1,2))]
    same_w=[n.run_scenario(requests=requests,reverse=reverse) for reverse in (False,True)]
    result=dict(mode='targeted audit',environment=n.environment(),scenarios=5,
        premature_request_use=dict(observed=premature,allocation=alloc,first_request_arrival=first_req,summary=pre_summary),
        superluminal_notification=dict(observed=ftl,emit_t=cargo['t'],receive_t=receipt['t'],distance=dx,dt=dt,c=1,
            probe_t=F(19,4),reserved_with_source_delay=notice_summary['probes']['V_return_reserved:r1'],
            reserved_with_causal_delay=control['probes']['V_return_reserved:r1'],summary=notice_summary),
        same_receiver_contention=dict(classifications=[x['classification'] for x in same_w],
            order_sensitive=same_w[0]['classification']!=same_w[1]['classification'],
            summaries=same_w,interpretation='Not in original two-receiver fixture; a shared-receiver collision needs a declared local batch/tie rule, not an arbitrary scheduler order.'),
        scope='No repair of supplied code; these checks do not accept a physical architecture.',
        compute_seconds=time.perf_counter()-start)
    assert premature and ftl
    assert result['superluminal_notification']['reserved_with_source_delay']==0
    assert result['superluminal_notification']['reserved_with_causal_delay']==F(3,8)
    assert result['same_receiver_contention']['order_sensitive']
    return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--calibrate',action='store_true');ap.add_argument('--out',required=True)
    args=ap.parse_args();out=calibration() if args.calibrate else audit()
    Path(args.out).write_text(json.dumps(out,default=str,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:out[k] for k in ('mode','scenarios')}))


if __name__=='__main__':main()
