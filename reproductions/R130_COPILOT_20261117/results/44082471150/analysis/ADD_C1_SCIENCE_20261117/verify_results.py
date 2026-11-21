"""Read back raw files, check accounting and independent combinatorial entropy."""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent


def local_reference(word,r):
    n=len(word); k=min(n,2*r+1)
    particles=[(s&1)+(s>>1) for s in word]
    q=sum(particles[:k])
    lookup=[math.log(math.comb(2*k,p)) for p in range(2*k+1)]
    total=0.0
    for i in range(n):
        total+=lookup[q]
        q+=particles[(i+k)%n]-particles[i]
    return total/n,total


def main():
    results=json.loads((HERE/'RESULTS.json').read_text())
    summary=json.loads((HERE/'LONG_SUMMARY.json').read_text())+json.loads((HERE/'EXTENDED_SUMMARY.json').read_text())
    ledger=[]; transitions=0
    for item in summary:
        name=item['name']
        with gzip.open(HERE/(name+'.csv.gz'),'rt') as f:
            rows=list(csv.DictReader(f))
        assert len(rows)==item['steps']+1
        assert [int(x['t']) for x in rows]==list(range(len(rows)))
        assert int(rows[-1]['L'])==item['final_L']
        for a,b in zip(rows[:-1],rows[1:]):
            assert int(b['L'])-int(a['L'])==int(a['split_next'])-int(a['merge_next'])
            assert (int(a['na']),int(a['nb']))==(item['na'],item['nb'])
            transitions+=1
        words=json.load(gzip.open(HERE/(name+'_words.json.gz'),'rt'))
        for key,row in [('initial',rows[0]),('final',rows[-1])]:
            w=words[key]; n=len(w); p=sum((s&1)+(s>>1) for s in w)
            assert n==int(row['L'])
            exact=math.log(math.comb(2*n,p))
            assert abs(exact-float(row['S_global']))<1e-7
            for r in (1,5):
                local,total=local_reference(w,r)
                assert math.isclose(local,float(row[f'S_local_r{r}']),abs_tol=1e-8)
                assert math.isclose(total,float(row[f'sum_local_r{r}']),rel_tol=1e-9,abs_tol=1e-7)
        minimum=min(int(x['L']) for x in rows)
        first_min=next(int(x['t']) for x in rows if int(x['L'])==minimum)
        last_merge=max((int(x['t']) for x in rows[:-1] if int(x['merge_next'])>0),default=None)
        if '_extended_' in name:
            base=name.replace('_extended','')
            with gzip.open(HERE/(base+'.csv.gz'),'rt') as f:
                baseline=list(csv.DictReader(f))
            for a,b in zip(baseline,rows):
                for key in a:
                    if a[key]!='':
                        assert a[key]==b[key], (name,key,a[key],b[key])
        ledger.append({'name':name,'rows':len(rows),'minimum_L':minimum,'first_minimum_t':first_min,
                       'last_merge_input_t':last_merge})
    assert transitions==results['long_steps']+results['extension_steps']
    with gzip.open(HERE/'EXHAUSTIVE.csv.gz','rt') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==results['exhaustive_trajectories']
    record={'status':'PASS','raw_trajectory_files':len(summary),'checked_transitions':transitions,
            'exhaustive_summary_rows':len(rows),'independent_entropy_endpoints':2*len(summary),
            'extended_prefixes_match_original':True,'trajectory_ledger':ledger}
    (HERE/'VERIFICATION.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k!='trajectory_ledger'}))


if __name__=='__main__':
    main()
