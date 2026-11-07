"""Bounded, independent reconstruction of the single-token v3 witness.

Not a full distributed engine. Fractions are exact; JSON numbers are strings.
Local decision functions receive one node and delivered message content only.
The simulator owns transport bookkeeping; its audit is never a policy input.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import heapq
import itertools
import json
import os
from pathlib import Path
import platform
import resource
import time

Q = F(1, 2)


@dataclass
class Sender:
    stock: F = Q
    escrow: F = F(0)
    deadline: F = F(0)
    state: str = 'INIT'


@dataclass
class Receiver:
    stock: F = F(0)
    reserved: F = F(0)
    deadline: F = F(0)
    state: str = 'INIT'


def on_ack(v, now, amount, defect=None):
    # No receiver state/expiry or global loss ledger is available here.
    valid = v.state == 'WAIT_ACK' and now < v.deadline
    if defect == 'late_ack':
        valid = v.state in ('WAIT_ACK', 'EXPIRED_ACK')
    if not valid:
        return F(0)
    v.escrow -= amount
    v.state = 'COMMITTED'
    return amount


def on_arrival(w, now, amount, commit_evidence, defect=None):
    # Evidence is carried by this parcel; no sender live-state lookup.
    valid = (commit_evidence and w.state == 'RESERVED'
             and now < w.deadline and w.reserved >= amount
             and w.stock + w.reserved <= Q)
    if defect == 'stale_accept':
        valid = commit_evidence
    if valid:
        w.stock += amount
        w.reserved = max(F(0), w.reserved - amount)
        w.state = 'ARRIVED_VALID'
        return 'VALID'
    return 'STALE_AUTHORIZED' if commit_evidence else 'UNAUTHORIZED'


def simulate(lease=Q, ack_wait=F(3), delay=F(1), reverse=False,
             duplicates=False, loss=False, defect=None):
    v, w = Sender(), Receiver()
    transit = returning = lost = F(0)
    delivered = returned = F(0)
    queue, events, violations = [], [], []
    seq = 0
    parcel_consumed = return_consumed = False
    classification = 'NO_SEND'
    reserved_probe = None

    def put(t, kind):
        nonlocal seq
        seq += 1
        # Physical local boundary convention is explicit; insertion order is not it.
        phase = 0 if kind in ('expire_ack', 'expire_cap') else 1
        heapq.heappush(queue, (F(t), phase, -seq if reverse else seq, kind))

    def snap():
        return dict(v=v.stock, escrow=v.escrow, w=w.stock, reserved=w.reserved,
                    transit=transit, returning=returning, lost=lost)

    def audit():
        s = snap()
        if s['v'] + s['escrow'] + s['w'] + transit + returning + lost != Q:
            violations.append('resource_balance')
        if any(x < 0 for x in s.values()):
            violations.append('nonnegative')
        if v.stock + v.escrow > Q or w.stock + w.reserved > Q:
            violations.append('capacity')

    put(1, 'allocate')  # request sent at (0,1), delivered at (1,0)
    while queue:
        now, _, _, kind = heapq.heappop(queue)
        before = snap()
        if kind == 'allocate':
            v.stock -= Q
            v.escrow += Q
            v.deadline = now + ack_wait
            v.state = 'WAIT_ACK'
            if defect != 'no_expiry':
                put(v.deadline, 'expire_ack')
            put(now + 1, 'offer')
        elif kind == 'offer':
            assert w.stock + w.reserved + Q <= Q
            w.reserved += Q
            w.deadline = now + lease
            w.state = 'RESERVED'
            if defect != 'no_expiry':
                put(w.deadline, 'expire_cap')
            put(now + 1, 'ack')
            if duplicates:
                put(now + 1, 'ack')
                put(now + 10, 'ack')
        elif kind == 'expire_ack':
            if v.state == 'WAIT_ACK':
                v.stock += v.escrow
                v.escrow = F(0)
                v.state = 'EXPIRED_ACK'
        elif kind == 'expire_cap':
            if w.state == 'RESERVED':
                w.reserved = F(0)
                w.state = 'EXPIRED_CAP'
        elif kind == 'ack':
            sent = on_ack(v, now, Q, defect)
            if sent:
                transit += sent
                put(now + delay, 'arrival')
                if duplicates:
                    put(now + delay, 'arrival')
                if loss:
                    # Loss at (3.5,0.5); query (3.6,1) is spacelike from it.
                    assert delay == 1
                    put(now + Q, 'loss')
                    put(now + F(3, 5), 'probe')
        elif kind == 'loss':
            lost += transit
            transit = F(0)
            parcel_consumed = True
            classification = 'LOST'
            if defect == 'instant_release':
                w.reserved = F(0)
                w.state = 'LOSS_ORACLE'
            # Detector survives on channel; notice travels 0.5 at c=1.
            put(now + Q, 'notice')
            if duplicates:
                put(now + Q, 'notice')
                put(now + 20, 'notice')
        elif kind == 'probe':
            reserved_probe = w.reserved
        elif kind == 'notice':
            if w.state == 'RESERVED':
                w.reserved = F(0)
                w.state = 'LOSS_NOTIFIED'
        elif kind == 'arrival' and not parcel_consumed:
            parcel_consumed = True
            classification = on_arrival(w, now, transit, True, defect)
            if classification == 'VALID':
                delivered += transit
                transit = F(0)
            else:
                returning += transit
                transit = F(0)
                put(now + 1, 'return')
                if duplicates:
                    put(now + 1, 'return')
                    put(now + 10, 'return')
        elif kind == 'return' and not return_consumed:
            return_consumed = True
            # This isolated one-token scenario guarantees capacity at V.
            # Multiple-token returns require a separate admission rule.
            assert v.stock + v.escrow + returning <= Q or defect is not None
            v.stock += returning
            returned += returning
            returning = F(0)
        audit()
        events.append(dict(t=now, event=kind, before=before, after=snap()))
    return dict(final=snap(), classification=classification, delivered=delivered,
                returned=returned, reserved_probe=reserved_probe,
                violations=sorted(set(violations)), events=events,
                obligations_closed=(v.escrow == w.reserved == transit == returning == 0))


def reference(lease, ack_wait, delay):
    if ack_wait <= 2:
        return 'NO_SEND'
    return 'VALID' if lease > 1 + delay else 'STALE_AUTHORIZED'


def supplemental():
    central = simulate()
    progress = simulate(lease=F(3))
    lost = simulate(lease=F(10), loss=True, duplicates=True)
    controls = {
        'N1_instant_remote_release': simulate(lease=F(10), loss=True, defect='instant_release')['reserved_probe'] != Q,
        'N3_stale_acceptance': simulate(defect='stale_accept')['classification'] != reference(Q, F(3), F(1)),
        'N9_late_ack': 'nonnegative' in simulate(ack_wait=F(1), defect='late_ack')['violations'],
        'N10_no_expiry': not simulate(ack_wait=F(1), defect='no_expiry')['obligations_closed'],
    }
    # Separate exact counterexample: third store initially has 1/2. V sends 1/2,
    # then receives the third store's 1/2 before its own rejected parcel returns.
    # Both the old cargo and the new cargo exist: total initial mass is 1.
    return_capacity = dict(capacity=Q, filled_stock=Q, returning=Q,
        naive_final=2*Q, naive_overflow=Q,
        corrected_stock=Q, corrected_loss=Q, initial_total=2*Q,
        corrected_balance=(Q+Q == 2*Q))
    # Sufficient delivery condition from reservation time includes ACK travel.
    lease, ack_delay, process, cargo = F(3, 2), F(1), F(0), F(1)
    progress_gap = dict(lease=lease, ack_delay=ack_delay, processing=process, cargo=cargo,
        source_short_condition=(cargo+process < lease),
        actual_chain_fits=(ack_delay+process+cargo < lease),
        simulation=simulate(lease=lease)['classification'])
    assert all(controls.values())
    assert central['classification'] == 'STALE_AUTHORIZED' and central['final']['v'] == Q
    assert progress['classification'] == 'VALID' and progress['delivered'] == Q
    assert lost['reserved_probe'] == Q and lost['final']['lost'] == Q
    assert central['obligations_closed'] and lost['obligations_closed']
    return dict(central=central, progress=progress, remote_loss=lost,
                negative_controls_detected=controls,
                return_capacity_counterexample=return_capacity,
                missing_ack_time_counterexample=progress_gap)


def environment():
    def read(path):
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None
    return dict(python=platform.python_version(), platform=platform.platform(),
        affinity=sorted(os.sched_getaffinity(0)), cpu_count=os.cpu_count(),
        cpu_model=next((x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')), None),
        cpu_max=read('/sys/fs/cgroup/cpu.max'), memory_max=read('/sys/fs/cgroup/memory.max'),
        memory_current=read('/sys/fs/cgroup/memory.current'), libraries='stdlib only; Fraction; no BLAS',
        worker_threads=1, code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=240)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    start = time.perf_counter()
    env = environment()
    rows = []
    base_start = time.perf_counter()
    params = list(itertools.product([Q,F(1),F(2),F(3),F(4)],
                map(F,[1,2,3,4]), map(F,[1,2,3]), [False,True], [False,True]))
    # Stride for calibration to include successful/failed and duplicate variants.
    selected = params if args.limit == 240 else params[::10][:args.limit]
    for lease, ack, delay, reverse, duplicates in selected:
        out = simulate(lease, ack, delay, reverse, duplicates)
        expected = reference(lease, ack, delay)
        ok = out['classification'] == expected and not out['violations'] and out['obligations_closed']
        rows.append(dict(lease=lease, ack_wait=ack, delay=delay, reverse=reverse,
            duplicate_notifications=duplicates, expected=expected,
            actual=out['classification'], ok=ok, events=len(out['events'])))
    base_seconds = time.perf_counter()-base_start
    extra_start = time.perf_counter()
    extra = supplemental()
    extra_seconds = time.perf_counter()-extra_start
    result = dict(scope='single-token pilot, not P1-P10 full suite', environment=env,
        trajectories=len(rows), event_count=sum(r['events'] for r in rows),
        matched=sum(r['ok'] for r in rows), rows=rows, supplemental=extra,
        base_seconds=base_seconds, supplemental_seconds=extra_seconds,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Record measured compute section separately from full subprocess walltime.
    result['compute_seconds'] = time.perf_counter()-start
    Path(args.out).write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('trajectories','event_count','matched','compute_seconds','peak_rss_kib')}))
    assert result['trajectories'] == args.limit and result['matched'] == args.limit


if __name__ == '__main__':
    main()
