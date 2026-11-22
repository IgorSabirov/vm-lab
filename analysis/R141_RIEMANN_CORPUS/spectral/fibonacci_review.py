"""Check the numerical assertions in the review using the committed raw inputs."""
from decimal import Decimal, localcontext
from hashlib import sha256
from itertools import permutations
import json
import math
from pathlib import Path
import sys


def analyze(folder, zero_file):
    ex=json.loads((folder/'experiments.json').read_text())
    selection=json.loads((folder/'selected.json').read_text())
    replay=json.loads((folder/'bbn_replay.json').read_text())
    marks=replay['spectrum_tests']['marks']
    white={}
    for law,rows in marks.items():
        position=rows['equal']['obs_sd'][0]**2
        white[law]=rows['common_chi2_2']['obs_sd'][0]**2-position
        for key,row in rows.items():
            assert math.isclose(row['obs_sd'][0]**2,position+row['mark_var']*white[law],rel_tol=1e-12)
    assert math.isclose(white['GOE'],white['GUE'],rel_tol=1e-13)
    # Fixed training fits; evaluate exactly which terms change on the same eight held-out records.
    fe=ex['21803002']
    cuts=fe['tests']
    cut=cuts['0.1']['cut_eV']
    x=[row[-1] for row in selection['21803002']['rows'][fe['split']:]]
    assert cut<min(x)
    pt,exp=cuts['0.1']['scale_eV']
    change_norm=cut*(-1/exp)-math.log(math.erfc(math.sqrt(cut/pt)))
    log_score=sum(-.5*math.log(v)-v/pt-.5*math.log(math.pi*pt)+v/exp+math.log(exp) for v in x)/len(x)
    assert math.isclose(log_score+change_norm,cuts['0.1']['mean_log_PT_minus_exp'],abs_tol=1e-12)
    # In the small series the test used one stratum, so enumerate the exact permutation distribution.
    small=selection['10172047']['rows']
    g=[b[1]-a[1] for a,b in zip(small,small[1:])]
    z=[r[-1] for r in small[:-1]]
    def ranks(values):
        assert len(set(values))==len(values)
        return [sorted(values).index(x)-len(values)//2 for x in values]
    left,right=ranks(g),ranks(z)
    observed=sum(a*b for a,b in zip(left,right))
    hits=sum(abs(sum(a*b for a,b in zip(left,rr)))>=abs(observed) for rr in permutations(right))
    raw=zero_file.read_bytes()
    assert sha256(raw).hexdigest()=='c3ea7085b25c16caafb43db250efefd171b627a34c3097498027751226d61c28'
    with localcontext() as ctx:
        ctx.prec=55
        roots=[Decimal(row['gamma']) for row in json.loads(raw)['roots']]
        assert len(roots)==657
        product=math.prod(1-1/t**2 for t in roots)
        first_order=math.prod(1-1/t**2 for t in roots[:650])*(1-sum(1/t**2 for t in roots[650:]))
        approx=Decimal('0.9771416745871240308814')
    return dict(common_white_variance=white,PT_score_unconditional_after_refit=log_score,
                PT_score_conditional_normalization=change_norm,heldout_count=len(x),
                exact_small_gap_permutation=[hits,math.factorial(len(right))],
                hadamard_P657=str(product),absolute_error_vs_quoted_target=str(product-approx),
                first_order_difference_using_actual_seven=str(first_order-product),
                redraw_ratio=replay['wrong_independent_time_sd_over_coherent'],
                one_DH_accuracy=replay['spectrum_tests']['idealized_single_DH_gaussian_accuracy'])


if __name__=='__main__':
    print(json.dumps(analyze(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
