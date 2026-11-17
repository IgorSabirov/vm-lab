"""Compare archived local evidence to the fixed GitHub execution, without rerunning science.

Usage: python verify_handoff.py LOCAL.zip GITHUB_ARTIFACT.zip --evidence-dir DIR --output DIR
Requires Pillow only for PNG pixel comparison; everything else uses the standard library.
GITHUB_TREES.json and GITHUB_EVIDENCE.json are GitHub API snapshots at the recorded SHAs.
"""
import argparse
import ast
import base64
import collections
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile
import zlib


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def decoded(name, data):
    return gzip.decompress(data) if name.endswith('.gz') else data


def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(a.keys() | b.keys()):
            p = path + '/' + key
            if key not in a or key not in b:
                out.append({'path': p, 'kind': 'added' if key in b else 'removed',
                            'old': a.get(key), 'new': b.get(key)})
            else:
                out.extend(differences(a[key], b[key], p))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = [] if len(a) == len(b) else [{'path': path, 'kind': 'length', 'old': len(a), 'new': len(b)}]
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(differences(x, y, path + '/' + str(i)))
        return out
    return [] if type(a) == type(b) and a == b else [{'path': path, 'kind': 'changed', 'old': a, 'new': b}]


def role(name):
    if '/' not in name:
        return 'archive_packaging_and_historical_publication_status'
    if '/ADD_C1_AUTHOR_REPRO_' in name:
        return 'earlier_operator_package'
    if name.startswith('local_execution/'):
        return 'local_execution_wrapper_or_embedded_bundle'
    if '/NOW_RESULTS_SYNTHESIS_' in name or '/REGISTRY_LINKS/' in name:
        return 'historical_registry_snapshot'
    if name.endswith('/SOURCES.json'):
        return 'bibliography'
    if name.endswith(('/RAW_DATA.tar.xz', '/RAW_MANIFEST.sha256')):
        return 'duplicate_raw_container_or_manifest'
    return 'historical_execution_receipt_log_or_manifest'


