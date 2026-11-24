#!/usr/bin/env python3
"""Narrow P0 role/mode checks on pinned existing code; no physical stage runs.

The fixture retains the published model/point rows and XB source/coordinate
bytes, but uses a synthetic observational release and decision-rule table.
Source inventory and Git checkout checks are isolated after SHA-256 verification
of the tested modules. This is not an end-to-end P0/physical replay.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import urllib.request
from unittest.mock import patch

SOURCE_SHA = 'c3bc771d1daa292d5d9fd3e1d17bf4d3d6d01c92'
PREFIX = 'analysis/R135_PHYSICAL_SECTOR_X_20261120/full_run/'
CHECKSUMS = {
    'PLAN.json': '5fffbb0bfee2c894081cf339310272215d6dbee013f1d6c630dfec04a1c26477',
    'software/p0_register.py': '2bfe4c6e26be1026ed6d0b81c2bf0280a8a7523d40ee71236d7471613796a015',
    'software/p0_snapshot/model_register.json': '5891651c5a3bbe53fb8c8baa88d3082f1cf254782c770a84000e3f573fad548d',
    'software/r135/common.py': '6d275d0fc494135051e0872c5d793edb438f6e43599f99c7b1ad72c5ba425fe5',
    'software/r135/contracts.py': '4fde815028333b4a39e1c423948c135cac44a01805951203e7d1d304eca766ad',
    'software/xb_reference/coordinates.json': 'c9bebefd93c153331e826b1ab3b073fc5f35a75a09bc7d424bc94ffab01ce956',
    'software/xb_reference/inputs.json': 'fc1f28db062687a10cdf236b6ed6513cc411f3a2355d233fda7c1b5f49a7008d',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def get_sources(cache, offline):
    result = []
    for name, expected in CHECKSUMS.items():
        path = cache / name
        url = f'https://raw.githubusercontent.com/IgorSabirov/vm-lab/{SOURCE_SHA}/{PREFIX}{name}'
        if not path.exists():
            if offline:
                raise FileNotFoundError(path)
            data = urllib.request.urlopen(url, timeout=30).read()
            if digest(data) != expected:
                raise ValueError('Source checksum mismatch: '+name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if digest(path.read_bytes()) != expected:
            raise ValueError('Source checksum mismatch: '+name)
        result.append({'path': PREFIX+name, 'url':url, 'sha256':expected})
    return result


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def run(cache, offline):
    sources = get_sources(cache, offline)
    p0 = module('xb_neighbor_p0', cache/'software/p0_register.py')
    package = types.ModuleType('xb_neighbor_runtime')
    package.__path__ = [str(cache/'software/r135')]
    sys.modules[package.__name__] = package
    common = module(package.__name__+'.common', cache/'software/r135/common.py')
    contracts = module(package.__name__+'.contracts', cache/'software/r135/contracts.py')
    frozen = json.loads((cache/'software/p0_snapshot/model_register.json').read_bytes())
    plan = json.loads((cache/'PLAN.json').read_bytes())
    cases = []

    def expect(name, action, error=None):
        try:
            result = action()
        except (ValueError, common.InputError, common.OpenInput) as exc:
            if error is None or str(exc) != error:
                raise
            cases.append({'case':name, 'result':'PASS', 'observed':'rejected',
                          'exception':type(exc).__name__, 'message':str(exc)})
            return None
        if error is not None:
            raise AssertionError('Expected rejection: '+name)
        cases.append({'case':name, 'result':'PASS', 'observed':'accepted'})
        return result

    with tempfile.TemporaryDirectory(prefix='xb-p0-contract-') as folder:
        root = Path(folder)
        for name in ('inputs.json','coordinates.json'):
            target = root/'xb_reference'/name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(cache/'software/xb_reference'/name, target)
        registry = {
            'models':frozen['models'], 'points':frozen['points'],
            'xb_reference':frozen['xb_reference'],
            'rules':[{'claim':claim, 'models':[m['model_id'] for m in frozen['models']],
                      'required_data_ids':['FIXTURE']} for claim in plan['claims']],
            'data_releases':[{'data_id':'FIXTURE', 'source':'synthetic contract fixture',
                             'version':'1', 'state':'published_statistic', 'value':1,
                             'sigma':0.1, 'observable':'fixture', 'units':'1'}],
        }
        source = root/'register_inputs.json'
        source.write_bytes(p0.encoded(registry))
        built = expect('published_point_rows_pass_P0_build_with_fixture_observations', lambda:p0.build(source))
        snapshot = root/'p0_snapshot'
        p0.freeze(snapshot, built)
        inventory_files = [{'path':s['path'],'sha256':s['sha256']} for s in sources]
        inventory = {'sha256':common.canonical_hash(inventory_files), 'files':inventory_files}

        def request(mode, point_id, registry_path=source):
            point = next(p for p in frozen['points'] if p['point_id']==point_id)
            config = {'offline':True}
            return {'schema':'r135-stage-request-v1', 'stage':'P0',
                    'key':{'claim_id':'XB_SU3_cosmology', 'model_id':point['model_id'],
                           'point_id':point_id, 'thermal_path':point['thermal_path']},
                    'execution_sha':SOURCE_SHA, 'mode':mode, 'config':config,
                    'config_sha256':common.canonical_hash(config),
                    'source_sha256':inventory['sha256'],
                    'applicability':{'description':'P0 role/mode contract fixture only'},
                    'inputs':[{'name':name, 'path':str(path), 'sha256':digest(path.read_bytes())}
                              for name,path in [('model_register',snapshot/'model_register.json'),
                                                ('registry',registry_path)]]}

        # The actual role guards and actual P0 build/verified_registry are used.
        # Only full-checkout inventory/Git mechanics are replaced by the pinned
        # source verification above; no numerical/physical result is mocked.
        with patch.object(contracts,'_commit',return_value=SOURCE_SHA), \
             patch.object(contracts,'source_inventory',return_value=inventory), \
             patch.object(contracts,'source_matches_commit',return_value=True):
            expect('diagnostic_validation_request',
                   lambda:contracts.validate_request(request('validation','XB-T0-0-0'),'P0',root))
            expect('diagnostic_conditional_request',
                   lambda:contracts.validate_request(request('conditional','XB-T0-0-0'),'P0',root),
                   'diagnostic P0 points require validation mode')
            expect('published_FMS_conditional_request',
                   lambda:contracts.validate_request(request('conditional','XB-FMS-top-left'),'P0',root))
            expect('published_FMS_physical_request',
                   lambda:contracts.validate_request(request('physical','XB-FMS-top-left'),'P0',root),
                   'physical mode requires an independently calibrated P0 physical_candidate')

            unknown_role = copy.deepcopy(registry)
            next(p for p in unknown_role['points'] if p['point_id']=='XB-T0-0-0')['role']='conditional_scan'
            bad_source = root/'unknown_role.json'
            bad_source.write_bytes(p0.encoded(unknown_role))
            expect('new_conditional_scan_role',lambda:p0.build(bad_source),'Unknown point role')

            changed_benchmark = copy.deepcopy(registry)
            next(p for p in changed_benchmark['points'] if p['point_id']=='XB-FMS-top-left')['m0_GeV']=2
            changed_source = root/'changed_benchmark.json'
            changed_source.write_bytes(p0.encoded(changed_benchmark))
            expect('FMS_role_with_changed_mass',lambda:p0.build(changed_source),
                   'Published preparation differs from source inputs')

            config_path, template_path = root/'config.json',root/'template.json'
            config_path.write_bytes(p0.encoded({'offline':True}))
            template_path.write_bytes(p0.encoded(request('validation','XB-T0-0-0',bad_source)))
            expect('seal_does_not_execute_P0_registry_build',
                   lambda:contracts.seal('P0',config_path,template_path,root/'REQUEST.json'))
            bad_out = root/'bad_p0_result'; bad_out.mkdir()
            expect('P0_build_after_seal_rejects_bad_registry',
                   lambda:contracts._p0({'offline':True},{'registry':bad_source},bad_out),
                   'Unknown point role')
            good_out = root/'good_p0_result'; good_out.mkdir()
            result = contracts._p0({'offline':True},{'registry':source},good_out)
            if result['software_status']!='PASS' or result['evidence_status']!='DESIGN_RECORDS':
                raise AssertionError(result)
            cases.append({'case':'P0_result_is_design_evidence','result':'PASS',
                          'software_status':result['software_status'],
                          'evidence_status':result['evidence_status'],
                          'limitations':result['limitations']})
    return {'schema':'xb-p0-role-mode-review-v1','source_commit':SOURCE_SHA,
            'sources':sources,'status':'PASS','cases':cases,
            'published_point_counts':frozen['point_counts'],
            'published_XB_diagnostic_count':sum(p['model_id']=='XB-pureSU3' and p['role']=='diagnostic'
                                                for p in frozen['points']),
            'scope':'Narrow existing validator checks; no physical calculation or scientific promotion',
            'isolated_dependencies':['synthetic observational release and rule table',
                                     'full checkout source inventory and Git attribution mechanics'],
            'unmodified_real_checks':['p0_register.build','p0_register.freeze/verify',
                                      'contracts.verified_registry','contracts.validate_request role/mode guards',
                                      'contracts.seal','contracts._p0'],
            'not_claimed':['full original P0 replay','source-calibration truth or independence',
                           'P1-P10 execution','authorization to launch physics']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=Path(__file__).parent/'p0_checks/cache')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('xb_p0_contract_checks.json'))
    args=parser.parse_args()
    result=run(args.cache.resolve(),args.offline)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'cases':len(result['cases']),
                      'source_commit':result['source_commit']},ensure_ascii=False))


if __name__=='__main__':
    main()
