"""Invoke native Copilot exactly as in the successful R130 run, via fixed MCP tools."""
import hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
WORK=Path(os.environ["RUNNER_TEMP"])/"r141-zeta-task"
WORK.mkdir(parents=True,exist_ok=True)
for name in ("reproduce.py","zeta_tool.py"):
    shutil.copy2(HERE/name,WORK/name)
out=WORK/"results"
out.mkdir(exist_ok=True)
token=os.environ.get("COPILOT_GITHUB_TOKEN","")
if not token: raise RuntimeError("AUTH_MISSING: COPILOT_GITHUB_TOKEN")
env={k:v for k,v in os.environ.items() if not k.startswith(("COPILOT_","GH_AW_")) and k not in ("GH_TOKEN","GITHUB_TOKEN")}
env.update(COPILOT_GITHUB_TOKEN=token,COPILOT_HOME=str(Path(os.environ["RUNNER_TEMP"])/"r141-copilot-profile"))
prompt="""Owner-authorized complete R141 numerical reproduction. Work only through the dedicated zeta MCP server.
Call zeta.execute exactly once with no arguments. It runs the fixed, complete 657-zero mpmath replay, Siegel-Z sign checks, indexed spot checks, Hadamard partial products, Gaussian sums and separate CCC+TL clock integral. If status is RUNNING, call zeta.status repeatedly until exit_code is not null. Do not stop after the first response. Do not ask questions, change code, invoke shell, browse, edit, delegate or launch another process. Report actual status, exit code, root count, threshold crossings and any failed check. All raw outputs and logs are saved by the fixed tool; the trusted workflow publishes them."""
config={"mcpServers":{"zeta":{"command":sys.executable,"args":[str(WORK/"zeta_tool.py")],"tools":["execute","status"]}}}
argv=[shutil.which("copilot"),"-C",str(WORK),"--model","auto","--max-ai-credits","30",
      "--disable-builtin-mcps","--additional-mcp-config",json.dumps(config),
      "--excluded-tools","bash","powershell","edit","create","apply_patch","view","glob","grep",
      "web_fetch","task","ask_user","skill","read_bash","write_bash","list_bash","stop_bash",
      "--allow-tool","zeta(execute)","--allow-tool","zeta(status)",
      "--deny-tool","shell","--deny-tool","write","--deny-tool","url",
      "--no-custom-instructions","--no-ask-user","--no-auto-update","--disable-client-telemetry",
      "--log-level","warning","-s"]
started=time.perf_counter()
p=subprocess.run(argv,cwd=WORK,env=env,input=prompt,capture_output=True,text=True)
def redact(s):
    s=s.replace(token,"[REDACTED]") if token else s
    return re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+","[REDACTED]",s)
(out/"COPILOT_RESPONSE.txt").write_text(redact(p.stdout),encoding="utf-8")
(out/"COPILOT_STDERR.txt").write_text(redact(p.stderr),encoding="utf-8")
(out/"COPILOT_PROMPT.txt").write_text(prompt,encoding="utf-8")
receipt={"status":"COPILOT_SESSION_FINISHED","cli_version":"1.0.103","model":"native auto",
 "returncode":p.returncode,"session_seconds":time.perf_counter()-started,"max_ai_credits":30,
 "tools":["zeta.execute","zeta.status"],"shell_access":False,"arbitrary_arguments":False,
 "source_sha":os.environ.get("GITHUB_SHA"),"run_id":os.environ.get("GITHUB_RUN_ID")}
if (out/"STARTED.json").exists():
    pid=json.loads((out/"STARTED.json").read_text()).get("pid")
    while pid:
        rec=out/"CHECKS.json"
        if rec.exists(): break
        try: os.kill(pid,0)
        except ProcessLookupError: break
        time.sleep(2)
runner_status="NOT_STARTED"
if (out/"CHECKS.json").exists():
    runner_status=json.loads((out/"CHECKS.json").read_text()).get("status","UNKNOWN")
elif (out/"FAILURE.json").exists():
    runner_status="FAILED"
receipt["calculation_status"]=runner_status
(out/"COPILOT_RECEIPT.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
files=sorted(x for x in out.rglob("*") if x.is_file() and x.name!="MANIFEST.sha256")
(out/"MANIFEST.sha256").write_text("".join(hashlib.sha256(x.read_bytes()).hexdigest()+"  "+x.relative_to(out).as_posix()+"\n" for x in files))
print(json.dumps(receipt),flush=True)
print(redact(p.stdout),flush=True)
print(redact(p.stderr),file=sys.stderr,flush=True)
if p.returncode or runner_status not in ("PASS_NUMERICAL_REPLAY","FAILED"):
    raise SystemExit("COPILOT_SESSION_OR_CALCULATION_NOT_CONFIRMED")
if runner_status!="PASS_NUMERICAL_REPLAY": raise SystemExit(1)
