"""Build one canonical summary from pinned, already published reports only."""
import hashlib
import json
import re
from pathlib import Path
from e002e_exp.runtime import ROOT
from .plan import cases, protocol_hash, implementation_hash


def build(destination, source_manifest=None):
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    source_manifest = Path(source_manifest or ROOT/'experiments/e002e_corr/input_integrity.json')
    pins = json.loads(source_manifest.read_text())
    if not re.fullmatch('[0-9a-f]{40}', pins['repository_ref']):
        raise ValueError('Invalid explicit source commit')
    indexed = {p['path']:p for p in pins['checks']}
    if len(indexed) != len(pins['checks']):
        raise ValueError('Duplicate source pin')
    def pinned_bytes(path):
        rel = path.relative_to(ROOT).as_posix(); raw = path.read_bytes(); pin = indexed[rel]
        blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if hashlib.sha256(raw).hexdigest() != pin['sha256'] or blob != pin['expected_github_blob']:
            raise ValueError('Published input differs from explicit commit pin: '+rel)
        return raw
    baselines = []; canonical = []
    for c in cases():
        p = ROOT/'results/E002e_BASELINE_v001_r001/files'/(c['id']+'.json')
        raw = pinned_bytes(p); record = json.loads(raw)
        if record['id'] != c['id'] or not record['quality']['pass'] or not record['refinement']['gate']['pass_gate']:
            raise ValueError('Unverified baseline')
        baselines.append(dict(case_id=c['id'], path=p.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(raw).hexdigest(),
                              repository_commit=pins['repository_ref']))
        canonical.append(dict(case=c, raw={n:record['raw'][n] for n in ('F','J_h','h6','P_m6_N2','inventory')},
                              j6=record['conditional']['j6']))
    sources = {}; summary = {}
    for tag, rel in (('R_F3_T', 'analysis/E002e_F2_v001/training_analysis.json'),
                     ('F2', 'analysis/E002e_F2_v001/heldout_analysis.json'),
                     ('shape', 'analysis/E002e_NEIGHBOR_REVIEW_20261101/numbers.json')):
        data = pinned_bytes(ROOT/rel); obj = json.loads(data)
        sources[tag] = dict(path=rel, sha256=hashlib.sha256(data).hexdigest(),
                            repository_commit=pins['repository_ref'])
        summary[tag] = ({k:obj[k] for k in ('static','frequency','qrt')} if tag == 'R_F3_T' else
                        {k:obj[k] for k in ('families','lines','width_status','background_status')} if tag == 'F2' else
                        {k:obj[k] for k in ('fits','width_transfer','exact_ratio_decomposition')})
    evidence = dict(schema='E002e_CORR_evidence_v1', protocol_sha256=protocol_hash(), baselines=baselines, sources=sources,
                    missing_unverified_neighbor_sources=['RESULT 2', 'candidate_A_report'])
    dump = lambda p,v: p.write_text(json.dumps(v, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n')
    dump(destination/'evidence.json', evidence)
    dump(destination/'canonical_numbers.json', dict(baselines=canonical, sources=sources, published_only=summary, new_NESS=0))
    evidence_path = destination/'evidence.json'
    base = dict(mode='production', source_commit=None, protocol_sha256=protocol_hash(),
                implementation_sha256=implementation_hash(), technical_review=None, calibration=None,
                evidence=dict(path=evidence_path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest()),
                forecast=None, memory_budget=None)
    dump(destination/'production.template.json', base)
    dump(destination/'calibration.template.json', dict(base, mode='calibration'))
    return dict(baselines=len(baselines), sources=len(sources), new_NESS=0)
