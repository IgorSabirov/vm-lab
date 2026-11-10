#!/usr/bin/env python3
"""VM host runner: pinned GitHub code -> sequential validation -> GitHub results."""
import argparse, datetime, fcntl, hashlib, json, os, pathlib, platform, pwd
import shutil, subprocess, sys, time, uuid
P = pathlib.Path
PACKAGES = [('v043', 'x27', 'experiments/X27_PACKAGES_20261110/v043'),
            ('v051', 'x27v051', 'experiments/X27_PACKAGES_20261110/v051')]

def report_ok(version, report):
    if version == 'v051':
        return report.get('software_smoke_pass') is True
    return (report['E2']['all_pass'] is True and
            report['PC_NC']['summary']['all_pass'] is True and
            all(report['G0'][k]['status'] == 'PASS' for k in ('X27-A', 'X27-B-LITE')))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', required=True, help='Immutable 40-hex Git commit')
    ap.add_argument('--timeout', type=int, default=7200, help='Per command watchdog, not a scientific timing forecast')
    args = ap.parse_args()
    if len(args.source) != 40 or any(c not in '0123456789abcdef' for c in args.source):
        raise ValueError('Expected full source commit')
    if os.geteuid() != 0:
        raise RuntimeError('Run on VM host with sudo; computations drop privileges')
    base = P('/var/lib/vm-lab-x27'); base.mkdir(mode=0o755, exist_ok=True)
    lock = open(base/'runner.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cfg = json.loads(P('/etc/vm-lab-sync/config.json').read_text())
    if cfg.get('repository') != 'IgorSabirov/vm-lab' or cfg.get('remote') not in (
        'ssh://git@ssh.github.com:443/IgorSabirov/vm-lab.git', 'git@github.com:IgorSabirov/vm-lab.git'):
        raise ValueError('Unexpected repository configuration')
    env = {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'GIT_CONFIG_NOSYSTEM':'1',
           'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_TERMINAL_PROMPT':'0',
           'GIT_SSH_COMMAND':cfg['ssh_command'], 'GIT_AUTHOR_NAME':'VM Compute',
           'GIT_AUTHOR_EMAIL':'vm-compute@users.noreply.github.com',
           'GIT_COMMITTER_NAME':'VM Compute', 'GIT_COMMITTER_EMAIL':'vm-compute@users.noreply.github.com'}
    runid = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    run = base/runid; run.mkdir(mode=0o755)
    repo = run/'repo'; repo.mkdir(mode=0o700)
    def git(*cmd, check=True):
        r = subprocess.run(['/usr/bin/git','-c','core.hooksPath=/dev/null','-c','gc.auto=0',*cmd],
                           cwd=repo, env=env, capture_output=True, timeout=600)
        if check and r.returncode:
            raise RuntimeError('git '+cmd[0]+' failed, code '+str(r.returncode))
        return r if not check else r.stdout.decode().strip()
    git('init'); git('remote','add','origin',cfg['remote'])
    git('config','remote.origin.promisor','true')
    git('config','remote.origin.partialclonefilter','blob:none')
    git('fetch','--depth=1','--filter=blob:none','origin',args.source)
    if git('rev-parse','FETCH_HEAD') != args.source: raise RuntimeError('Source mismatch')
    git('sparse-checkout','init','--cone')
    git('sparse-checkout','set','experiments/X27_PACKAGES_20261110')
    git('checkout','--detach',args.source)
    manifest = json.loads((repo/'experiments/X27_PACKAGES_20261110/IMPORT.json').read_text())
    for rel, expected in manifest['files'].items():
        if hashlib.sha256((repo/rel).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source hash mismatch: '+rel)
    dest = 'results/X27_PAIR/'+runid
    output = repo/dest; output.mkdir(parents=True)
    account = pwd.getpwnam('nobody')
    receipt = {'source_commit':args.source,'run_id':runid,'status':'RUNNING',
               'scope':'SOFTWARE_VALIDATION_ONLY_NOT_FROZEN_MAIN_RUN_NOT_EXECUTED',
               'python':sys.version,'platform':platform.platform(),'commands':[],
               'watchdog_seconds':args.timeout,'scientific_runtime_gate':'NOT_EVALUATED',
               'second_package':'NOT_STARTED'}
    def save():
        (output/'PROCESS.json').write_text(json.dumps(receipt,indent=2)+'\n')
    def publish():
        save()
        sums = {str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'FILE_HASHES.json'}
        (output/'FILE_HASHES.json').write_text(json.dumps(sums,indent=2)+'\n')
        for attempt in range(3):
            git('fetch','--depth=1','--filter=blob:none','origin','main')
            parent = git('rev-parse','FETCH_HEAD')
            git('read-tree',parent)
            git('add','--sparse','-f','--',dest)
            tree = git('write-tree')
            commit = git('commit-tree',tree,'-p',parent,'-m','X27 sequential VM validation '+runid+' '+receipt['status'])
            pushed = git('push','origin',commit+':refs/heads/main',check=False)
            if pushed.returncode == 0:
                git('fetch','--depth=1','origin','main')
                expected = git('rev-parse',commit+':'+dest)
                if git('rev-parse','FETCH_HEAD:'+dest) != expected:
                    raise RuntimeError('Remote result tree mismatch')
                (run/'PUBLISHED.json').write_text(json.dumps({'commit':commit,'path':dest}))
                print('PUBLISHED',commit,dest,flush=True); return
        raise RuntimeError('Publication failed after 3 attempts; outputs preserved at '+str(output))
    def command(argv, cwd, outdir, label):
        log = outdir/(label+'.log')
        taskenv = {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONPATH':str(cwd/'src'),
                   'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','HOME':str(outdir)}
        started=time.monotonic()
        row={'package':cwd.name,'command':argv,'log':str(log.relative_to(run))}
        try:
            with log.open('w') as f:
                r=subprocess.run(argv,cwd=cwd,env=taskenv,stdout=f,stderr=subprocess.STDOUT,
                                 timeout=args.timeout,user=account.pw_uid,group=account.pw_gid,extra_groups=[])
            row['exit_code']=r.returncode
        except subprocess.TimeoutExpired:
            row['exit_code']=124; row['timeout']=True
        row['elapsed_seconds']=time.monotonic()-started
        receipt['commands'].append(row)
        if row['exit_code'] != 0: raise RuntimeError('Command failed: '+label)
    try:
        for version, module, path in PACKAGES:
            if version=='v051': receipt['second_package']='RUNNING'
            src=run/version; shutil.copytree(repo/path,src)
            work=run/(version+'_output');work.mkdir(mode=0o755)
            os.chown(work,account.pw_uid,account.pw_gid)
            try:
                command(['/usr/bin/python3','-m','unittest','discover','-s','tests','-v'],src,work,'unit_tests')
                target=work/'smoke_report.json' if version=='v043' else work/'validation'
                command(['/usr/bin/python3','-m',module+'.cli','smoke','--output',str(target)],src,work,'diagnostics')
                report_path=target if version=='v043' else target/'SMOKE_REPORT.json'
                if not report_ok(version,json.loads(report_path.read_text())):
                    raise RuntimeError('Software report gate failed: '+version)
            finally:
                shutil.copytree(work,output/version,dirs_exist_ok=True)
            receipt[version]='SOFTWARE_CHECKS_PASS'
            if version=='v051': receipt['second_package']='COMPLETE'
            receipt['status']='FIRST_COMPLETE' if version=='v043' else 'COMPLETE'
            publish()
    except Exception as e:
        receipt['status']='STOP';receipt['error']=str(e)
        save()
        try: publish()
        except Exception as pe: print(str(pe),flush=True)
        raise
    print('COMPLETE: both packages; scientific main-run status unchanged.',flush=True)
if __name__=='__main__': main()
