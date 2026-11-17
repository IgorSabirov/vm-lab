#!/usr/bin/env python3
"""Read this entire file from GitHub and execute it in Chat's Python tool.
No network, git client, API key, separate download, or installation is needed.
Embedded files preserve source commit d24f1577c070595aa791b3b2dbd875d20b71d34b.
GitHub publication is performed afterwards through Chat's GitHub tools.
--check-bundle verifies/examines embedded bytes without running the experiment.
"""
from pathlib import Path
from datetime import datetime, timezone
import ast, base64, hashlib, json, os, platform, shutil, subprocess, sys, time, zlib

SOURCE_COMMIT = "d24f1577c070595aa791b3b2dbd875d20b71d34b"
PUBLISH_BRANCH = "work/chat-add-c1-handoff-20261117"
PAYLOAD = (
    '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'
    '3qDn2Z1gPGAdy+oHNnt2f///AXIPnyE='
)

def load_sources():
    files = json.loads(zlib.decompress(base64.b64decode(PAYLOAD)))
    for name, item in files.items():
        assert Path(name).name == name
        data = item["content"].encode("utf-8")
        blob = hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        assert blob == item["git_blob_sha"], "Git blob mismatch: "+name
        if name.endswith(".py"):
            ast.parse(item["content"], filename=name)
    expected = {}
    for line in files["SOURCE_MANIFEST.sha256"]["content"].splitlines():
        digest, name = line.split()
        assert hashlib.sha256(files[name]["content"].encode()).hexdigest() == digest, name
        expected[name] = digest
    return files, expected

