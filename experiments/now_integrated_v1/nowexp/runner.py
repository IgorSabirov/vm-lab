"""Bounded jobs with verified source, durable rows, branch checkpoints and supervision."""
import argparse
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

from .engine import Engine, canonical_hash
from .enumeration import FiniteEnumeration
from .state import Config
from .provenance import (atomic_json, read_json, digest, environment, gate,
                         verify_source, configure_io_budget)
from .observables import summarize, paired_contrasts, ancestor_report, distribution


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("reviewer", "smoke", "calibrate", "main"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--signature-library", type=Path, help="optional already-built Serbian C++ kernel")
    parser.add_argument("--acceptance")
    parser.add_argument("--smoke-report")
    parser.add_argument("--calibration")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reviewer-name")
    parser.add_argument("--fault", choices=("after_row", "after_checkpoint", "finalization", "hang"))
    parser.add_argument("--fault-fraction", type=float, default=.8)
    parser.add_argument("--diagnostic-wall-cap", type=float)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if len(args.source_commit) != 40 or any(c not in "0123456789abcdef" for c in args.source_commit):
        raise ValueError("exact GitHub source commit required")
    if args.fault and (args.phase not in ("smoke", "reviewer") or not 0 < args.fault_fraction <= 1):
        raise ValueError("fault injection only in bounded diagnostic phases")
    if args.diagnostic_wall_cap is not None and (args.phase not in ("smoke", "reviewer") or args.diagnostic_wall_cap <= 0):
        raise ValueError("shortened wall budget only in diagnostic phases")
    if args.phase == "reviewer" and not args.reviewer_name:
        raise ValueError("external reviewer identity required")
    return args


def make_tasks(plan, cases, phase):
    limits = plan["phase_limits"][phase]
    selected = cases["cases"] if phase == "main" else [c for c in cases["cases"] if c["id"] in limits["cases"]]
    if not selected or len({c["id"] for c in cases["cases"]}) != len(cases["cases"]):
        raise ValueError("empty cases or duplicate case IDs")
    if phase != "main" and {c["id"] for c in selected} != set(limits["cases"]):
        raise ValueError("unknown phase case")
    tasks = []
    for case in selected:
        cfg = Config(**case["config"], thresholds=plan["acceptance"]).validate()
        if case["sampling_mode"] == "deterministic":
            if cfg.memory != "classical" or cfg.classical_survival != 1 or cfg.forced_content is None:
                raise ValueError("mislabelled deterministic case: "+case["id"])
            mode, seeds = "deterministic", [0]
        elif cfg.memory == "classical" and cfg.classical_survival == 1:
            mode, seeds = "finite_enumeration", [0]
        elif phase in ("main", "calibrate"):
            mode, seeds = "finite_enumeration", [0]
        else:
            mode, seeds = "seed_ensemble", range(limits["seeds"])
        for seed in seeds:
            tasks.append(dict(case_id=case["id"], config=asdict(cfg), sampling_mode=mode, seed=seed))
    if phase in ("main", "calibrate"):
        for name in plan["monte_carlo_validation"]["cases"]:
            case = next((c for c in selected if c["id"] == name), None)
            if case is None:
                continue
            cfg = Config(**case["config"], thresholds=plan["acceptance"]).validate()
            for seed in range(plan["monte_carlo_validation"]["seeds"] if phase == "main" else limits["seeds"]):
                tasks.append(dict(case_id="mc::"+name, config=asdict(cfg), sampling_mode="seed_ensemble", seed=seed))
    if phase in ('smoke','main','calibrate'):
        for control in plan.get('design_controls',[]):
            if phase not in control['phases']:continue
            cfg=Config(**control['config'],thresholds=plan['acceptance']).validate()
            tasks.append(dict(case_id='control::'+control['id'],config=asdict(cfg),sampling_mode='design_control',seed=0,
                              control_kind=control['kind'],design_ids=control['design_ids']))
    return selected, tasks



def workload_inventory(plan, cases):
    """Describe actual generated tasks without executing a trajectory."""
    from collections import Counter
    return {phase: dict(tasks=len(tasks), modes=dict(Counter(t['sampling_mode'] for t in tasks)))
            for phase in ('reviewer','smoke','calibrate','main')
            for _, tasks in [make_tasks(plan, cases, phase)]}


def validate_workload(plan, cases, amendment=None):
    inventory = workload_inventory(plan, cases)
    count = inventory['main']['tasks']
    if plan.get('proposed_main_tasks') != count:
        raise ValueError('declared main workload differs from make_tasks')
    if plan.get('workload_inventory') != inventory:
        raise ValueError('declared phase workload differs from make_tasks')
    if amendment is not None and amendment.get('main_task_count') != count:
        raise ValueError('amendment workload differs from normative protocol')
    return inventory


def context(root, args):
    files = verify_source(root, args.source_commit, args.source_manifest)
    plan = read_json(root/"preregistration/PROTOCOL.json")
    cases = read_json(root/"preregistration/CASES.json")
    validate_workload(plan, cases, read_json(root/"preregistration/FOUR_CANDIDATE_AMENDMENT.json"))
    source_id, config_id = digest(files), digest(cases)
    admission = gate(root, args.phase, source_id, config_id, args.acceptance, args.smoke_report, args.calibration)
    selected, tasks = make_tasks(plan, cases, args.phase)
    limits = dict(plan["phase_limits"][args.phase])
    if args.diagnostic_wall_cap is not None:
        if args.diagnostic_wall_cap > limits["hard_wall_seconds"]:
            raise ValueError("diagnostic cap cannot enlarge the budget")
        limits["hard_wall_seconds"] = args.diagnostic_wall_cap
    if admission.get("forecast"):
        forecast = admission["forecast"]
        if forecast["task_count"] != len(tasks):
            raise ValueError("forecast workload mismatch")
        limits.update({k:forecast[k] for k in ("hard_wall_seconds", "memory_limit_mib", "disk_limit_mib")})
    return files, plan, cases, source_id, config_id, admission, selected, tasks, limits


def supervise(root, args):
    ctx = context(root, args)
    limits, output = ctx[-1], args.output
    if not args.resume and output.exists() and any(output.iterdir()):
        raise ValueError("output is not empty; use a new directory or --resume")
    output.mkdir(parents=True, exist_ok=True)
    configure_io_budget(output, limits["disk_limit_mib"]*1024**2, 2*1024**3)
    attempts_path = output/"ATTEMPTS.json"
    attempts = read_json(attempts_path) if args.resume else []
    # A dead supervisor cannot know its unlogged work: reserve is charged, never erased.
    for attempt in attempts:
        if attempt["state"] == "RUNNING":
            attempt.update(state="UNRECORDED_TERMINATION", charged_seconds=attempt["reserved_seconds"])
    prior = sum(x["charged_seconds"] for x in attempts)
    remaining = limits["hard_wall_seconds"]-prior
    if remaining <= 0:
        raise RuntimeError("cumulative attempt budget exhausted")
    started = time.monotonic()
    current = dict(attempt=len(attempts)+1, state="RUNNING", started_utc=time.time(),
                   reserved_seconds=remaining, charged_seconds=0., fault=args.fault)
    attempts.append(current)
    atomic_json(attempts_path, attempts)
    log = (output/f"attempt_{len(attempts):03d}.log").open("w")
    env = dict(os.environ)
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    process = subprocess.Popen([sys.executable, str(root/"run.py"), *sys.argv[1:], "--_worker"],
        env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    reason, interrupted, peak_rss = None, [], 0
    old_handlers = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        old_handlers[sig] = signal.signal(sig, lambda signum, frame: interrupted.append(signum))
    try:
        while process.poll() is None:
            elapsed = time.monotonic()-started
            try:
                status = Path(f"/proc/{process.pid}/status").read_text()
                rss = next(int(line.split()[1]) for line in status.splitlines() if line.startswith("VmRSS:"))
                peak_rss = max(peak_rss, rss)
            except (OSError, StopIteration):
                pass
            if interrupted:
                reason = "USER_INTERRUPT"
            elif elapsed >= remaining:
                reason = "HARD_WALL_LIMIT"
            elif peak_rss > limits["memory_limit_mib"]*1024:
                reason = "RSS_LIMIT"
            elif shutil.disk_usage(output).free < 2*1024**3:
                reason = "DISK_RESERVE"
            if reason:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(.05)
        code = process.wait()
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        log.close()
    current.update(state="COMPLETED" if code == 0 else "FAILED", returncode=code,
                   charged_seconds=time.monotonic()-started, reason=reason,
                   peak_worker_rss_mib=peak_rss/1024, finished_utc=time.time())
    atomic_json(attempts_path, attempts)
    total = sum(x["charged_seconds"] for x in attempts)
    run_path = output/"RUN.json"
    report = read_json(run_path) if run_path.exists() else {}
    report.update(complete=code == 0 and report.get("complete", False),
                  technical_pass=code == 0 and report.get("technical_pass", False),
                  supervisor_exit_code=code, cumulative_attempt_seconds=total,
                  attempt_count=len(attempts), supervisor_reason=reason)
    forecast = ctx[5].get("forecast")
    if forecast:
        report["runtime_gate"] = "PASS" if forecast["lower_seconds"] <= total <= forecast["upper_seconds"] else "REVIEW_REQUIRED"
    atomic_json(run_path, report)
    atomic_json(output/"STATUS.json", dict(state="COMPLETED" if report["complete"] else "FAILED",
        attempt=len(attempts), exit_code=code, reason=reason, cumulative_seconds=total))
    print(json.dumps({k:v for k,v in report.items() if k not in ("files",)}, ensure_ascii=False))
    return code


def worker(root, args):
    files, plan, cases, source_id, config_id, admission, selected, tasks, limits = context(root, args)
    # Hard address-space ceiling in addition to supervisor RSS monitoring.
    resource.setrlimit(resource.RLIMIT_AS, (limits["memory_limit_mib"]*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (min(64, limits["disk_limit_mib"])*1024**2,)*2)
    env, output = environment(), args.output
    configure_io_budget(output, limits["disk_limit_mib"]*1024**2, 2*1024**3)
    fingerprint = digest(dict(source=source_id, commit=args.source_commit, phase=args.phase,
                              tasks=tasks, environment=digest(env),
                              signature_library=None if args.signature_library is None else __import__("hashlib").sha256(args.signature_library.read_bytes()).hexdigest()))
    checkpoint = output/"CHECKPOINT.json"
    cursor, active, row_hashes, rows = 0, None, [], []
    if args.resume:
        saved = read_json(checkpoint)
        if saved.get("schema") != 3 or saved["fingerprint"] != fingerprint:
            raise ValueError("checkpoint source/commit/config/environment mismatch")
        cursor, active, row_hashes = saved["cursor"], saved["active"], saved["row_hashes"]
        if len(row_hashes) != cursor:
            raise ValueError("invalid committed row count")
        for i, expected_hash in enumerate(row_hashes):
            row = read_json(output/"rows"/f"{i:06d}.json")
            # JSON normalizes tuples to lists; identity uses the same canonical form as the manifest.
            if digest(row) != expected_hash or digest(row["task_descriptor"]) != digest(tasks[i]):
                raise ValueError("committed row integrity mismatch")
            rows.append(row)
        if (output/"FAILED.json").exists():
            os.replace(output/"FAILED.json", output/f"FAILED_before_attempt_{len(read_json(output/'ATTEMPTS.json')):03d}.json")
    atomic_json(output/"SOURCE.json", dict(source_commit=args.source_commit, source_digest=source_id, files=files))
    atomic_json(output/"ENVIRONMENT.json", env)
    atomic_json(output/"STATUS.json", dict(state="RUNNING", cursor=cursor, planned=len(tasks)))
    started = time.perf_counter()
    fault_at = max(1, math.ceil(len(tasks)*args.fault_fraction))

    def save(state=None):
        atomic_json(checkpoint, dict(schema=3, fingerprint=fingerprint, cursor=cursor,
                                    active=state, row_hashes=row_hashes))

    def fault(point):
        if args.fault == "hang" and point == "after_checkpoint" and cursor >= fault_at:
            atomic_json(output/"FAULT_READY.json", dict(point=point, cursor=cursor, planned=len(tasks)))
            while True:
                time.sleep(1)
        if args.fault == point and (cursor >= fault_at or point == "finalization"):
            os._exit(86)

    try:
        save(active)
        while cursor < len(tasks):
            task = tasks[cursor]
            cfg = Config(**task["config"]).validate()
            begin = time.perf_counter()
            was_resumed = active is not None
            if task['sampling_mode']=='design_control':
                from .design_controls import execute
                control=execute(task['control_kind'],cfg,task['seed'])
                if not control['technical_pass']:raise ArithmeticError('design control failed: '+task['case_id'])
                payload,trace=dict(control_result=control),control
            elif task["sampling_mode"] == "finite_enumeration":
                job = FiniteEnumeration(cfg, saved=active, max_nodes=plan["max_enumeration_nodes"])
                while job.pending:
                    job.advance()
                    if job.nodes % plan["checkpoint_branch_interval"] == 0:
                        save(job.snapshot())
                payload, trace = job.result(), job.trace
            else:
                engine = Engine.restore(active) if active is not None else Engine(cfg, task["seed"])
                while engine.queue:
                    engine.step()
                payload, trace = dict(result=engine.result()), engine.snapshot()
            active = None
            row = dict(task_descriptor=task, task_id=digest([task,source_id])[:24], **task, **payload,
                       task_compute_seconds=time.perf_counter()-begin,
                       timing_scope="resumed_branch_suffix" if was_resumed else "complete_task")
            row["scientific_hash"] = digest(payload)
            if task["seed"] == 0 and (plan.get("trace_case_ids") is None or task["case_id"] in plan["trace_case_ids"]):
                atomic_json(output/"traces"/(row["task_id"]+".json"), trace)
                if task['sampling_mode'] != 'design_control':
                    from .geometry_diagnostics import diagnose
                    atomic_json(output/'geometry'/(row['task_id']+'.json'), diagnose(trace, args.signature_library))
            atomic_json(output/"rows"/f"{cursor:06d}.json", row)
            rows.append(row)
            cursor += 1
            fault("after_row")
            row_hashes.append(digest(row))
            save()
            fault("after_checkpoint")
        scientific_rows=[r for r in rows if r['sampling_mode']!='design_control']
        control_rows=[r for r in rows if r['sampling_mode']=='design_control']
        summaries = summarize(scientific_rows)
        phase_contrasts = [c for c in cases["contrasts"] if args.phase in c.get("phases", ("reviewer", "smoke", "calibrate", "main"))]
        contrasts = paired_contrasts(scientific_rows, phase_contrasts, plan["acceptance"]["profile_equivalence_tv"])
        if args.phase in ("smoke", "main") and any(v["status"] == "NOT_EVALUABLE" for v in contrasts.values()):
            raise ValueError("complete phase left a declared contrast unevaluable")
        from .memory import response
        responses = {}
        for case in selected:
            cfg = Config(**case["config"], thresholds=plan["acceptance"]).validate()
            if cfg.memory != "classical":
                key = digest([cfg.bath_modes,cfg.bath_coupling,cfg.detuning])
                if key not in responses:
                    responses[key] = dict(parameters=[cfg.bath_modes,cfg.bath_coupling,cfg.detuning],
                        atoms=response(cfg.bath_modes,cfg.bath_coupling,cfg.detuning))
        atomic_json(output/"RESPONSE.json", responses)
        # Full outcome rows remain authoritative; do not duplicate large profile strings.
        exported_summaries = {}
        for name, summary in summaries.items():
            item = dict(summary)
            if any(name.startswith(prefix) for prefix in plan.get("compact_profile_case_prefixes", [])):
                item.pop("joint_profile", None)
                item["joint_profile_storage"] = "Reconstruct exactly from normalized outcomes in rows/ and ROWS_INDEX.json"
            exported_summaries[name] = item
        atomic_json(output/"METRICS.json", dict(summary=exported_summaries, contrasts=contrasts))
        from .amendment_report import report as amendment_report
        atomic_json(output/'FOUR_CANDIDATE_RETURN.json', amendment_report(scientific_rows, contrasts))
        validation = {}
        for name in plan["monte_carlo_validation"]["cases"]:
            if name in summaries and "mc::"+name in summaries:
                exact, sample = summaries[name], summaries["mc::"+name]
                half = math.sqrt(math.log(40)/(2*sample["n_tasks"]))
                difference = sample["q_final"]-exact["q_final"]
                validation[name] = dict(exact_q=exact["q_final"], sampled_q=sample["q_final"],
                    difference=difference, nominal_95_halfwidth=half, within_bound=abs(difference)<=half,
                    interpretation="Diagnostic seed-model comparison; not an independence proof")
        atomic_json(output/"MONTE_CARLO_VALIDATION.json", dict(status="EXECUTED" if validation else "NOT_SCHEDULED_IN_THIS_PHASE", comparisons=validation))
        contracts = read_json(root/"preregistration/ANCESTOR_CONTRACTS.json")["contracts"]
        atomic_json(output/"ANCESTOR_RETURN.json", ancestor_report(contracts, scientific_rows, summaries, contrasts))
        controls={r['case_id']:r['control_result'] for r in control_rows}
        atomic_json(output/'DESIGN_CONTROLS.json',controls)
        from .scope_evidence import collect,returns
        mapping=read_json(root/'preregistration/IMPLEMENTATION_MAP.json')
        evidence=collect(mapping,contrasts,controls,args.source_commit,config_id)
        atomic_json(output/'DESIGN_EVIDENCE.json',evidence)
        prospective=read_json(root/'preregistration/SCOPE_RETURN_CONTRACTS.json')
        atomic_json(output/'SCOPE_ANCESTOR_RETURN.json',returns(prospective,contrasts,controls))
        if args.phase in ('smoke','main') and plan.get('scope_evidence_required'):
            if any(not values or not all(x['complete'] for x in values) for values in evidence['comparisons'].values()):
                raise ValueError('declared design comparison lacks completed executable evidence')
        atomic_json(output/"ROWS_INDEX.json", dict(row_hashes=row_hashes,
            scientific_hashes=[r["scientific_hash"] for r in rows],
            storage="canonical per-task rows; no duplicate full TRAJECTORIES dump"))
        fault("finalization")
        report = dict(phase=args.phase, source_commit=args.source_commit, source_digest=source_id,
            config_digest=config_id, environment_fingerprint=digest(env), complete=True,
            technical_pass=all(r["finished"] for _,r in distribution(scientific_rows)) and all(r['control_result']['technical_pass'] for r in control_rows),
            scientific_confirmation=False, task_count=len(rows),
            physical_outcome_rows=sum(len(r.get("outcomes", [None])) for r in scientific_rows),
            design_control_tasks=len(control_rows),
            events=sum(r.get("executed_events", r.get("result", {}).get("events", 0)) for r in rows),
            current_worker_seconds=time.perf_counter()-started,
            runtime_gate="UNCALIBRATED_BOUNDED_MEASUREMENT", expected_seconds=None,
            max_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            output_bytes=sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
            contrasts_evaluated=len(contrasts), observed_limits=limits)
        atomic_json(output/"RUN.json", report)
    except Exception as exc:
        atomic_json(output/"FAILED.json", dict(type=type(exc).__name__, message=str(exc),
                    cursor=cursor, planned=len(tasks), source_digest=source_id))
        raise


def run_cli(root):
    root = Path(root).resolve()
    args = arguments()
    if args._worker:
        worker(root, args)
    else:
        sys.exit(supervise(root, args))