def classify_diff(name, d):
    parts = d['path'].strip('/').split('/')
    if name.endswith('/LONG_SUMMARY.json') and d['kind'] == 'added' and parts[-1] == 'inverse_tail_status':
        return 'derived_status_added'
    if d['path'] == '/prior_harness_failure':
        return 'execution_history'
    root = parts[0]
    meta = {'environment', 'python', 'runtime_plan_actual', 'elapsed_seconds', 'measured_at_utc',
            'peak_rss_kib', 'calibration_seconds', 'forecast_seconds', 'made_before_main_utc',
            'range_seconds', 'forecast_code_seconds', 'forecast_components_seconds',
            'this_execution_code_seconds', 'successful_phase_code_seconds', 'actual_over_forecast'}
    if root in meta or parts[-1] == 'seconds':
        return 'runtime_environment_or_forecast'
    return 'unexplained'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('archive', type=Path)
    ap.add_argument('github_artifact', type=Path)
    ap.add_argument('--evidence-dir', type=Path, default=Path(__file__).parent)
    ap.add_argument('--output', type=Path, default=Path(__file__).parent)
    args = ap.parse_args()
    t = json.loads((args.evidence_dir/'GITHUB_TREES.json').read_text())
    e = json.loads((args.evidence_dir/'GITHUB_EVIDENCE.json').read_text())
    old = zipfile.ZipFile(args.archive)
    new = zipfile.ZipFile(args.github_artifact)
    original = {p: old.read(p) for p in old.namelist() if not p.endswith('/')}
    output = {p: new.read(p) for p in new.namelist() if not p.endswith('/')}
    source = {x['path']: x for x in t['source']['tree'] if x['type'] == 'blob'}
    ref = {x['path']: x for x in t['reference']['tree'] if x['type'] == 'blob'}
    result = {'analysis/'+x['path']: x for x in t['results']['tree'] if x['type'] == 'blob'}
    result.update({x['name']: x for x in e['published_root'] if x['type'] == 'file'})
    assert all(not t[k]['truncated'] for k in t)
    for entries in e['payload_refs'].values():
        by_name = {x['name']: x['sha'] for x in entries}
        assert by_name['source'] == t['source']['sha']
        assert by_name['reference'] == t['reference']['sha']
    assert len(original) == len(set(old.namelist()))
    archive_manifest = []
    for line in original['ARCHIVE_MANIFEST.sha256'].decode().splitlines():
        digest, path = line.split(None, 1)
        path = path.lstrip('*')
        assert sha(original[path]) == digest, path
        archive_manifest.append(path)
    assert set(archive_manifest) == set(original)-{'ARCHIVE_MANIFEST.sha256'}
    github_files = []
    for path, data in output.items():
        assert path in result and blob(data) == result[path]['sha'], path
        github_files.append(path)
    assert set(result) - set(output) == {'COMPARISON_ASSESSMENT.json', 'REPORT_RU.md'}
    source_rows = []
    for p, v in source.items():
        path = 'analysis/'+p
        assert blob(original[path]) == v['sha'] == blob(output[path]), path
        source_rows.append({'path': path, 'sha256': sha(original[path]), 'git_blob': v['sha'], 'matches': True})
    ref_rows = []
    for p, v in ref.items():
        if p == 'RAW_DECODED_SHA256.json':
            assert blob(e['raw_reference_content'].encode()) == v['sha']
            continue
        assert blob(original['analysis/'+p]) == v['sha'], p
        ref_rows.append('analysis/'+p)
    raw_names = [p for p in original if p.endswith(('.csv.gz', '_words.json.gz', '_samples.json'))]
    raw_manifest = json.loads(e['raw_reference_content'])
    assert set(raw_manifest) == {Path(p).name for p in raw_names}
    raw_rows = []
    for p in sorted(raw_names):
        a, b = decoded(p, original[p]), decoded(p, output[p])
        assert sha(a) == raw_manifest[Path(p).name]['sha256_decoded'], p
        assert a == b, p
        raw_rows.append({'path': p, 'sha256_decoded': sha(a), 'old_sha256': sha(original[p]),
                         'new_sha256': sha(output[p]), 'encoded_equal': original[p] == output[p], 'decoded_equal': True})
    tar_rows = []
    with tarfile.open(fileobj=io.BytesIO(original['analysis/ADD_C1_SCIENCE_20261117/RAW_DATA.tar.xz']), mode='r:xz') as tar:
        for m in tar.getmembers():
            if m.isfile():
                p = 'analysis/ADD_C1_SCIENCE_20261117/'+m.name
                assert tar.extractfile(m).read() == original[p], p
                tar_rows.append(p)
    assert set(tar_rows) == set(raw_names)
    json_rows = []
    for p in sorted(set(original) & set(output)):
        if not p.endswith('.json'):
            continue
        for d in differences(json.loads(original[p]), json.loads(output[p])):
            d.update(file=p, category=classify_diff(p, d))
            if d['category'] == 'derived_status_added':
                row = json.loads(original[p])[int(d['path'].split('/')[1])]
                expected = None if row['direction'] == 'forward' else ('POSITIVE_INTEGER_TAIL' if row['integer_linear_tail512'] and 1 <= row['tail_slope'] <= min(row['na'], row['nb']) else 'TRANSIENT_OR_CONTROL')
                assert expected == d['new']
                d['independently_recomputed_from_old_fields'] = True
            json_rows.append(d)
    assert not [d for d in json_rows if d['category'] == 'unexplained']
    # Read bundles as data; do not import or execute archived scripts.
    bundle = json.loads(original['local_execution/chat_bundle_sources.json'])
    ast_tree = ast.parse(original['local_execution/CHAT_RUN_ADD_C1_BLOCK1.py'])
    payload = next(ast.literal_eval(n.value) for n in ast_tree.body if isinstance(n, ast.Assign) and any(isinstance(x, ast.Name) and x.id == 'PAYLOAD' for x in n.targets))
    embedded = json.loads(zlib.decompress(base64.b64decode(payload)))
    bundle_rows = []
    for p, item in bundle.items():
        data = item['content'].encode()
        assert blob(data) == item['git_blob_sha']
        assert data == original['analysis/ADD_C1_AUTHOR_REPRO_20261116/'+p]
        bundle_rows.append({'name': p, 'matches_earlier_author_package': True,
                            'matches_local_package': data == original['analysis/ADD_C1_LOCAL_REPRO_20261117/'+p]})
    author_diff = differences(json.loads(original['analysis/ADD_C1_AUTHOR_REPRO_20261116/RESULTS.json']),
                              json.loads(original['analysis/ADD_C1_LOCAL_REPRO_20261117/RESULTS.json']))
    assert all(classify_diff('RESULTS.json', d) == 'runtime_environment_or_forecast' for d in author_diff)
    from PIL import Image
    png = 'analysis/ADD_C1_SCIENCE_20261117/FIGURES.png'
    a = Image.open(io.BytesIO(original[png])).convert('RGBA')
    b = Image.open(io.BytesIO(output[png])).convert('RGBA')
    assert a.size == b.size and a.tobytes() == b.tobytes()
    # The SVG's geometry is compared after normalizing only generated identifiers and metadata.
    import xml.etree.ElementTree as ET
    def svg_normalized(data):
        root = ET.fromstring(data)
        ids = {n.attrib['id']: 'id'+str(i) for i,n in enumerate(n for n in root.iter() if 'id' in n.attrib)}
        def clean(n):
            attrs = dict(n.attrib)
            for k,v in attrs.items():
                if k == 'id': attrs[k] = ids[v]
                elif v.startswith('#') and v[1:] in ids: attrs[k] = '#'+ids[v[1:]]
                elif v.startswith('url(#') and v[5:-1] in ids: attrs[k] = 'url(#'+ids[v[5:-1]]+')'
            return [n.tag, sorted(attrs.items()), (n.text or '').strip(), [clean(c) for c in n if not c.tag.endswith('}metadata')]]
        return clean(root)
    svg = 'analysis/ADD_C1_SCIENCE_20261117/FIGURES.svg'
    svg_equal = svg_normalized(original[svg]) == svg_normalized(output[svg])
    # Account for every archive path, including material never sent in this handoff.
    inventory = []
    for p,data in sorted(original.items()):
        rel = p.removeprefix('analysis/')
        destinations = []
        if rel in source: destinations.append('source/'+rel)
        if p in ref_rows: destinations.append('reference/'+rel)
        if p in output: destinations.append('results/44082471150/'+p)
        equivalent = [q for q,v in source.items() if blob(data) == v['sha'] and q != rel]
        if p in output:
            status = 'input_copied' if rel in source else 'output_regenerated'
        elif p in ref_rows:
            status = 'reference_document_copied'
        else:
            status = 'not_in_handoff'
        inventory.append({'archive_path':p,'bytes':len(data),'archive_sha256':sha(data),
                          'status':status,'destinations':destinations,'equivalent_source_paths':equivalent,
                          'omission_class':role(p) if status == 'not_in_handoff' else None,
                          'new_bytes_equal':data == output[p] if p in output else None})
    long_csv = [p for p in raw_names if p.endswith('.csv.gz') and not p.endswith('/EXHAUSTIVE.csv.gz')]
    transitions = {p:sum(1 for _ in csv.DictReader(io.StringIO(decoded(p,output[p]).decode())))-1 for p in long_csv}
    exhaustive_rows = list(csv.DictReader(io.StringIO(gzip.decompress(output['analysis/ADD_C1_SCIENCE_20261117/EXHAUSTIVE.csv.gz']).decode())))
    summary = {
        'status':'ARCHIVE_HANDOFF_AND_EXECUTION_AUDITED',
        'archive_sha256':sha(args.archive.read_bytes()), 'artifact_sha256':sha(args.github_artifact.read_bytes()),
        'source_payload_commit':'9e53090e6f288d16adc692e57a22ab7326459bf9',
        'executed_commit':'2c6f647ee4c9b87bc2918c6bf9a87e18b67a16a7',
        'compared_result_commit':'d2d0252f4237087552e61cb69894ad3fd6dec0aa',
        'run_id':44082471150, 'artifact_id':14328360959,
        'archive_files':len(original),'archive_manifest_verified':len(archive_manifest),
        'artifact_files_verified_against_committed_git_blobs':len(github_files),
        'executed_analysis_files':len([p for p in output if p.startswith('analysis/')]),
        'unchanged_input_files':len(source_rows),'copied_reference_files':len(ref_rows),
        'archive_coverage':dict(collections.Counter(r['status'] for r in inventory)),
        'omissions_by_class':dict(collections.Counter(r['omission_class'] for r in inventory if r['status']=='not_in_handoff')),
        'raw_decoded_equal':len(raw_rows),'raw_encoded_equal':sum(r['encoded_equal'] for r in raw_rows),
        'duplicate_tar_members_verified':len(tar_rows),
        'json_compared_files':len([p for p in set(original)&set(output) if p.endswith('.json')]),
        'json_difference_counts':dict(collections.Counter(r['category'] for r in json_rows)),
        'json_exact_comparison_no_tolerance':True,
        'png_pixels_equal':True,'png_size':a.size,'svg_equal_after_id_and_metadata_normalization':svg_equal,
        'long_trajectory_csv_files':len(long_csv),'long_transition_counts':dict(collections.Counter(transitions.values())),
        'long_transitions_including_extensions':sum(transitions.values()),'exhaustive_csv_rows':len(exhaustive_rows),
        'bundle_rows':bundle_rows, 'embedded_payload_matches_json_bundle':embedded==bundle,
        'earlier_author_results_differences':author_diff,
        'receipt':json.loads(output['EXECUTION_RECEIPT.json']),
        'limits':['Compares the supplied final local archive; does not recover unrecorded original process state.',
                  'No new scientific execution or independent model implementation was performed.',
                  'Files absent from this handoff may exist elsewhere in repository history; this audit makes no repository-wide absence claim.']}
    assert svg_equal and embedded == bundle
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in [('AUDIT.json',summary),('JSON_DIFFERENCES.json',json_rows),('FILE_MAP.json',inventory),('RAW_COMPARISON.json',raw_rows),('SOURCE_COMPARISON.json',source_rows)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    with (args.output/'FILE_MAP.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=inventory[0].keys());w.writeheader()
        w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in r.items()} for r in inventory)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('receipt','bundle_rows')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
