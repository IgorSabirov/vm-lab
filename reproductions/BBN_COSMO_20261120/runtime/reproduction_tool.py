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
def status(wait=False):
    request = OUT/"COPILOT_EXECUTE_REQUEST.json"
    receipt = OUT/"EXECUTION_RECEIPT.json"
    for _ in range(5 if wait else 1):
        if receipt.exists():
            value = json.loads(receipt.read_text())
            return {"status":value["status"],"completed_pairs":value.get("completed_pairs")}
        if not request.exists():
            return {"status":"NOT_STARTED"}
        if (OUT/"COPILOT_TOOL_START.json").exists():
            return {"status":"RUNNING"}
        if wait:
            time.sleep(.2)
    return {"status":"REQUESTED"}

def execute():
    request = OUT/"COPILOT_EXECUTE_REQUEST.json"
    try:
        with request.open("x") as f:
            json.dump({"tool":"bbn.execute","args":[]},f)
    except FileExistsError:
        return {"duplicate_refused":True, **status()}
    return status(wait=True)

def answer(request):
    method = request.get('method')
    if method == 'initialize':
        return {'protocolVersion': request['params']['protocolVersion'], 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'bbn-fixed-reproduction', 'version': '1.0'}}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': [
            {'name': 'execute', 'description': 'Start the one owner-authorized complete BBN + CLASS integrations. No arguments. Never launches twice.',
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
