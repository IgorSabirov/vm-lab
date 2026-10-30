"""Two-turn opt-in CLI persistence probe; not a background worker."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT.parents[1]/'infra'/'copilot_bridge.py'

def save(path, data):
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--round',type=int,choices=[1,2],required=True)
    p.add_argument('--bridge',type=Path,default=BRIDGE)
    args=p.parse_args()
    spec=importlib.util.spec_from_file_location('bridge',args.bridge)
    bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    config_path=ROOT/'probe_config.json'
    if args.round==1:
        if config_path.exists():raise RuntimeError('Probe already exists; inspect it rather than duplicating')
        config=dict(session_id=str(uuid.uuid4()),marker='BRIDGE_MEMORY_'+uuid.uuid4().hex[:12])
        save(config_path,config)
    else:
        config=json.loads(config_path.read_text())
        prior=json.loads((ROOT/'round_1'/'status.json').read_text())
        if prior.get('returncode')!=0:raise RuntimeError('Round 1 did not finish successfully')
    cwd=ROOT/'session_workdir';cwd.mkdir(exist_ok=True)
    outdir=ROOT/f'round_{args.round}';outdir.mkdir(exist_ok=False)
    prompt=(f"Connection continuity test, no tools. Remember this exact code for our next turn: {config['marker']}. Reply only SAVED."
        if args.round==1 else 'Continue our preceding conversation. What exact code did I ask you to remember? Return only that code. Do not use tools.')
    (outdir/'prompt.txt').write_text(prompt)
    cli=bridge.cli_path();version=bridge.checked_version(cli)
    command=bridge.prompt_command(cli,cwd,prompt)
    extra=['--session-id',config['session_id'],'--output-format','json','--stream','on',
           '--share',str(outdir/'transcript.md'),'--usage-output-file',str(outdir/'usage.json'),'--sync-session=off']
    command=command[:-2]+extra+command[-2:]
    meta=dict(round=args.round,session_id=config['session_id'],cli_version=version,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),state='PREPARED',
        created_utc=datetime.now(timezone.utc).isoformat())
    save(outdir/'request.json',meta)
    started=time.monotonic()
    with (outdir/'events.jsonl').open('w') as out, (outdir/'stderr.txt').open('w') as err:
        process=subprocess.Popen(command,env=bridge.child_env(),stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,text=True,start_new_session=True)
        save(outdir/'status.json',dict(meta,state='RUNNING',pid=process.pid))
        result=process.wait()
    meta.update(state='FINISHED' if result==0 else 'FAILED',returncode=result,
                elapsed_seconds=round(time.monotonic()-started,3),
                transcript_exists=(outdir/'transcript.md').is_file(),usage_exists=(outdir/'usage.json').is_file())
    save(outdir/'status.json',meta)
    print(json.dumps(meta,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result==0 else 1)

if __name__=='__main__':main()
