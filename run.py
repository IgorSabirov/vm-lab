"""Lossless transport of GitHub-published files only; no VM archive access."""
import base64
import hashlib
import json
import os
from pathlib import Path
import resource
import time


def main():
    start=time.perf_counter()
    root=Path(__file__).resolve().parent
    if root!=Path(os.environ['VM_SOURCE_DIR']).resolve():
        raise ValueError('Source directory mismatch')
    cfg=json.loads((root/'config.json').read_text())
    resource.setrlimit(resource.RLIMIT_AS,(256*2**20,256*2**20))
    report=Path('report');report.mkdir(exist_ok=False)
    output=[]
    for spec in cfg['files']:
        if spec['input']!='inputs/'+spec['name'] or Path(spec['name']).name!=spec['name']:
            raise ValueError('Invalid explicit input path')
        data=(root/spec['input']).read_bytes()
        git_blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if len(data)!=spec['size'] or hashlib.sha256(data).hexdigest()!=spec['sha256'] or git_blob!=spec['git_blob']:
            raise ValueError('Published source identity mismatch')
        parts=[]
        for i,begin in enumerate(range(0,len(data),512*1024)):
            raw=data[begin:begin+512*1024];name=spec['name']+'.part'+str(i).zfill(3)+'.b64'
            encoded=base64.b64encode(raw)
            (report/name).write_bytes(encoded)
            if base64.b64decode((report/name).read_bytes(),validate=True)!=raw:
                raise ValueError('Lossless transport verification failed')
            parts.append(dict(name=name,offset=begin,raw_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        output.append(dict(spec,parts=parts))
    mapping=dict(source_report_commit=cfg['source_report_commit'],original_run=cfg['original_run'],
                 original_source_commit=cfg['original_source_commit'],files=output,
                 input_origin='GITHUB_BLOBS_IN_PINNED_LAUNCH_TREE',archive_accessed=False,scientific_solves=0)
    (report/'transport.json').write_text(json.dumps(mapping,indent=2)+'\n')
    (report/'data_manifest.json').write_text(json.dumps(mapping,indent=2)+'\n')
    elapsed=time.perf_counter()-start
    metrics=dict(status='LOSSLESS_EXPORT_COMPLETE',source_commit=os.environ['VM_SOURCE_COMMIT'],
                 input_files=len(output),input_bytes=sum(s['size'] for s in output),parts=sum(len(s['parts']) for s in output),
                 internal_seconds=elapsed,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 forecast=cfg['forecast'],full_process_time='CHECK_ENCLOSING_RUN_JSON',science='NO_NEW_SCIENTIFIC_WORK')
    (report/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    text='Время: прогноз '+str(cfg['forecast']['expected_seconds'])+' с; внутренний факт '+str(elapsed)+' с. Полное время см. run.json.\n\nТранспорт опубликованных GitHub-данных без изменения байтов. Никаких новых решений или доступа к неопубликованному архиву. Исходный отчёт '+cfg['source_report_commit']+'.\n'
    (report/'README.md').write_text(text);(report/'RESULT.md').write_text(text)


if __name__=='__main__':main()
