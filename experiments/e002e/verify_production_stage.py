"""Verify a fully downloaded, immutable GitHub stage report without VM raw data."""
import argparse
import json
from pathlib import Path
from infra.github_result_reader import read_github_result
from e002e_exp.export import verify_report
from e002e_exp.plan import selected_work, workload
from e002e_exp.runtime import kernel_hash


def main():
    parser = argparse.ArgumentParser()
    for field in ('run-id', 'source', 'report-commit', 'output'):
        parser.add_argument('--'+field, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    result = read_github_result(lambda repo, path, ref: (root/path).read_bytes(),
        repository='IgorSabirov/vm-lab', result_commit=args.report_commit,
        run_id=args.run_id, source_commit=args.source)
    assert result['execution_succeeded']
    report = root/'results'/args.run_id/'files'
    c = json.loads((report/'config.json').read_text())
    m = json.loads((report/'metrics.json').read_text())
    job = result['report']['job']
    elapsed = job['finished']-job['started']
    assert c['forecast']['lower_seconds'] <= elapsed <= c['forecast']['upper_seconds'], 'Runtime needs audit'
    assert not m['failure'] and m['runtime_gate']['status'] == 'PASS'
    assert m['source_commit'] == c['source_commit'] == args.source
    assert m['kernel_sha256'] == c['source_kernel_sha256'] == kernel_hash()
    assert m['environment_comparison']['comparable']
    assert m['environment_comparison']['memory']['status'] == 'PASS'
    work = selected_work(c['stage'])
    assert m['actual_counts'] == c['expected_workload'] == workload(work)
    verified = verify_report(report)
    assert (report/'README.md').read_bytes() == (report/'RESULT.md').read_bytes()
    dm = json.loads((report/'data_manifest.json').read_text())
    fm = json.loads((report/'full_manifest.json').read_text())
    assert dm['full_files'] == fm['files'] and dm['full_total_bytes'] == fm['total_bytes']
    records = []
    cases = [(f'small_{i:03d}', case) for i, case in enumerate(work['small'])]
    cases += [(case['id'], case) for case in work['full']]
    for case_id, case in cases:
        record = json.loads((report/(case_id+'.json')).read_text())
        assert record['id'] == case_id and record['case'] == case
        assert record['quality']['pass'] and record['refinement']['quality']['pass']
        assert record['refinement']['gate']['pass_gate']
        assert record['renewal']['status'] != 'FAIL'
        assert record['symmetry'].get('parity_status') != 'OPERATOR_CHECK_FAILED'
        records.append(record)
    responses = json.loads((report/'responses.json').read_text())
    assert len(responses) == m['actual_counts']['static_responses']+m['actual_counts']['frequency_responses']
    assert all(r['refinement_gate']['pass_gate'] for r in responses)
    assert all(q['refinement']['pass_gate'] for q in m['qrt'])
    assert not any(x['status'] == 'FAIL' for x in json.loads((report/'symmetry_pairs.json').read_text()))
    output = dict(status='VERIFIED_GITHUB', stage=c['stage'], run_id=args.run_id,
        source_commit=args.source, report_commit=args.report_commit, kernel_sha256=kernel_hash(),
        runtime=dict(**c['forecast'], actual_seconds=elapsed, deviation_seconds=elapsed-c['forecast']['expected_seconds'], status='PASS'),
        expected_workload=c['expected_workload'], actual_workload=m['actual_counts'],
        report_verification=verified, transport_files_verified=len(result['artifacts']),
        cases_checked=len(records), maximum_state_solver_difference=max(x['refinement']['state_difference_inf'] for x in records),
        memory=m['environment_comparison']['memory'], scientific_acceptance=False,
        full_data_access='NOT_ACCESSED; published report verified without raw VM state files')
    Path(args.output).write_text(json.dumps(output, indent=2, allow_nan=False)+'\n')
    print(json.dumps(output))


if __name__ == '__main__':
    main()
