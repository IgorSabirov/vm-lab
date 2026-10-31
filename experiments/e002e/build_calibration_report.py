"""Build an auditable budget from fully verified GitHub calibration files."""
import argparse,hashlib,json,math,time
from pathlib import Path
import numpy as np
from e002e_exp.plan import selected_work,workload
from e002e_exp.runtime import kernel_hash

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'experiments/e002e'
def save(name,data):
    p=DEST/name;p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n');return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    start=time.perf_counter();p=argparse.ArgumentParser();p.add_argument('--report-commit',required=True);a=p.parse_args()
    folder=ROOT/'results/E002e_FINAL_CAL_v001_r001';r=json.loads((folder/'run.json').read_text());m=json.loads((folder/'files/metrics.json').read_text())
    assert r['job']['exit_code']==0 and r['export_errors']==[] and m['status']=='CALIBRATION_COMPLETED_NOT_ACCEPTED'
    # Caller has already used github_result_reader. Repeat byte checks locally.
    for name,meta in r['files'].items():
        b=(folder/name).read_bytes();assert len(b)==meta['bytes'] and hashlib.sha256(b).hexdigest()==meta['sha256']
    assert m['kernel_sha256']==kernel_hash()
    cases=m['cases'];assert len(cases)==6 and len(m['small_cases'])==10
    assert m['validation']['exit_code']==0 and m['validation']['executed_tests']==42
    seconds=r['job']['finished']-r['job']['started'];forecast=m['forecast']
    assert forecast['lower_seconds']<=seconds<=forecast['upper_seconds']
    phase=m['phase_times'];assert all(x['max_compute_threads_observed']==1 for x in phase)
    assert all(c['quality']['pass'] and c['refinement_quality']['pass'] and c['agreement']['pass_gate'] for c in cases)
    assert sum(len(c['responses']) for c in cases)==20
    qsteps=sum(s['steps'] for c in cases for s in c['qrt']['summaries']);assert qsteps==71500
    assert all(q['pass_gate'] for c in cases for q in c['qrt']['comparisons'])
    old=json.loads((DEST/'baseline_reference_v001.json').read_text());checks=[]
    for model,tol in [('QS',1e-8),('RR_QS',5e-6)]:
        c=next(c for c in cases if c['case']['model']==model and c['case']['phi_over_pi']==.5)
        ref=old['cases'][model];node=json.loads((folder/'files'/(c['id']+'_nodes.json')).read_text())
        dx={k:abs(v-ref['scalar_endpoint']['h' if k=='J_h' else k]) for k,v in c['raw'].items() if isinstance(v,(int,float)) and ('h' if k=='J_h' else k) in ref['scalar_endpoint']}
        nd=float(abs(np.array(node['real'])+1j*np.array(node['imag'])-np.array(ref['nodes_real'])-1j*np.array(ref['nodes_imag'])).max())
        j=c['conditional']['j6']['value'];jr=ref['scalar_endpoint']['h_m6_N2']/ref['scalar_endpoint']['p_m6_N2']
        check=dict(model=model,primitive_count=len(dx),maximum_primitive_difference=max(dx.values()),maximum_node_difference=nd,j6_difference=abs(j-jr),tolerance=tol,status='PASS' if max(max(dx.values()),nd)<=tol else 'FAIL',reference_path=ref['path'],reference_sha256=ref['sha256'])
        assert check['status']=='PASS';checks.append(check)
    save('baseline_final_checks.json',checks)
    rates={}
    ness_names={'build','LU_factor','LU_NESS','LU_quality','ILU_factor','GMRES_NESS','GMRES_quality','condition'}
    for c in cases:
        rows={x['name'].split('/',1)[1]:x['seconds'] for x in phase if x['name'].startswith(c['id']+'/')}
        model=c['case']['model'];rate=rates.setdefault(model,dict(ness=0.,static_pair=0.,frequency_pair=0.,qrt_step=0.))
        rate['ness']=max(rate['ness'],sum(t for k,t in rows.items() if k in ness_names))
        static=[k for k in rows if k.startswith('static_') and not k.startswith('static_ref_')]
        if static:rate['static_pair']=max(rate['static_pair'],max(rows[k]+rows['static_ref_'+k[len('static_'):]] for k in static))
        freq=[k for k in rows if k.startswith('frequency_') and not k.startswith('frequency_ref_')]
        if freq:rate['frequency_pair']=max(rate['frequency_pair'],max(rows[k]+rows['frequency_ref_'+k[len('frequency_'):]] for k in freq))
        rate['qrt_step']=max(rate['qrt_step'],max(s['elapsed_seconds']/s['steps'] for s in c['qrt']['summaries']))
    components={};budgets={}
    for stage in ('G','baseline','F2'):
        work=selected_work(stage);detail={}
        if stage=='G':
            per=max(x['seconds'] for x in m['small_cases'])
            detail=dict(small_solve_and_checks=92*per,condition_export_and_startup=2.)
        else:
            cmap={c['id']:c for c in work['full']}
            detail['ness']=sum(rates[c['model']]['ness'] for c in work['full'])
            detail['static_pairs']=sum((len(c['tasks'])-1)*rates[c['model']]['static_pair'] for c in work['full'])
            detail['frequency_pairs']=sum(rates[cmap[f['base_id']]['model']]['frequency_pair'] for f in work['frequency'])
            qids={q['base_id'] for q in work['correlations']}
            detail['qrt_two_grids']=sum(30000*rates[cmap[cid]['model']]['qrt_step'] for cid in qids)
            detail['unmeasured_export_and_overhead']=1.+.12*len(work['full'])
        estimate=sum(detail.values());center=float(math.ceil(estimate))
        lo=max(.1,.65*center);hi=1.55*center+2
        if stage=='F2':lo=.45*center;hi=2.5*center+5
        budgets[stage]=dict(expected_seconds=center,lower_seconds=round(lo,3),upper_seconds=round(hi,3));components[stage]=detail
    rss=max(x['max_rss_bytes'] for x in phase);vm=max(x['max_vm_bytes_sampled'] for x in phase);factors=max(c['simultaneous_factor_storage_bytes'] for c in cases)
    peak=max(1024**3,math.ceil(2*max(rss,vm,factors)))
    memory=dict(peak_additional_bytes=peak,reserve_bytes=1024**3,measured_peak_rss_bytes=rss,measured_peak_vm_bytes=vm,simultaneous_factor_storage_bytes=factors)
    qcase=next(c for c in cases if c['qrt']['horizon']==100.)
    verification=dict(status='VERIFIED_GITHUB',kernel_sha256=kernel_hash(),source_commit=r['source_commit'],report_commit=a.report_commit,run_id=r['run_id'],
        environment=m['environment'],numerics=json.loads((folder/'files/config.json').read_text())['numerics'],
        baseline_equivalence_pass=True,observable_accuracy_pass=True,baseline_checks=checks,
        qrt_validation=dict(status='VERIFIED_GITHUB',full_model_representative=True,reference_method='third_RK4_grid',maximum_scaled_discrepancy=qcase['qrt']['comparisons'][-1]['max_scaled'],horizon=100.,grids=[.01,.005,.0025],source_commit=r['source_commit'],report_commit=a.report_commit,tail_status='TAIL_UNRESOLVED'),
        stage_budgets=budgets,stage_memory_budgets={s:memory for s in budgets},measured_rates=rates,budget_components=components,
        runtime=dict(expected_seconds=forecast['expected_seconds'],actual_seconds=seconds,deviation_seconds=seconds-forecast['expected_seconds'],status='PASS'),
        work=dict(tests=42,small_cases=10,full_cases=6,ness_solves=12,static_solves=36,frequency_solves=4,qrt_steps=qsteps,block_rhs=4*qsteps),
        limitations=['QRT third-grid validation covers QS phi=pi/2; RR/IC production remains checked on two grids.', 'RR/IC H100 runtime extrapolated from H1; F2 v=0/.5 costs extrapolated without viewing heldout outcomes.', 'Sampled VmSize is not a continuous maximum; 2x forecast plus 1 GiB reserve used.', 'Ancestor cgroup and CPU quota are hidden; hard process address-space limit is measured and enforced.', 'Two-method errors are engineering estimates, not rigorous total-error bounds.', 'F2 requires frozen predictions after declared training; full-line width and infinite correlation tails remain unresolved.'],
        scientific_acceptance=False,production_started=False)
    calsha=save('calibration_verification_final.json',verification)
    review=dict(status='REVIEWED_AND_CHECKED',kernel_sha256=kernel_hash(),implementation_commit=r['source_commit'],reviewed_source_commit=r['source_commit'],
        review_scope='Prior Copilot review of scientific implementation plus assistant-reviewed launcher/library/resource compatibility delta and 42 tests on target VM',
        prior_copilot_implementation_commit='98cb6b0a7d8c60036308307e9ef1c3005f1d6dc8',prior_copilot_kernel_sha256='9264d19764462081e07d24907109764bb04839eb1c3c998e640858634ff91bd3',
        copilot_reviewed_new_delta=False,delta_reviewed_by='assistant',target_vm_test_report_commit=a.report_commit,tests_passed=42,open_code_findings=[],scientific_acceptance=False)
    reviewsha=save('implementation_review_final.json',review)
    for stage in ('G','baseline'):
        config=dict(experiment='E002e',mode='production',stage=stage,source_commit='FROM_VERIFIED_VM_LAUNCHER',source_kernel_sha256=kernel_hash(),address_space_limit_bytes=8*1024**3,
            copilot_review=dict(path='experiments/e002e/implementation_review_final.json',sha256=reviewsha),
            calibration_verification=dict(path='experiments/e002e/calibration_verification_final.json',sha256=calsha),
            forecast=budgets[stage],expected_workload=workload(selected_work(stage)),numerics=verification['numerics'])
        save('production_'+stage+'_config.json',config)
    save('calibration_report_build_runtime.json',dict(expected_seconds=.3,lower_seconds=.05,upper_seconds=2.,internal_seconds=time.perf_counter()-start))
    print(json.dumps(dict(runtime=verification['runtime'],budgets=budgets,memory=memory,rates=rates,baseline=checks,qrt=verification['qrt_validation']),ensure_ascii=False))

if __name__=='__main__':main()
