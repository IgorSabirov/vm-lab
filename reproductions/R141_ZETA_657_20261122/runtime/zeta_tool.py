"""Restricted MCP bridge: only start the fixed R141 replay or poll it."""
import json, os, subprocess, sys, time
from pathlib import Path

for key in list(os.environ):
    if "TOKEN" in key or "SECRET" in key or key.startswith(("COPILOT_", "GH_AW_")):
        del os.environ[key]
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)
proc = None
streams = []

def status(wait=False):
    if proc is None:
        return {"status": "NOT_STARTED"}
    if wait and proc.poll() is None:
        try: proc.wait(timeout=15)
        except subprocess.TimeoutExpired: pass
    receipt = OUT / "RUNNER_RECEIPT.json"
    value = json.loads(receipt.read_text()) if receipt.exists() else {}
    return {"status": value.get("status", "RUNNING"), "exit_code": proc.poll(),
            "elapsed_seconds": value.get("elapsed_seconds"), "error": value.get("error")}

def execute():
    global proc
    if proc is not None or (OUT / "STARTED.json").exists():
        return {"duplicate_refused": True, **status()}
    (OUT / "STARTED.json").write_text(json.dumps({"tool":"zeta.execute","pid_pending":True})+"\n")
    so = (OUT / "CALCULATION.stdout.log").open("w")
    se = (OUT / "CALCULATION.stderr.log").open("w")
    streams.extend([so,se])
    proc = subprocess.Popen([sys.executable, str(ROOT/"reproduce.py")], cwd=ROOT,
                            env=dict(os.environ), stdout=so, stderr=se, start_new_session=True)
    (OUT / "STARTED.json").write_text(json.dumps({"tool":"zeta.execute","pid":proc.pid,
        "command":[sys.executable,"reproduce.py"],"credentials_removed":True})+"\n")
    return status(wait=True)

def dispatch(req):
    method=req.get("method")
    if method=="initialize":
        return {"protocolVersion":req["params"]["protocolVersion"],"capabilities":{"tools":{}},
                "serverInfo":{"name":"r141-fixed-zeta-replay","version":"1.0"}}
    if method=="ping": return {}
    if method=="tools/list":
        return {"tools":[
          {"name":"execute","description":"Run the one fixed owner-authorized R141 657-zero replay; no arguments.",
           "inputSchema":{"type":"object","properties":{},"additionalProperties":False}},
          {"name":"status","description":"Wait up to 15 seconds and report the same R141 replay process; no arguments.",
           "inputSchema":{"type":"object","properties":{},"additionalProperties":False}}]}
    if method=="tools/call":
        p=req.get("params",{})
        if p.get("arguments",{}) or p.get("name") not in ("execute","status"):
            return {"isError":True,"content":[{"type":"text","text":"Unsupported operation/arguments; nothing executed."}]}
        name=p["name"]
        value=execute() if name=="execute" else status(wait=True)
        with (OUT/"MCP_CALLS.jsonl").open("a") as f: f.write(json.dumps({"tool":name,"result":value})+"\n")
        return {"content":[{"type":"text","text":json.dumps(value)}]}
    raise ValueError("Unsupported MCP method")

for line in sys.stdin:
    req=json.loads(line)
    if "id" not in req: continue
    try: resp={"jsonrpc":"2.0","id":req["id"],"result":dispatch(req)}
    except Exception as e: resp={"jsonrpc":"2.0","id":req["id"],"error":{"code":-32603,"message":str(e)}}
    print(json.dumps(resp),flush=True)
