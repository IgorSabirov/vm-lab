"""Verify saved U008 output without running trajectories; Python standard library."""
import argparse, collections, hashlib, json, zipfile
from pathlib import Path

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('directory', type=Path, help='Directory containing FULL_OUTPUT.zip, PROCESS.json, JOB.json')
    ap.add_argument('--output', type=Path)
    args=ap.parse_args(); root=args.directory
    process=json.loads((root/'PROCESS.json').read_text())
    job=json.loads((root/'JOB.json').read_text())
    archive=root/'FULL_OUTPUT.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==process['archive_sha256']
    assert archive.stat().st_size==process['archive_bytes']
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        read=lambda name:json.loads(z.read(name))
        cases=read('CASES.json'); source=read('SOURCE.json'); summary=read('SUMMARY.json')
        rows=[read('rows/'+c['id']+'.json') for c in cases]
        tables=read('TABLES.json'); env=read('ENVIRONMENT.json')
        checkpoint=read('CHECKPOINT.json')
    assert len(cases)==len(rows)==process['tasks']==process['planned']==592
    assert len({c['id'] for c in cases})==592
    assert checkpoint['completed']==checkpoint['total']==592
    assert source['cases_digest']==digest(cases)
    assert process['source_commit']==source['source_commit']
    assert process['script_sha256']==source['script_sha256']==job['source_sha256']
    panels=collections.defaultdict(list); pairs=collections.defaultdict(dict)
    for c,r in zip(cases,rows):
        assert r['case']==c and r['source_hash']==source['script_sha256']
        assert r['initial_balance']==r['final_balance']
        assert all(e['balance']==r['initial_balance'] for e in r['log'])
        y=r['outcomes']; assert y['Y_star']==int(all(y[k] for k in ['Y_H','Y_T','Y_V','Y_F']))
        if y['Y_F']: assert r['child_output']==r['observer_xor_target']==(c['bits'][0]^c['bits'][1])
        panels[c['panel']+':'+c['arm']].append(r)
        if c['panel']=='primary':
            pairs[(c['fuel'],c['material'],c['ready'],tuple(c['bits']))][c['arm']]=r
            if c['arm']=='A1':assert y['Y_star']==int(c['fuel']>=10 and c['material']>=5 and c['ready']==8)
    recomputed={key:dict(n=len(rs),means={k:sum(r['outcomes'][k] for r in rs)/len(rs) for k in rs[0]['outcomes']}) for key,rs in panels.items()}
    assert recomputed==summary['panels']
    assert len(pairs)==summary['paired_primary_states']==108
    contrasts=[]
    for key,arms in sorted(pairs.items()):
        assert set(arms)=={'A0','A1','A2','A3','A4'}
        assert len({r['pre_snapshot_hash'] for r in arms.values()})==1
        assert arms['A2']['outcomes']['Y_H']==0
        value=lambda a:arms[a]['outcomes']['Y_star']
        contrasts.append(dict(state=[*key[:3],list(key[3])],repair=value('A1')-value('A2'),production=value('A2')-value('A3'),versus_intact=value('A1')-value('A0')))
    assert contrasts==summary['contrasts']
    assert sum(x['repair'] for x in contrasts)==16
    assert summary['mean_repair']==16/108
    assert dict(collections.Counter(r['first_failed_stage'] or 'none' for r in rows))==summary['failures']
    assert set(tables)=={'initial','interventions','channel','transfer','continuation','balance'}
    assert all(len(v)==592 and {x['id'] for x in v}=={c['id'] for c in cases} for v in tables.values())
    forecast=process['forecast']; body=process['process_body_wall_seconds']; worker=job['finished']-job['started']
    assert digest(env)==process['environment_digest']==forecast['environment_digest']
    assert forecast['source_commit']==process['source_commit'] and forecast['script_sha256']==source['script_sha256']
    assert forecast['lower_seconds']<=body<=forecast['upper_seconds']
    startup_allowance=forecast['expected_seconds']-forecast['expected_body_seconds']
    assert worker<=forecast['upper_seconds']+startup_allowance and worker<forecast['hard_wall_seconds']
    assert job['state']=='completed' and job['exit_code']==0 and process['runtime_gate']=='PASS'
    result=dict(status='PASS',kind='offline_saved_output_verification_no_simulation',tasks=592,paired_primary_states=108,primary_A1_success=16,primary_A2_success=0,
                mean_repair=16/108,balances_all_events=True,panels_match=True,contrasts_match=True,six_tables_complete=True,
                source_consistent=True,archive_sha256=process['archive_sha256'],body_seconds=body,worker_seconds=worker,
                worker_startup_allowance_seconds=startup_allowance,runtime_gate='PASS',new_vm_jobs=0,scientific_confirmation=False)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text)

if __name__=='__main__':main()
