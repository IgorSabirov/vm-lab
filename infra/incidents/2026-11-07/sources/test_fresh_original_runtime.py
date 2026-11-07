from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

payload=json.loads(Path('fresh_original_payload.json').read_text())
with tempfile.TemporaryDirectory(prefix='fresh-vm-test-') as directory:
    root=Path(directory)
    work=root/'work'
    for part in ('code','data','jobs','results'):
        (work/part).mkdir(parents=True,exist_ok=True)
    config={'root':str(work),'work':str(work),'token':'a'*64,'port':0,
            'bind':'127.0.0.1','ready_path':str(root/'ready.json'),'resources':{'threads':1}}
    (root/'config.json').write_text(json.dumps(config))
    (root/'server.py').write_text(payload['server_source'])
    (root/'worker.py').write_text(payload['worker_source'])
    processes=[]
    try:
        processes.append(subprocess.Popen([sys.executable,str(root/'worker.py'),str(work)]))
        processes.append(subprocess.Popen([sys.executable,str(root/'server.py'),str(root/'config.json')]))
        for attempt in range(100):
            if (root/'ready.json').exists():
                break
            time.sleep(.05)
        port=json.loads((root/'ready.json').read_text())['port']
        url=f'http://127.0.0.1:{port}/'+config['token']+'/mcp'
        def rpc(method,params=None):
            request=urllib.request.Request(url,json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=5) as response:
                body=json.load(response)
            assert 'error' not in body,body
            return body['result']
        def call(name,**args):
            result=rpc('tools/call',{'name':name,'arguments':args})
            assert not result.get('isError'),result
            return json.loads(result['content'][0]['text'])
        assert rpc('initialize')['serverInfo']['version']=='4.0.0'
        assert {'write_work_file','start_python_job','job_status'}<={x['name'] for x in rpc('tools/list')['tools']}
        wrote=call('write_work_file',path='code/check.py',text="from pathlib import Path\nPath('answer.txt').write_text(str(19*23))\n")
        job='fresh_test_000001'
        call('start_python_job',path=wrote['path'],sha256=wrote['sha256'],request_id=job)
        for attempt in range(100):
            result=call('job_status',job_id=job)
            if result['state'] not in ('queued','running'):
                break
            time.sleep(.1)
        assert result['state']=='completed',result
        assert call('read_work_file',path=result['results_path']+'/answer.txt')['text']=='437'
        print('PASS: original API + worker, MCP initialize/tools, file write, queued job, status and result read.')
    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
