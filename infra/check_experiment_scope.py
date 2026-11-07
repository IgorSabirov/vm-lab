"""Fail closed when a partial implementation is presented as the complete design.

This checks the claim, not scientific correctness. Completeness needs both named
interventions and executed evidence tied to the same source/configuration.
"""
import argparse
import json
from pathlib import Path


def audit(graph, mapping, evidence=None):
    required={x['id']:x for x in graph['cross_branch_contrasts']}
    supplied={x['id']:x for x in mapping['comparisons']}
    rows=[]
    for identity, requirement in required.items():
        item=supplied.get(identity,{})
        implemented=item.get('implementation_status')=='IMPLEMENTED'
        observations=[] if evidence is None else evidence.get('comparisons',{}).get(identity,[])
        executed=implemented and bool(observations) and all(
            x.get('complete') and x.get('source_commit')==evidence.get('source_commit')
            and x.get('config_digest')==evidence.get('config_digest') for x in observations)
        rows.append(dict(id=identity,title=requirement['title'],
                         required_intervention=requirement['contrast'],
                         decision=requirement['decision'],
                         implemented=implemented,executed=executed,
                         implementation_limit=item.get('limit','Missing implementation'),
                         evidence=observations))
    return dict(schema=1,full_design_implemented=all(x['implemented'] for x in rows),
                full_design_executed=all(x['executed'] for x in rows),
                required_count=len(required),rows=rows,
                missing_from_map=sorted(set(required)-set(supplied)),
                unexpected_in_map=sorted(set(supplied)-set(required)),
                scientific_confirmation=False)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--design',type=Path,required=True)
    p.add_argument('--implementation',type=Path,required=True)
    p.add_argument('--evidence',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--require-full',action='store_true')
    args=p.parse_args()
    read=lambda path:json.loads(path.read_text())
    result=audit(read(args.design),read(args.implementation),read(args.evidence) if args.evidence else None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
    if args.require_full and not result['full_design_executed']:
        raise SystemExit(2)


if __name__=='__main__':main()
