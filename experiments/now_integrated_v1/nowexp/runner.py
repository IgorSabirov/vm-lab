import argparse
from dataclasses import asdict
import json
from pathlib import Path
import resource
import time

from .engine import Engine, canonical_hash
from .state import Config
from .provenance import atomic_json, read_json, source_manifest, digest, environment, gate
from .observables import summarize, paired_contrasts, ancestor_report


def run_cli(root):
    parser = argparse.ArgumentParser(description="Integrated candidate: review before smoke, VM calibration before main")
    parser.add_argument("--phase", choices=("reviewer","smoke","calibrate","main"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--acceptance")
    parser.add_argument("--smoke-report")
    parser.add_argument("--calibration")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reviewer-name", default=None)
    args = parser.parse_args()
    if len(args.source_commit) != 40 or any(c not in "0123456789abcdef" for c in args.source_commit):
        raise ValueError("exact GitHub source commit required")
    if args.phase == "reviewer" and not args.reviewer_name:
        raise ValueError("identify external review run")
    files = source_manifest(root)
    source_digest = digest(files)
    plan = read_json(root/"preregistration"/"PROTOCOL.json")
    cases = read_json(root/"preregistration"/"CASES.json")
    config_digest = digest(cases)
    admission = gate(root, args.phase, source_digest, config_digest,
                     args.acceptance, args.smoke_report, args.calibration)
    limits = plan["phase_limits"][args.phase]
    selected = cases["cases"] if args.phase == "main" else [c for c in cases["cases"] if c["id"] in limits["cases"]]
    seeds = list(range(limits["seeds"]))
    tasks = [(c, seed) for c in selected for seed in ([0] if c.get("sampling_mode")=="deterministic" else seeds)]
    if not tasks or len({c["id"] for c in cases["cases"]}) != len(cases["cases"]):
        raise ValueError("empty workload or duplicate case IDs")
    if args.phase != "main" and {c["id"] for c in selected} != set(limits["cases"]):
        raise ValueError("unknown case in phase manifest")
    forecast = admission.get("forecast")
    if forecast and forecast["task_count"] != len(tasks):
        raise ValueError("forecast workload does not match manifest")
    env = environment()
    env_id = digest(env)
    fingerprint = digest(dict(source=source_digest, cases=config_digest, phase=args.phase,
                              seeds=seeds, selected=[c["id"] for c in selected], environment=env_id))
    output = args.output
    checkpoint = output/"CHECKPOINT.json"
    rows, cursor, active, elapsed_prior = [], 0, None, 0.0
    if args.resume:
        saved = read_json(checkpoint)
        if saved.get("schema") != 2:
            raise ValueError("unsupported runner checkpoint")
        if saved["fingerprint"] != fingerprint:
            raise ValueError("checkpoint belongs to a different experiment/environment")
        cursor, active = saved["cursor"], saved["active"]
        rows = [read_json(output/"rows"/(f"{i:06d}.json")) for i in range(cursor)]
        elapsed_prior = saved["elapsed_seconds"]
    elif output.exists() and any(output.iterdir()):
        raise ValueError("refuse to mix artifacts: choose an empty output or --resume")
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output/"ENVIRONMENT.json", env)
    atomic_json(output/"SOURCE.json", dict(source_commit=args.source_commit, source_digest=source_digest, files=files))
    start = time.perf_counter()
    hard_wall = forecast["hard_wall_seconds"] if forecast else limits["hard_wall_seconds"]
    memory_cap = forecast["memory_limit_mib"] if forecast else limits["memory_limit_mib"]
    disk_cap = forecast["disk_limit_mib"] if forecast else limits["disk_limit_mib"]

    def elapsed():
        return elapsed_prior + time.perf_counter()-start

    def save_active(engine=None):
        atomic_json(checkpoint, dict(schema=2, fingerprint=fingerprint, cursor=cursor,
                    active=None if engine is None else engine.snapshot(), elapsed_seconds=elapsed()))

    def enforce_limits():
        if elapsed() > hard_wall:
            raise RuntimeError("declared wall budget exhausted; checkpoint retained")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024 > memory_cap:
            raise RuntimeError("declared RSS limit exceeded; checkpoint retained")
        if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) > disk_cap*1024**2:
            raise RuntimeError("declared output disk limit exceeded")

    try:
        while cursor < len(tasks):
            case, seed = tasks[cursor]
            task_started = time.perf_counter()
            cfg = Config(**case["config"]).validate()
            engine = Engine.restore(active) if active is not None else Engine(cfg, seed)
            active = None
            save_active(engine)
            while engine.queue:
                engine.step()
                if engine.processed % plan["checkpoint_event_interval"] == 0:
                    save_active(engine)
                    enforce_limits()
            result = engine.result()
            task_id = canonical_hash([case["id"], seed, source_digest])[:24]
            row = dict(task_id=task_id, case_id=case["id"], seed=seed, config=asdict(cfg),
                       sampling_mode=case.get("sampling_mode","seed_ensemble"),
                       result=result, result_hash=canonical_hash(result),
                       task_compute_seconds=time.perf_counter()-task_started)
            row["timing_scope"] = "remaining_segment_after_resume" if args.resume else "complete_task"
            if seed == 0:
                atomic_json(output/"traces"/(task_id+".json"), engine.snapshot())
            atomic_json(output/"rows"/(f"{cursor:06d}.json"), row)
            rows.append(row)
            cursor += 1
            save_active()
            enforce_limits()
        summary = summarize(rows)
        contrasts = paired_contrasts(rows, cases["contrasts"])
        from .memory import response
        responses = {}
        for case in selected:
            cfg = Config(**case["config"]).validate()
            if cfg.memory != "classical":
                key = digest([cfg.bath_modes,cfg.bath_coupling,cfg.detuning])
                if key not in responses:
                    responses[key] = dict(parameters=[cfg.bath_modes,cfg.bath_coupling,cfg.detuning],
                        atoms=response(cfg.bath_modes,cfg.bath_coupling,cfg.detuning),
                        input_interface="two bright inputs", interpretation="finite spectral measure, not entire continuation profile")
        atomic_json(output/"RESPONSE.json", responses)
        contracts = read_json(root/"preregistration"/"ANCESTOR_CONTRACTS.json")["contracts"]
        atomic_json(output/"TRAJECTORIES.json", rows)
        atomic_json(output/"METRICS.json", dict(summary=summary, contrasts=contrasts))
        atomic_json(output/"ANCESTOR_RETURN.json", ancestor_report(contracts, rows, summary, contrasts))
        duration = elapsed()
        in_range = None if not forecast else forecast["lower_seconds"] <= duration <= forecast["upper_seconds"]
        report = dict(phase=args.phase, reviewer=args.reviewer_name, source_commit=args.source_commit,
            source_digest=source_digest, config_digest=config_digest, environment_fingerprint=env_id,
            complete=True, technical_pass=all(r["result"]["finished"] for r in rows),
            scientific_confirmation=False, trajectories=len(rows), events=sum(r["result"]["events"] for r in rows),
            runtime_seconds=duration, runtime_gate="UNCALIBRATED_BOUNDED_MEASUREMENT" if in_range is None else ("PASS" if in_range else "REVIEW_REQUIRED"),
            expected_seconds=None if not forecast else forecast["expected_seconds"],
            max_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            observed_limits=dict(wall=hard_wall,memory_mib=memory_cap,disk_mib=disk_cap),
            readiness_note="calibration report alone is not a forecast; estimate each backend on VM before main")
        atomic_json(output/"RUN.json", report)
        print(json.dumps(report, ensure_ascii=False))
    except Exception as exc:
        atomic_json(output/"FAILED.json", dict(type=type(exc).__name__, message=str(exc),
                    cursor=cursor, planned=len(tasks), source_digest=source_digest, elapsed_seconds=elapsed()))
        raise
