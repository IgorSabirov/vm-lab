"""Exact arithmetic controls for the family-number review; no fitted masses or couplings."""
from fractions import Fraction
from itertools import product
from math import gcd
import json

# Left-handed SM fields, conjugating every right-handed charged fermion.
# Entries: name, color dimension, weak dimension, hypercharge 6Y, color cubic sign.
FAMILY = (("Q",3,2,1,1), ("u^c",3,1,-4,-1), ("d^c",3,1,2,-1),
          ("L",1,2,-3,0), ("e^c",1,1,6,0), ("nu^c",1,1,0,0))
# Wilson characters of the author's Spin(10) 16, Eq. (24), in matching order.
CHARGES = dict(zip(("Q","u^c","d^c","L","e^c","nu^c"),
                   ((1,2),(2,2),(2,0),(0,0),(0,2),(0,1))))

def anomalies():
    return {
        "color_cubic":sum(w*t for _,c,w,h,t in FAMILY),
        "color_squared_times_6Y":sum(w*h for _,c,w,h,t in FAMILY if c==3),
        "weak_squared_times_6Y":sum(c*h for _,c,w,h,t in FAMILY if w==2),
        "sixY_cubed":sum(c*w*h**3 for _,c,w,h,t in FAMILY),
        "gravity_times_6Y":sum(c*w*h for _,c,w,h,t in FAMILY),
        "weak_doublets_mod_two":sum(c for _,c,w,h,t in FAMILY if w==2)%2}

def invariant_multiplicities(copies):
    modes=[(a,b) for _ in range(copies) for a,b in product(range(3),repeat=2)]
    return {f:sum((a+x)%3==(b+y)%3==0 for a,b in modes) for f,(x,y) in CHARGES.items()}

def check():
    four=anomalies()
    assert not any(four.values())
    sectors={str(m):invariant_multiplicities(m) for m in (1,2,3,4)}
    assert all(set(counts.values())=={int(m)} for m,counts in sectors.items())
    assert sum(c*w*sectors["3"][name] for name,c,w,*_ in FAMILY)==48
    # In the SU(4) bundle model: c3/2 upstairs in authors' convention anti16 minus 16.
    assert Fraction(-54,2*9)==-3
    six={str(d):[n for n in range(1,13) if d*n%6==0] for d in (2,4)}
    assert all(allowed==[3,6,9,12] for allowed in six.values())
    # All leptons in 3, q quark families in 3, remaining N-q in anti-3
    # (simultaneously conjugating every representation reverses the anomaly sign).
    solutions=[(n,q,11-2*n) for n in range(1,13) for q in range(n+1)
               if n+3*(2*q-n)==0]
    assert [n for n,q,b0 in solutions if b0>0]==[3]
    # M^(-8) has order 3 iff m divides 24 and m does not divide 8.
    order3=[m for m in range(1,25) if m//gcd(m,8)==3]
    assert order3==[3,6,12,24]
    return {"sm_one_family_anomalies":four,"BHOP_Wilson_invariants_by_number_of_regular_reps":sectors,
            "BHOP_chiral_index_on_quotient":-3,"six_dimensions_allowed_N_up_to_12":six,
            "minimal_331_solutions_N_q_b0_up_to_12":solutions,"H6_dimensions_with_relative_order_3":order3,
            "CKM_physical_phases":{str(n):(n-1)*(n-2)//2 for n in (2,3,4)}}
if __name__=="__main__":
    print(json.dumps(check(),ensure_ascii=False,indent=2))
