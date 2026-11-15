"""Admitted, sequential nine-integration D+D local-response package."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, math, os, subprocess, sys, time, traceback

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/"infra/autonomy/admit.py").is_file())
ADAPTER = ROOT/"analysis/CCC_BBN_NETWORK_20261114/s3_standard/linx_dd_adapter_20261115"
IDENTITY = ADAPTER/"full_run_20261115"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(IDENTITY))
from infra.autonomy import admit, finish, execution_policy

PACKAGE = json.loads((HERE/"PACKAGE.json").read_text())
CONTRACT = json.loads((HERE/"CONTRACT.json").read_text())
REQUEST = json.loads((HERE/"RUN_REQUEST.json").read_text())
PLAN = json.loads((HERE/"EXECUTION_PLAN.json").read_text())
OUT = HERE/"results"/PACKAGE["id"]
OUT_REL = OUT.relative_to(ROOT)

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def validate_source():
    if os.environ.get("GITHUB_REPOSITORY") != "IgorSabirov/vm-lab":
        raise ValueError("Wrong repository")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("Automatic retries are forbidden")
    if os.environ.get("BASE_BRANCH") != PACKAGE["publication_branch"]:
        raise ValueError("Workflow base branch differs from frozen plan")
    sha = os.environ["SOURCE_SHA"]
    if git("rev-parse", "HEAD") != sha:
        raise ValueError("Checkout differs from merged source SHA")
    if REQUEST.get("execution_enabled") is not True or REQUEST.get("id") != PACKAGE["id"]:
        raise ValueError("Execution request disabled or mismatched")
    if PLAN.get("package_id") != PACKAGE["id"] or PLAN.get("publication_branch") != PACKAGE["publication_branch"]:
        raise ValueError("Execution plan/package mismatch")
    subprocess.run(["git","merge-base","--is-ancestor",PLAN["source_commit"],sha],cwd=ROOT,check=True)
    manifest = read(HERE/"INPUT_MANIFEST.json")
    changed = set(git("diff","--name-only",sha+"^1",sha).splitlines())
    if not changed.issubset(set(manifest["allowed_changed_paths"])):
        raise ValueError("Unexpected paths in package merge: "+repr(sorted(changed-set(manifest["allowed_changed_paths"]))))
    for item in manifest["files"]:
        path = ROOT/item["path"]
        if not path.is_file() or digest(path) != item["sha256"]:
            raise ValueError("Pinned input hash mismatch: "+item["path"])
    return sha

def reserve(sha):
    control = read(ROOT/"infra/autonomy/CONTROL.json")
    if not control["enabled"] or control.get("policy_version") != "20261115-sequential-no-daily-quota-v1":
        raise ValueError("Autonomy controller disabled or policy changed")
    validated = execution_policy.validate(PLAN, control["limits"], root=ROOT)
    if validated["executor"] != "github_actions":
        raise ValueError("Plan not admitted for GitHub Actions")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    candidate = {
        "id":PACKAGE["id"], "executor":"github_actions", "started_utc":now(),
        "status":"RESERVED", "source_sha":sha,
        "execution_plan_sha256":execution_policy.digest(PLAN),
        "workflow_run_id":run_id, "reservation_plan_kind":"sequential_nine_integration_local_jacobian",
        "budget":PACKAGE["budget"], "publication_branch":PACKAGE["publication_branch"],
        "scientific_acceptance":False
    }
    decision = admit.reserve(admit.read_ledger, admit.write_ledger,
             admit.actions_runs(datetime.now(timezone.utc)), candidate,
             datetime.now(timezone.utc), control["limits"], run_id)
    if not decision.get("admitted"):
        raise RuntimeError("Package not admitted: "+str(decision.get("reason")))
    result = {**decision, "execute":True, "phase":"ADMITTED", "source_sha":sha,
              "contract_sha256":digest(HERE/"CONTRACT.json"),
              "input_manifest_sha256":digest(HERE/"INPUT_MANIFEST.json"),
              "observed_utc":now(), "ledger_and_actions_checked":True,
              "policy_version":control["policy_version"], "route":"github_actions",
              "bounded_executor":True, "scientific_acceptance":False}
    save(OUT/"ADMISSION.json", result)
    return result

def recover_old_identity():
    root = ADAPTER/"full_run_20261115/results/LINX_BBN_IDENTITY_20261115_r3"
    manifest_path = root/"ARTIFACTS.json"
    manifest = read(manifest_path)
    if digest(manifest_path) != "15f786ad46d61ebccfe0456982ed607bd5f07619715cf1ef64d22901736d98b2":
        raise ValueError("Historical r3 artifact manifest changed")
    def checked(rel):
        item = next((x for x in manifest["files"] if x["path"] == rel), None)
        if item is None or digest(root/rel) != item["sha256"]:
            raise ValueError("Historical artifact hash mismatch: "+rel)
        return item["sha256"]
    native_sha = checked("native/RESULT.json")
    override_sha = checked("override/RESULT.json")
    calibration_sha = checked("CALIBRATION.json")
    native = read(root/"native/RESULT.json")
    override = read(root/"override/RESULT.json")
    checks = {
        "same_source_sha":native["source_sha"] == override["source_sha"] == "5183eb818d2b3c746d2e919b1f3561a08e7d1b09",
        "same_contract_sha256":native["contract_sha256"] == override["contract_sha256"],
        "same_background_sha256":native["background_sha256"] == override["background_sha256"],
        "same_reaction_order":native["reaction_order"] == override["reaction_order"],
        "same_effective_q":native["effective_q"] == override["effective_q"],
        "same_rate_table_hashes":native["table_sha256"] == override["table_sha256"],
        "same_initial_state":native["Y_initial"] == override["Y_initial"],
        "same_final_state":native["Y_final"] == override["Y_final"],
        "override_used_native_tables":override["all_tables_bitwise_native"] is True
    }
    if not all(checks.values()):
        raise ValueError("Could not reconstruct r3 adapter identity: "+repr(checks))
    receipt = {
        "status":"RECOVERED_FROM_HASHED_R3_ARM_ARTIFACTS",
        "workflow_run_id":43743586010, "source_sha":native["source_sha"],
        "historical_summary_status":"FAIL_DUE_TO_TERMINAL_NUMPY_BOOL_JSON_SERIALIZATION",
        "native_result_sha256":native_sha, "override_result_sha256":override_sha,
        "calibration_sha256":calibration_sha, "artifact_manifest_sha256":digest(manifest_path),
        "checks":checks, "native_final_abundances":native["Y_final"],
        "override_final_abundances":override["Y_final"], "scientific_acceptance":False,
        "interpretation":"Historical r3 native-table identity only; other-reaction q controls were nonzero. Not this package's all-q=0 baseline or a sensitivity result."
    }
    save(OUT/"ADAPTER_IDENTITY_RECOVERY.json", receipt)
    return receipt

def run_one(sha, role, name, root, channel=None, q=None, background=None, background_sha=None):
    task_dir = OUT/name
    cmd = [sys.executable,str(HERE/"worker.py"),"--role",role,"--root",str(root),
           "--out",str(task_dir),"--admission",str(OUT/"ADMISSION.json"),"--source-sha",sha]
    if channel is not None:
        cmd += ["--channel",channel,"--q",str(q)]
    if background is not None:
        cmd += ["--background",str(background),"--background-sha256",str(background_sha)]
    env = {k:v for k,v in os.environ.items() if not k.endswith("TOKEN") and k not in ("GH_TOKEN","GITHUB_TOKEN")}
    limits = {"wall_seconds":600,"memory_bytes":PACKAGE["budget"]["memory_bytes"]-128*1024**2,
              "output_bytes":PACKAGE["budget"]["output_bytes"]}
    sys.path.insert(0,str(IDENTITY))
    import bounded
    guard = bounded.run(cmd, OUT/(name+".log"), limits, env=env)
    if guard["exit_code"] != 0 or guard["stop"] is not None:
        raise RuntimeError(name+" failed: "+json.dumps(guard))
    result = read(task_dir/"RESULT.json")
    result["supervisor"] = guard
    save(task_dir/"RESULT.json",result)
    return result

def postprocess(results):
    channels = CONTRACT["rate_model"]["channels"]
    observables = CONTRACT["observables"]
    derivatives = {}
    for obs in observables:
        derivatives[obs] = {}
        for channel in channels:
            derivatives[obs][channel] = {}
            for h in (1.0,0.5):
                suffix = str(h).replace(".","_")
                plus = results[f"{channel}_plus_{suffix}"]["observables"][obs]
                minus = results[f"{channel}_minus_{suffix}"]["observables"][obs]
                derivatives[obs][channel][str(h)] = (math.log(plus)-math.log(minus))/(2*h)
    rho_grid = [-1.0,-0.8,-0.5,-0.3,0.0,0.3,0.5,0.8,1.0]
    expected = {
        "D_H":{"ddHe3n":"negative","ddtp":"negative"},
        "He3_H_late":{"ddHe3n":"positive","ddtp":"positive"},
        "Li7_H_late":{"ddHe3n":"positive","ddtp":"positive"},
        "Yp":None
    }
    outputs = {}
    for obs, by_channel in derivatives.items():
        a1, a2 = by_channel["ddHe3n"]["0.5"], by_channel["ddtp"]["0.5"]
        norm = a1*a1+a2*a2
        if norm <= 1e-30:
            kappa = None; qforms = {str(r):None for r in rho_grid}; ratios = {str(r):None for r in rho_grid}
        else:
            kappa = 2*a1*a2/norm
            if abs(kappa) > 1+1e-12:
                raise ValueError("Numerical kappa violates algebraic bound")
            qforms = {str(r):norm+2*r*a1*a2 for r in rho_grid}
            ratios = {str(r):math.sqrt(max(0.0,qforms[str(r)]/norm)) for r in rho_grid}
        step, by_h = {}, {}
        for h in ("1.0","0.5"):
            v1,v2 = by_channel["ddHe3n"][h],by_channel["ddtp"][h]
            den=v1*v1+v2*v2
            kh = None if den <= 1e-30 else 2*v1*v2/den
            if kh is not None and abs(kh)>1+1e-12:
                raise ValueError("Step-specific kappa violates bounds")
            by_h[h] = {
                "kappa":kh,
                "independent_quadratic_form":den,
                "correlated_quadratic_form":{str(r):(None if kh is None else den+2*r*v1*v2) for r in rho_grid},
                "sigma_ratio":{str(r):(None if kh is None else math.sqrt(max(0.0,1+kh*r))) for r in rho_grid}
            }
        for channel in channels:
            x,y = by_channel[channel]["1.0"],by_channel[channel]["0.5"]
            scale = max(abs(x),abs(y))
            if scale < 1e-8:
                step[channel] = {"status":"NEAR_ZERO_RESPONSE","a_h1":x,"a_h0_5":y}
            else:
                gap = abs(x-y)/scale
                step[channel] = {"status":"STEP_CONVERGED" if gap<0.01 else "STEP_NOT_CONVERGED",
                                 "relative_discrepancy":gap,"a_h1":x,"a_h0_5":y}
        signs = {c:("negative" if by_channel[c]["0.5"]<0 else "positive" if by_channel[c]["0.5"]>0 else "zero") for c in channels}
        if expected[obs] is None:
            hypothesis = {"status":"NO_PREREGISTERED_SIGN","observed":signs}
        else:
            matches = {c:signs[c]==expected[obs][c] for c in channels}
            hypothesis = {"status":"MATCH" if all(matches.values()) else "DEVIATES_FROM_DIRECTIONAL_HYPOTHESIS",
                          "expected":expected[obs],"observed":signs,"matches":matches,
                          "note":"Diagnostic network-flow hypothesis; not a software acceptance gate."}
        outputs[obs] = {
            "baseline_observable":results["baseline"]["observables"][obs],
            "derivatives":by_channel,"a_vector_h0_5":[a1,a2],"kappa_h0_5":kappa,
            "by_step":by_h,"absolute_log_variance_contribution_per_unit_marginal_variance":norm,
            "correlated_quadratic_form_h0_5":qforms,"sigma_corr_over_sigma_indep_delta_method":ratios,
            "rho_grid":rho_grid,"step_diagnostics":step,"derivative_signs_h0_5":signs,
            "directional_hypothesis":hypothesis
        }
    return {"schema":"vm-lab-s3-dd-response-result-v1","id":PACKAGE["id"],"status":"COMPUTE_COMPLETE",
            "source_sha":os.environ["SOURCE_SHA"],"integrations":9,"results":outputs,
            "rho_status":"UNMEASURED_PARAMETER; results are functions of rho, not a measured correlated covariance",
            "propagation_status":"FIRST_ORDER_DELTA_METHOD_ONLY","scientific_acceptance":False,
            "scope_guard":"No nonlinear MC, GP posterior, experimental rho determination, observational likelihood, BH1 or S2 result."}

def finalize_artifacts():
    files=[]
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name!="ARTIFACTS.json":
            files.append({"path":str(p.relative_to(OUT)),"sha256":digest(p),"bytes":p.stat().st_size})
    if sum(x["bytes"] for x in files)>PACKAGE["budget"]["output_bytes"]:
        raise ValueError("Output byte budget exceeded")
    save(OUT/"ARTIFACTS.json",{"package_id":PACKAGE["id"],"source_sha":os.environ["SOURCE_SHA"],"files":files})

def publish():
    branch=PACKAGE["publication_branch"]
    git("fetch","origin",branch)
    remote=git("ls-remote","origin","refs/heads/"+branch).split()[0]
    if remote!=os.environ["SOURCE_SHA"]:
        raise RuntimeError("Publication branch moved; keep workflow artifact, do not overwrite")
    subprocess.run(["git","add","-f",str(OUT_REL)],cwd=ROOT,check=True)
    if not git("diff","--cached","--name-only"):
        return remote
    subprocess.run(["git","commit","-m",f"Publish {PACKAGE['id']} local D+D response results"],cwd=ROOT,check=True)
    sha=git("rev-parse","HEAD")
    pushed=subprocess.run(["git","push","origin","HEAD:refs/heads/"+branch],cwd=ROOT)
    if pushed.returncode and git("ls-remote","origin","refs/heads/"+branch).split()[0]!=sha:
        raise RuntimeError("Publication push not confirmed; reconcile manually")
    return sha

def close_reservation(reservation, conclusion, publication_sha):
    for _ in range(3):
        ledger, expected=admit.read_ledger()
        updated=finish.close(ledger,reservation,conclusion,publication_sha)
        row=next(x for x in updated["packages"] if x["id"]==PACKAGE["id"])
        row.update(result_sha=publication_sha,
                   summary_sha256=digest(OUT/"SUMMARY.json") if (OUT/"SUMMARY.json").exists() else None,
                   artifacts_sha256=digest(OUT/"ARTIFACTS.json") if (OUT/"ARTIFACTS.json").exists() else None,
                   processes_exited=True)
        if admit.write_ledger(updated,expected):
            return
    raise RuntimeError("Ledger CAS close failed; do not resubmit")

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    source_sha=validate_source()
    admission=reserve(source_sha)
    reservation=admission["reservation"]
    conclusion="failure"; publication_sha=source_sha
    started=time.perf_counter()
    try:
        recover_old_identity()
        roots=Path(os.environ["RUNNER_TEMP"])/"linx-dd-response-roots"
        subprocess.run([sys.executable,str(ADAPTER/"identity/materialize_roots.py"),str(roots)],cwd=ROOT,check=True)
        baseline=run_one(source_sha,"baseline","baseline",roots/"pristine")
        results={"baseline":baseline}
        wall=float(baseline["supervisor"]["wall_seconds"])
        forecast={"measured_baseline_wall_seconds":wall,"remaining_integrations":8,
                  "remaining_wall_forecast_seconds":8*wall,"per_integration_hard_cap_seconds":600,
                  "forecast_recorded_before_perturbations":True,
                  "within_5400_second_compute_cap":9*wall<=5400,"created_utc":now()}
        save(OUT/"FORECAST.json",forecast)
        if wall>600 or 9*wall>5400:
            raise RuntimeError("Measured baseline forecast exceeds compute envelope; no perturbations started")
        bg=OUT/"baseline"/"background.npz"; bg_sha=baseline["background_sha256"]
        for channel in CONTRACT["rate_model"]["channels"]:
            for h in (1.0,0.5):
                suffix=str(h).replace(".","_")
                for sign in (-1.0,1.0):
                    q=sign*h
                    direction="minus" if sign<0 else "plus"
                    name=f"{channel}_{direction}_{suffix}"
                    results[name]=run_one(source_sha,"perturb",name,roots/"override",
                                           channel=channel,q=q,background=bg,background_sha=bg_sha)
        summary=postprocess(results)
        summary.update(wall_seconds_package=time.perf_counter()-started,forecast=forecast)
        save(OUT/"SUMMARY.json",summary)
        conclusion="success"
    except Exception:
        save(OUT/"FAILURE.json",{"status":"FAIL","traceback":traceback.format_exc(),
                                 "source_sha":source_sha,"scientific_acceptance":False,"automatic_retry":False})
        raise
    finally:
        try:
            finalize_artifacts()
            publication_sha=publish()
        except Exception:
            conclusion="failure"
            raise
        finally:
            close_reservation(reservation,conclusion,publication_sha)

if __name__=="__main__":
    main()
