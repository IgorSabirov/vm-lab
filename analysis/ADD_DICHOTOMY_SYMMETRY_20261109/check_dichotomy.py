"""Bounded, offline checks of an analytic criterion against the pinned NOW carrier.

No VM run. No modification to the scientific executor. Run from any directory.
"""
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/now_integrated_v1'))
from nowexp.carrier import full_step, fixture

SOURCE_BLOB = '6e44c12cd1f27aadc9e2c73c1f82222944cd2e7b'

def canonical(w):
    w = tuple(w)
    return min(w[i:] + w[:i] for i in range(len(w)))

def motifs(w):
    return (sum(s in (3, 12) for s in w),
            sum((s, w[(i+1) % len(w)]) in ((1, 2), (4, 8))
                for i, s in enumerate(w)))

def half_counts(w):
    return tuple(sum((s & mask) == value for s in w)
                 for mask, value in ((5,1),(5,4),(5,5),(10,2),(10,8),(10,10)))

def compatibility(w):
    a1,a2,a12,b1,b2,b12 = half_counts(w)
    return a1*b1 + a2*b2

def first_split_prediction(w):
    L = len(w)
    distances = [(j-i) % L for i,b in enumerate(w) for j,a in enumerate(w)
                 if ((a & 5), (b & 10)) in ((1,2),(4,8))]
    return min(distances) if distances else None

def quiet_count(L):
    return 2*9**L + 2*8**L - 4*6**L + 4**L

def particle_counts(w):
    return [sum((s >> i) & 1 for s in w) for i in range(4)]

def trace(w, steps=12):
    rows = []
    for t in range(steps+1):
        rows.append(dict(t=t,word=w,L=len(w),motifs=motifs(w),K=compatibility(w)))
        w,_ = full_step(w)
    return rows

def inverse_half(w):
    return [(w[i-1] & 5) | (w[i] & 10) for i in range(len(w))]

def collision(w):
    return inverse_half(full_step(w)[0])

def R(w):
    return [((s&1)<<3)|((s&2)<<1)|((s&4)>>1)|((s&8)>>3) for s in w]

def main():
    started=time.perf_counter()
    path=ROOT/'experiments/now_integrated_v1/nowexp/carrier.py'
    b=path.read_bytes()
    actual=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
    if actual != SOURCE_BLOB:
        raise SystemExit('Carrier differs from the pinned source: '+actual)
    counts=[]; checked=0; Eprev,E=2,14
    for L in range(1,5):
        if L>1:Eprev,E=E,14*E-2*Eprev
        e0=quiet=0; delay={}; periods={}
        for tup in itertools.product(range(16), repeat=L):
            w=list(tup); h=half_counts(w); out,_=full_step(w)
            assert half_counts(out)==h
            checked+=1
            if any(motifs(w)):continue
            e0+=1; prediction=first_split_prediction(w); first=None; first_growth=None
            z=w[:]; found_period=None
            for t in range(L+2):
                s,m=motifs(z)
                assert m==0 and half_counts(z)==h
                if s and first is None:first=t
                nxt,_=full_step(z)
                assert len(nxt)-len(z)==s
                if len(nxt)>L and first_growth is None:first_growth=t+1
                if canonical(nxt)==canonical(w) and found_period is None:found_period=t+1
                z=nxt
            assert first==prediction
            if prediction is None:
                quiet+=1
                assert compatibility(w)==0 and first_growth is None and L%found_period==0
                periods[str(found_period)]=periods.get(str(found_period),0)+1
            else:
                assert compatibility(w)>0 and 1<=prediction<=L-1
                assert first_growth==prediction+1<=L
                delay[str(prediction)]=delay.get(str(prediction),0)+1
        assert e0==E and quiet==quiet_count(L)
        counts.append(dict(L=L,E0=e0,quiet=quiet,growing=e0-quiet,
                           first_split_counts=delay,quiet_period_counts=periods))
    witnesses={str(w):trace(w) for w in ([5,10],[9,6],[0,4,9],[0,11,0])}
    assert particle_counts([5,10])==particle_counts([9,6])==[1,1,1,1]
    w=[0,3]; ir=collision(R(w)); ri=R(collision(w))
    assert canonical(ir)!=canonical(ri)
    w2=[0,2,1]; T=lambda w:collision(R(w)); t2=T(T(w2))
    assert canonical(t2)!=canonical(w2)
    fixtures={}
    for kind in ('add_quiet','add_growing'):
        w=fixture(kind,['N0','N1','N2'])['word']
        fixtures[kind]=dict(word=w,particles=particle_counts(w),half_counts=half_counts(w),
                            K=compatibility(w),first_split=first_split_prediction(w))
    # All homogeneous E0 words remain homogeneous; check a finite instance.
    homogeneous=[]
    for s in range(16):
        if not any(motifs([s]*4)):
            out,_=full_step([s]*4)
            assert out==[s]*4 and compatibility(out)==0
            homogeneous.append(s)
    exact_counts=[];prev,now=2,14
    for L in range(1,13):
        if L>1:prev,now=now,14*now-2*prev
        exact_counts.append(dict(L=L,E0=now,quiet=quiet_count(L),quiet_fraction=quiet_count(L)/now))
    result=dict(status='PASS',source_commit='0ed4349731e3e8dbfc6ac6ca7a1dd6d8b3ef6cf6',
        carrier_blob=actual,all_words_checked=checked,E0_words_checked=sum(x['E0'] for x in counts),
        enumeration=counts,closed_form_counts=exact_counts,witnesses=witnesses,
        same_particle_vector=[1,1,1,1],fixtures=fixtures,
        author_R_counterexample=dict(initial=[0,3],IR=ir,RI=ri),
        author_T_squared_counterexample=dict(initial=w2,T_squared=t2),
        homogeneous_quiet_symbols=homogeneous,
        scope='Pure four-bit carrier; inherited same-orientation I; not full NOW or author C2 attestation',
        seconds=time.perf_counter()-started)
    out=Path(__file__).with_name('CHECKS.json');out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','all_words_checked','E0_words_checked','enumeration','fixtures','seconds')}))

if __name__=='__main__':main()
