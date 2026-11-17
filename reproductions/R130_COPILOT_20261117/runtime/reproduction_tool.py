"""A two-operation MCP server: run exactly the frozen reproduction, or read its status.

No shell, command/path arguments, file browsing or network access are exposed.
Credentials are removed before any tool is serviced or child process is started.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

for key in list(os.environ):
    if 'TOKEN' in key or 'SECRET' in key or key.startswith(('COPILOT_', 'GH_AW_')):
        del os.environ[key]
ROOT = Path(__file__).resolve().parent
OUT = ROOT/'results'
OUT.mkdir(exist_ok=True)
process = None
streams = []

def status(wait=False):
    if process is None:
        return {'status': 'NOT_STARTED'}
    if wait and process.poll() is None:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
    receipt = OUT/'EXECUTION_RECEIPT.json'
    value = json.loads(receipt.read_text()) if receipt.exists() else {}
    return {'status': value.get('status', 'RUNNING'), 'exit_code': process.poll(),
            'completed_commands': len(value.get('commands', [])),
            'code_wall_seconds': value.get('code_wall_seconds'), 'error': value.get('error')}

def execute():
    global process
    if process is not None or (OUT/'STARTED.json').exists():
        return {'duplicate_refused': True, **status()}
    stdout = (OUT/'RUNNER.stdout.log').open('w')
    stderr = (OUT/'RUNNER.stderr.log').open('w')
    streams.extend([stdout, stderr])
    process = subprocess.Popen([sys.executable, str(ROOT/'run_reproduction.py')], cwd=ROOT,
                               env=dict(os.environ), stdout=stdout, stderr=stderr, start_new_session=True)
    (OUT/'COPILOT_TOOL_START.json').write_text(json.dumps({'tool': 'r130.execute', 'pid': process.pid,
        'command': [sys.executable, 'run_reproduction.py'], 'credentials_removed': True,
        'arbitrary_arguments_supported': False})+'\n')
    return status(wait=True)

def answer(request):
    method = request.get('method')
    if method == 'initialize':
        return {'protocolVersion': request['params']['protocolVersion'], 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'r130-fixed-reproduction', 'version': '1.0'}}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': [
            {'name': 'execute', 'description': 'Start the one owner-authorized complete R130 reproduction. No arguments. Never launches twice.',
             'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
            {'name': 'status', 'description': 'Wait up to 15 seconds and report the same reproduction process. No arguments.',
             'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}]}
    if method == 'tools/call':
        params = request.get('params', {})
        if params.get('arguments', {}) or params.get('name') not in {'execute', 'status'}:
            return {'isError': True, 'content': [{'type': 'text', 'text': 'Unsupported operation or arguments; nothing executed.'}]}
        name = params['name']
        value = execute() if name == 'execute' else status(wait=True)
        with (OUT/'COPILOT_TOOL_CALLS.jsonl').open('a') as log:
            log.write(json.dumps({'tool': name, 'result': value})+'\n')
        return {'content': [{'type': 'text', 'text': json.dumps(value)}]}
    raise ValueError('Unsupported protocol method')

for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    try:
        response = {'jsonrpc': '2.0', 'id': request['id'], 'result': answer(request)}
    except Exception as error:
        response = {'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32603, 'message': str(error)}}
    print(json.dumps(response), flush=True)
