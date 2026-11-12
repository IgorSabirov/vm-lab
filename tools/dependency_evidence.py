#!/usr/bin/env python3
"""CycloneDX inventory from pip inspect plus active manifest hashes.

Runtime requirements are evaluated for this environment, with no extras selected.
This is not an SBOM of archived experiments, system libraries or external C++.
"""
import argparse
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import quote
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def generate(inspect):
    installed = {canonicalize_name(x['metadata']['name']): x for x in inspect['installed']}
    refs = {name: 'pkg:pypi/' + quote(name) + '@' + quote(row['metadata']['version']) for name, row in installed.items()}
    components, dependencies, missing = [], [], []
    for name, row in sorted(installed.items()):
        m = row['metadata']; ref = refs[name]
        components.append({'type':'library','name':name,'version':m['version'],'purl':ref,'bom-ref':ref})
        dep = []
        for text in m.get('requires_dist', []):
            r = Requirement(text)
            env = {**inspect.get('environment', {}), 'extra': ''}
            if r.marker and not r.marker.evaluate(env):
                continue
            key = canonicalize_name(r.name)
            if key in refs:
                dep.append(refs[key])
            else:
                missing.append({'package':name,'requirement':text})
        dependencies.append({'ref':ref,'dependsOn':sorted(set(dep))})
    serial = uuid.uuid5(uuid.NAMESPACE_URL, json.dumps({'components':components,'dependencies':dependencies},sort_keys=True))
    return {'$schema':'https://cyclonedx.org/schema/bom-1.6.schema.json',
            'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'serialNumber':serial.urn,
            'metadata':{'properties':[{'name':'vm-lab:scope','value':'pip inspect environment; default extras only; excludes OS and external C++'}]},
            'components':components,'dependencies':dependencies}, missing


def main():
    p=argparse.ArgumentParser();p.add_argument('--pip-inspect',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    bom,missing=generate(json.loads(a.pip_inspect.read_text()))
    active=json.loads((ROOT/'infra/external/ACTIVE_DEPENDENCIES.json').read_text())
    hashes={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in active['manifests']}
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'sbom.cdx.json').write_text(json.dumps(bom,indent=2)+'\n')
    (a.output/'DEPENDENCY_MANIFEST.json').write_text(json.dumps({'manifests':hashes,'missing_runtime_requirements':missing,'sbom_scope':'resolved CI environment, not all scientific environments'},indent=2)+'\n')
    if missing:raise SystemExit('Unresolved installed runtime requirements; see manifest')


if __name__=='__main__':main()
