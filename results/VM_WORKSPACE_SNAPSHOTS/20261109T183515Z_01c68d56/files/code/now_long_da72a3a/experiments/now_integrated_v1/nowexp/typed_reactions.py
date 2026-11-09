"""Explicit R070/R071 semantics; material/work payment does not derive the law."""
from collections import Counter


def reaction(state_type, access, mode, chosen_access=None):
    q=Counter({k:n for k,n in dict(access).items() if n>0})
    if mode not in ('V1','V2','A'):raise ValueError('unknown token semantics')
    a=state_type if mode=='A' and chosen_access is None else chosen_access
    if a is None:
        if not q:return None
        a=min(k for k,n in q.items() if n>0)
    if mode!='A' and q[a]<=0:return None
    if mode=='A' and a!=state_type and q[a]<=0:return None
    result=(state_type+a)%3  # Given finite composition table, not a physical derivation.
    added=result if mode=='V2' else a
    before=dict(q);q[added]+=1
    return dict(state_type=result,access=dict(q),added_type=added,before=before,
                material_required=1,fuel_required=1,semantics=mode)


def exhaustive_v1_control():
    rows=[]
    for x in range(3):
        for mask in range(1,8):
            q={k:1 for k in range(3) if mask&(1<<k)}
            for a in q:
                r=reaction(x,q,'V1',a)
                rows.append(dict(state=x,access=q,chosen=a,same_support=set(r['access'])==set(q)))
    return dict(all_same_support=all(x['same_support'] for x in rows),cases=rows,
                inference='Exact finite check of the declared V1 law; no restriction on other laws.')
