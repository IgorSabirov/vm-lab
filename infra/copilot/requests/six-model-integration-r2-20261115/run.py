#!/usr/bin/env python3
"""One explicitly authorized text-only request; reuse the established native bridge."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'infra'))
from copilot_probe import invoke_native


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify():
    request = json.loads((HERE / 'REQUEST.json').read_text())
    if request['id'] != HERE.name or request['model_calls'] != 1 or request['automatic_retry']:
        raise ValueError('Unexpected request identity or retry policy')
    raw = (HERE / 'CONTEXT.json').read_bytes()
    instruction = (HERE / 'PROMPT.md').read_bytes()
    if sha(raw) != request['context_sha256'] or sha(instruction) != request['instruction_sha256']:
        raise ValueError('Frozen input hash mismatch')
    prompt = instruction.decode() + '\n' + raw.decode()
    if len(prompt.encode()) > request['prompt_bytes_upper']:
        raise ValueError('No truncation: prompt exceeds declared limit')
    context = json.loads(raw)
    if context['baseline']['source_sha'] != request['baseline_sha']:
        raise ValueError('Baseline mismatch')
    for doc in context['updates'] + context['additional_baseline_documents']:
        if sha(doc['text'].encode()) != doc['sha256']:
            raise ValueError('Source content hash mismatch: ' + doc['path'])
    print(json.dumps({'status': 'INPUTS_VERIFIED', 'prompt_bytes': len(prompt.encode()),
                      'context_sha256': sha(raw), 'model_calls_in_preflight': 0}))
    return request, prompt


def generate():
    request, prompt = verify()
    if os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise SystemExit('Do not rerun: inspect/recover the saved artifact first')
    output = ROOT / 'integration-output'
    output.mkdir(exist_ok=True)
    if (output / 'STARTED.json').exists():
        raise SystemExit('Invocation already started; inspect saved state')
    common = {'task_id': request['id'], 'issue': 58, 'source_sha': os.environ['GITHUB_SHA'],
              'run_id': os.environ['GITHUB_RUN_ID'], 'baseline_sha': request['baseline_sha'],
              'request_sha256': sha((HERE / 'REQUEST.json').read_bytes()),
              'context_sha256': request['context_sha256'],
              'instruction_sha256': request['instruction_sha256'],
              'scientific_acceptance': False, 'scientific_status_changed': False,
              'links_accepted': False, 'automatic_retry': False}
    def save(name, data):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    save('STARTED.json', {**common, 'status': 'INVOCATION_STARTED'})
    try:
        receipt = invoke_native(prompt, timeout=request['inference_timeout_seconds'])
    except BaseException as error:
        save('FAILURE.json', {**common, 'status': 'INVOCATION_FAILED', 'error_type': type(error).__name__})
        raise
    raw_response = receipt.pop('stdout')
    (output / 'RAW_RESPONSE.txt').write_text(raw_response)
    receipt.update(common, response_sha256=sha(raw_response.encode()), repository_content_sent=True)
    if receipt['returncode'] or receipt['timed_out']:
        save('FAILURE.json', {**receipt, 'status': 'NATIVE_INFERENCE_FAILED'})
        raise SystemExit('Inference failed; full redacted response retained; no retry')
    try:
        if not 500 <= len(raw_response.encode()) <= 32000:
            raise ValueError('Report outside declared size bounds')
        if re.search(r'(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+', raw_response):
            raise ValueError('Credential-shaped response')
        for name in ('CCC', 'Anthropic', 'Serbian', 'IsingCauset', 'CDT', 'ADD'):
            if name.casefold() not in raw_response.casefold():
                raise ValueError('Missing required direction: ' + name)
    except ValueError as error:
        save('FAILURE.json', {**receipt, 'status': 'OUTPUT_VALIDATION_FAILED', 'error': str(error)})
        raise SystemExit('Saved response requires recovery, not another inference') from error
    report = ('# Copilot: шесть моделей и автоматизация исследований — R2\n\n'
              'Предложение модели; научная приёмка не предоставлена. '
              'Подготовка источников и публикация выполнены доверенными шагами.\n\n'
              f"Задача #58. Исходный commit: `{common['source_sha']}`. "
              f"[Запуск](https://github.com/IgorSabirov/vm-lab/actions/runs/{common['run_id']}).\n\n"
              + raw_response + '\n')
    receipt.update(status='NATIVE_REPORT_GENERATED', report_sha256=sha(report.encode()),
                   publication='PENDING', output_validation='STRUCTURE_ONLY_NOT_SCIENTIFIC_ACCEPTANCE')
    (output / 'REPORT.md').write_text(report)
    save('RECEIPT.json', receipt)
    save('native-proposal.json', {'source_sha': common['source_sha'], 'report': report, 'receipt': receipt})
    print(json.dumps({'status': receipt['status'], 'seconds': receipt['elapsed_seconds'],
                      'report_sha256': receipt['report_sha256']}))


if __name__ == '__main__':
    {'verify': verify, 'generate': generate}[sys.argv[1]]()
