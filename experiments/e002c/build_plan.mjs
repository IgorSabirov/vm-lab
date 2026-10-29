// Deterministic design manifest only. This does not execute physics or enqueue a VM job.
function buildE002cPlan() {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const models = ["QS","RR_QS"];
  const core = [];
  for (const phi of [0,0.5]) for (const detuning of [-0.5,0,0.5]) for (const dephasing of [0,0.05,0.25])
    core.push({phi_over_pi:phi,detuning,dephasing,family:"crossed"});
  for (const phi of [-0.5,1]) core.push({phi_over_pi:phi,detuning:0,dephasing:0.05,family:"flux_closure"});
  const strip=[];
  for (const phi of [0,0.5]) for (const detuning of [-2,-1,-0.25,0.25,1,2])
    strip.push({phi_over_pi:phi,detuning,dephasing:0.05,family:"resonance_strip"});
  const all=core.concat(strip);
  const anchors=[[0,0,0.05],[0.5,0,0.05],[0,-0.5,0],[0.5,0.5,0.25]];
  const cases=[];
  for(const m of models) for(let i=0;i<all.length;i++) cases.push({id:`${m}_P${String(i+1).padStart(2,"0")}_dt010`,model:m,point:i+1,...all[i],dt:0.01,horizon:200,main_steps:20000});
  for(const m of models) for(const a of anchors) {
    const i=all.findIndex(p=>p.phi_over_pi===a[0]&&p.detuning===a[1]&&p.dephasing===a[2]);
    assert(i>=0,"Missing refinement anchor");
    cases.push({id:`${m}_P${String(i+1).padStart(2,"0")}_dt005`,model:m,point:i+1,...all[i],dt:0.005,horizon:200,main_steps:40000});
  }
  const ic=[];
  for(let i=0;i<core.length;i++) ic.push({id:`IC1_QS_P${String(i+1).padStart(2,"0")}_dt010`,model:"IC1_QS",point:i+1,...core[i],dt:0.01,horizon:200,main_steps:20000});
  for(const a of anchors) {
    const i=core.findIndex(p=>p.phi_over_pi===a[0]&&p.detuning===a[1]&&p.dephasing===a[2]);
    ic.push({id:`IC1_QS_P${String(i+1).padStart(2,"0")}_dt005`,model:"IC1_QS",point:i+1,...core[i],dt:0.005,horizon:200,main_steps:40000});
  }
  const mainSteps=cases.reduce((s,c)=>s+c.main_steps,0);
  const icSteps=ic.reduce((s,c)=>s+c.main_steps,0);
  assert(all.length===32&&core.length===20,"Wrong point count");
  assert(new Set(all.map(p=>JSON.stringify([p.phi_over_pi,p.detuning,p.dephasing]))).size===32,"Duplicate point");
  assert(cases.length===72&&mainSteps===1600000,"Wrong mandatory work");
  assert(ic.length===24&&icSteps===560000,"Wrong IC transfer work");
  assert(new Set(cases.concat(ic).map(c=>c.id)).size===96,"Duplicate ID");
  assert(cases.every(c=>Number.isInteger(c.horizon/c.dt)),"Nonintegral steps");
  const tStep=422.035/240000;
  const estimate=n=>Math.round(n*tStep*1.25+90);
  const coreSeconds=estimate(mainSteps);
  const maxIcSteps=48*10000+60000+icSteps;
  const extendedSteps=mainSteps+icSteps+60000;
  const icTargets=[
    {edge:"01",pL:0.17647321418949896,pR:0.7529375001334022,loss:0.025894967777304632},
    {edge:"12",pL:0.1764732141815391,pR:0.7529375001471508,loss:0.025894967776122},
    {edge:"02",pL:0.26415137775171826,pR:0.6301880711475976,loss:0.038317472162921355}
  ].map(t=>({...t,loss_per_L:t.loss/t.pL,
    conditional_C_given_L:2*(0.1+0.01+0.05-t.loss/t.pL)/0.05,
    alpha_necessary_lower_bound_at_exact_target:t.loss/t.pR,
    inventory_stationarity_residual:t.pR-(1-(1+0.1/0.25)*t.pL)}));
  assert(icTargets.every(t=>t.conditional_C_given_L>=0&&t.conditional_C_given_L<=1&&
    Math.abs(t.inventory_stationarity_residual)<1e-8&&t.alpha_necessary_lower_bound_at_exact_target<=2),
    "IC target violates a necessary positivity/balance condition");
  const plan={
    experiment:"E002c",version:"v001",created_date_moscow:"2026-10-29",
    status:"PROTOCOL_PREPARED_NOT_EXECUTION_FROZEN",
    production_runner_ready:false,vm_calibration_completed:false,launch_authorized:false,damage_authorized:false,
    parent_commit:"158bf65f51664363592da0d9cd1aec84ace45326",
    model_source_commit:"556736fd5c6b23c22b24751accab63932a7c4825",
    baseline_result_commit:"8adfd0564884bdb4b7b2adad7bad2ea5435d25b8",
    primary:"IC1_QS structural feasibility and held-out transport; joint QS/RR mechanism screen is retained if IC fitting fails.",
    controls:{Q_formula:"C/2",IC_forward:"sqrt(alpha_e)*Bplus_e*C_e",IC_reverse:false,
      source:"sqrt(0.5)*sigma_plus_0",sink:"sqrt(0.5)*sigma_minus_2",
      flux:"theta01+theta12-theta02",gauge:"theta01=theta12=0; theta02=-Phi",
      detuning:"epsilon*n1",noise:"independent sqrt(gamma)*Z_i, i=0,1,2",
      rates_refit_after_interventions:false},
    points:all,cases,conditional_ic_cases:ic,
    ic_target_precheck:{status:"NECESSARY_CONDITIONS_PASS_NOT_EXISTENCE_PROOF",
      targets:icTargets,source_file:"data/e002b_targets.json",source_commit:"556736fd5c6b23c22b24751accab63932a7c4825",
      allowed_loss_per_L:[0.135,0.16],notes:"With exact stationary target: 0<=C|L<=1, pR=1-1.4pL, alpha>=loss/pR. Tolerant matching changes the exact-target lower bound."},
    ic_search:{parameters:["alpha01","alpha12","alpha02"],bounds:[0.0001,2],
      starts_factors:[0.25,1,4],max_function_evaluations_per_start:16,max_evaluations:48,
      optimizer:"scipy.optimize.minimize(method='Powell'), log-rates; maxfev=16 per start; xtol=1e-3, ftol=1e-4",
      fit_dt:0.02,fit_horizon:200,maximum_fit_steps:480000,
      objective_fields:["pL01","pL12","pL02","loss01","loss12","loss02"],hop_in_objective:false,
      validation_dts:[0.01,0.005],validation_maximum_base_steps:60000,
      failure_label:"no_match_found_within_declared_search; not a nonexistence proof"},
    conditional_extension:{base_horizon:200,extended_horizon:400,trigger:"declared stationarity gate fails; paired dt cases both extend",
      max_extensions_per_case:1,fit_trials_extend:false,selection_by_transport_or_entanglement:false,
      maximum_extra_steps_all_stages:extendedSteps},
    calibration:{status:"NOT_RUN",cases:8,steps_per_case:2000,main_steps:16000,
      expected_seconds_provisional:120,lower_seconds_provisional:30,upper_seconds_provisional:300,
      includes:"model build, RK4, masks/dark diagnostics, witness/PT samples, checkpoints and complete report",
      calibration_integration_seconds:20,dt:0.01},
    work:{mandatory_cases:72,mandatory_main_steps:mainSteps,mandatory_rhs_calls:4*mainSteps,
      maximum_ic_extra_steps:maxIcSteps,maximum_total_base_steps:mainSteps+maxIcSteps,
      maximum_total_steps_with_extensions:mainSteps+maxIcSteps+extendedSteps},
    runtime:{status:"ENGINEERING_ESTIMATE_REQUIRES_VM_CALIBRATION",
      baseline_trajectory_seconds:422.035,baseline_steps:240000,seconds_per_step:tStep,
      assumed_new_diagnostics_multiplier:1.25,setup_and_report_allowance_seconds_per_stage:90,
      mandatory_expected_seconds_provisional:coreSeconds,
      mandatory_interval_seconds_provisional:[Math.floor(.6*coreSeconds),Math.ceil(1.4*coreSeconds)],
      maximum_ic_stage_expected_seconds_provisional:estimate(maxIcSteps),
      maximum_base_stages_expected_seconds_provisional:coreSeconds+estimate(maxIcSteps),
      maximum_base_and_extensions_expected_seconds_provisional:coreSeconds+estimate(maxIcSteps)+estimate(extendedSteps),
      production_gate:"Freeze calibrated branch-specific formula and +/-40% engineering range before main queue request; time audit precedes science."},
    output:{full_matrix_bytes_complex128:216*216*16,
      matrix_times_base:[0,0.2,1,2,5,10,20,50,100,190,200],matrix_times_extension:[300,390,400],
      report_scalar_columns_max:56,full_scalar_interval:0.2,entanglement_interval:2,
      series_format:"lossless float64 npz plus schema; allow_pickle=false",
      diagnostic_columns_max:128,diagnostic_export_grid:"0:2:20 and 24:4:end",
      diagnostic_rows_per_base_case:56,diagnostic_rows_per_extended_case:106,
      maximum_exported_trajectories:98,evidence_budget_bytes_per_case:80*1024,
      report_metadata_reserve_bytes:1024*1024,
      report_size_bound_bytes:98*(246*56*8+106*128*8+80*1024)+1024*1024,
      report_grid:"0:0.2:10 and 12:2:end; all omitted-sample extrema retained separately",
      report_rows_per_base_case:146,report_rows_per_extended_case:246,
      result_md_max_bytes:24576,report_budget_bytes:30*1024*1024,report_files_max:500,
      report_file_max_bytes:8*1024*1024,full_budget_bytes:3*1024**3,
      disk_floor_bytes:1.5*1024**3,required_free_bytes:4.5*1024**3,
      conditional_probability_floor:1e-6,reduced_state_export_times:[2,20,"endpoint"],
      conditional_states_in_report:"unnormalized 8x8 node blocks for 8 masks; normalize only above floor; no full 216x216 matrices"},
    audit:{generator:"experiments/e002c/build_plan.mjs",structural_assertions_passed:7,
      simulation_tests_executed:false,algebra_runner_tests_executed:false}
  };
  assert(plan.work.maximum_total_base_steps===2700000,"Total work mismatch");
  assert(plan.work.maximum_total_steps_with_extensions===4920000,"Extension count mismatch");
  assert(plan.output.report_size_bound_bytes<=plan.output.report_budget_bytes,"Report budget exceeded");
  plan.audit.structural_assertions_passed=11;
  return plan;
}
console.log(JSON.stringify(buildE002cPlan(), null, 2));