def main(check_only=False):
    files, expected = load_sources()
    if check_only:
        print(json.dumps({"bundle_files": len(files), "git_blobs": "MATCH", "source_sha256": "MATCH", "python_syntax": "VALID", "experiment_executed": False}))
        return
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = Path.cwd()/"chat_add_c1_runs"/run_id
    out.mkdir(parents=True, exist_ok=False)
    for name in [*expected, "SOURCE_MANIFEST.sha256"]:
        (out/name).write_bytes(files[name]["content"].encode("utf-8"))
    def save(name, value):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    receipt = {
        "run_id": run_id, "source_commit": SOURCE_COMMIT,
        "execution_location": "ordinary_chat_python_sandbox",
        "owner_instruction": "Запуск в обычном Chat; вся передача через GitHub.",
        "source_sha256": expected, "historical_plan_kept_unchanged": True,
        "billing_status": "NOT_MEASURED",
        "python": sys.version, "platform": platform.platform(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else None,
        "disk_free_bytes_before": shutil.disk_usage(out).free,
        "publication_status": "PENDING",
    }
    save("RECEIPT.json", receipt)
    def invoke(flag, logfile):
        started = time.perf_counter()
        with (out/logfile).open("x", encoding="utf-8") as log:
            proc = subprocess.run([sys.executable,str(out/"run_block1.py"),flag],cwd=out,stdout=log,stderr=subprocess.STDOUT)
        return {"exit_code": proc.returncode,"process_wall_seconds":time.perf_counter()-started}
    try:
        receipt["calibration"] = invoke("--calibrate","calibration.log")
        save("RECEIPT.json",receipt)
        assert receipt["calibration"]["exit_code"] == 0, "Calibration failed; see calibration.log"
        forecast = json.loads((out/"PREFLIGHT.json").read_text())
        assert forecast["main_allowed_by_checks"] and forecast["planned_main_inputs"] == 6032
        print(json.dumps({"before_main_forecast_seconds":forecast["forecast_seconds"],"range_seconds":forecast["range_seconds"],"planned_cases":6032}),flush=True)
        receipt["main"] = invoke("--run","run.log")
        save("RECEIPT.json",receipt)
        actual = json.loads((out/"RESULTS.json").read_text())
        baseline = json.loads(files["RESULTS.json"]["content"])
        stable = ["case_counts","total_case_inputs","total_input_vertices","corpus_sha256","metrics","unexpected_failures","status","scope","source_sha256","negative_validation_controls","P_raw"]
        comparison = {k:actual.get(k)==baseline.get(k) for k in stable}
        comparison["WITNESSES"] = (out/"WITNESSES.json").exists() and json.loads((out/"WITNESSES.json").read_text())==json.loads(files["WITNESSES.json"]["content"])
        comparison["source_bytes_after"] = all(hashlib.sha256((out/name).read_bytes()).hexdigest()==digest for name,digest in expected.items())
        comparison["main_exit_zero"] = receipt["main"]["exit_code"]==0
        status = "MATCH" if all(comparison.values()) else "MISMATCH"
        save("COMPARISON.json",{"reference_commit":SOURCE_COMMIT,"checks":comparison,"reproduction_status":status,"ignored_reference_fields":"timestamps, timings, environment, RSS, runtime_plan_actual"})
        receipt["reproduction_status"] = status
        receipt["runtime_plan_actual"] = actual.get("runtime_plan_actual")
        report = ["# ADD C1: повтор блока 1 в Chat", "", "Источник: `"+SOURCE_COMMIT+"`.",
            "Родители: R126 → R130 → ADD_C1_AUTHOR_REPRO_20261116; задача #83.",
            "Сверка детерминированных полей и witnesses: **"+status+"**.",
            "Входов: "+str(actual.get("total_case_inputs"))+"; хеш корпуса: `"+str(actual.get("corpus_sha256"))+"`.",
            "Статус движка: "+str(actual.get("status"))+".",
            "Прогноз/факт вычисления: `"+json.dumps(actual.get("runtime_plan_actual"))+"`.",
            "Процессное wall time основного запуска: "+str(receipt["main"]["process_wall_seconds"])+" с.",
            "Калибровка, подготовка, чтение GitHub и публикация учитываются отдельно.",
            "Нарушения по версиям: `"+json.dumps({v:{k:m['failed'] for k,m in rows.items() if m['failed']} for v,rows in actual['metrics'].items()})+"`.",
            "P_raw: `"+json.dumps([{k:r[k] for k in ('L','edge_count','status')} for r in actual['P_raw']])+"`.",
            "Это воспроизведение конечного блока; Lemma 1, асимптотика и энтропийные теоремы не проверялись.",
            "Списание кредитов не измерено; успешное вычисление не доказывает бесплатность.",
            "Публикация: PENDING. Проверяется отдельно по readback итогового GitHub commit."]
        (out/"REPORT.md").write_text("\n\n".join(report)+"\n",encoding="utf-8")
    except Exception as exc:
        receipt["execution_error"] = {"type":type(exc).__name__,"message":str(exc)}
        raise
    finally:
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["disk_free_bytes_after"] = shutil.disk_usage(out).free
        save("RECEIPT.json",receipt)
        artifact_paths = sorted(p for p in out.iterdir() if p.is_file())
        manifest = "".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.name+"\n" for p in artifact_paths)
        (out/"MANIFEST.sha256").write_text(manifest,encoding="utf-8")
        prefix = "analysis/ADD_C1_CHAT_REPRO_20261117/"+run_id+"/"
        export = {"repository":"IgorSabirov/vm-lab","branch":PUBLISH_BRANCH,"prefix":prefix,
                  "files":[{"path":prefix+p.name,"content":p.read_text(encoding="utf-8")} for p in sorted(out.iterdir()) if p.is_file()]}
        export_path = out.parent/(run_id+"_GITHUB_EXPORT.json")
        export_path.write_text(json.dumps(export,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({"output_directory":str(out),"github_export":str(export_path),"reproduction_status":receipt.get("reproduction_status"),"execution_error":receipt.get("execution_error"),"publication_status":"PENDING"},ensure_ascii=False),flush=True)

if __name__ == "__main__":
    main(check_only="--check-bundle" in sys.argv)
