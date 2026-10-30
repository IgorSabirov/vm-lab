#!/usr/bin/env python3
"""Small, text-only Copilot CLI bridge. See ../COPILOT.md before first use.

Credentials stay in the CLI's own user profile, outside this repository.
Every operation starts a fresh process with the current environment's network
configuration. The bridge never changes proxy, TLS, or network policy settings.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request


CLI_VERSION = "1.0.105"
AUTH_ENV = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
TOKEN_RE = re.compile(r"(?:github_pat_|gh[oUpusr]_)[A-Za-z0-9_]+")
MAX_PROMPT_BYTES = 128 * 1024


def redact(text):
    text = TOKEN_RE.sub("[REDACTED_TOKEN]", str(text))
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1[REDACTED]", text)
    return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)


def child_env():
    # No snapshot of HTTP(S)_PROXY, NO_PROXY or CA paths is persisted.
    env = dict(os.environ)
    # This bridge deliberately uses the saved CLI login. An unrelated GH_TOKEN
    # must not silently override it. Environment-token auth is not implemented.
    for key in AUTH_ENV:
        env.pop(key, None)
    return env


def prefix():
    return Path.home() / ".cache" / "vm-lab" / "copilot-cli" / CLI_VERSION


def cli_path(explicit=None):
    selected = explicit or os.environ.get("VM_LAB_COPILOT_CLI")
    if selected:
        if not Path(selected).is_file():
            raise RuntimeError("CLI_MISSING: explicit executable does not exist")
        return str(Path(selected).absolute())
    candidates = [str(prefix() / "node_modules" / ".bin" / "copilot"), shutil.which("copilot")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).absolute())
    raise RuntimeError("CLI_MISSING: run this script with the install command")


def terminate(process):
    # Each captured command owns its process group, including CLI children.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.communicate()


def captured(argv, timeout):
    started = time.monotonic()
    process = subprocess.Popen(argv, env=child_env(), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    timed_out = False
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        out, err = terminate(process)
    except BaseException:
        terminate(process)
        raise
    return {"returncode": process.returncode, "stdout": redact(out),
            "stderr": redact(err), "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def checked_version(cli):
    result = captured([cli, "--no-auto-update", "--version"], 20)
    match = re.search(r"GitHub Copilot CLI (\d+\.\d+\.\d+)", result["stdout"])
    if result["returncode"] != 0 or not match:
        raise RuntimeError("CLI_VERSION_UNREADABLE: " + result["stderr"])
    if match.group(1) != CLI_VERSION:
        raise RuntimeError(f"CLI_VERSION_MISMATCH: expected {CLI_VERSION}, got {match.group(1)}")
    return match.group(1)


def failure_status(result):
    if result.get("timed_out"):
        return "TIMEOUT"
    text = (result.get("stderr", "") + "\n" + result.get("stdout", "")).lower()
    if "blocked by policy" in text or "network access denied" in text:
        return "POLICY_BLOCKED"
    if any(term in text for term in ("quota", "rate limit", "429", "insufficient credits", "credits exhausted")):
        return "LIMIT_REACHED"
    if any(term in text for term in ("401", "unauthorized", "not logged in", "not authenticated", "token expired", "please sign in", "please log in")):
        return "AUTH_REQUIRED"
    return "REQUEST_FAILED"


def prompt_command(cli, cwd, prompt):
    return [cli, "-C", str(cwd), "--model", "auto", "--max-ai-credits", "30",
            "--disable-builtin-mcps", "--available-tools",
            "--deny-tool", "shell", "--deny-tool", "write", "--deny-tool", "url",
            "--disallow-temp-dir", "--no-custom-instructions", "--no-ask-user",
            "--no-auto-update", "--disable-client-telemetry", "--log-level", "warning",
            "-s", "-p", prompt]


def request(cli, prompt, timeout, expected=None):
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("PROMPT_TOO_LARGE: limit is 128 KiB")
    if TOKEN_RE.search(prompt):
        raise ValueError("POSSIBLE_CREDENTIAL_IN_PROMPT: refusing to transmit")
    version = checked_version(cli)
    # Never give a diagnostic query implicit access to the working repository.
    with tempfile.TemporaryDirectory(prefix="vm-lab-copilot-") as cwd:
        result = captured(prompt_command(cli, cwd, prompt), timeout)
    answer = result.pop("stdout").strip()
    error = result.pop("stderr").strip()
    evidence = dict(result, stdout=answer, stderr=error)
    if result["returncode"] != 0 or result["timed_out"]:
        status = failure_status(evidence)
    elif not answer:
        status = "EMPTY_RESPONSE"
    elif expected is not None and answer != expected:
        status = "UNEXPECTED_RESPONSE"
    else:
        status = "OK"
    return dict(result, status=status, cli_version=version, answer=answer,
                error=error, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())


def probe(url):
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "vm-lab-copilot-doctor"})
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
        return {"url": url, "http_status": status, "reachable": True,
                "elapsed_seconds": round(time.monotonic() - started, 3)}
    except urllib.error.HTTPError as error:
        # 401/403 is a response, but is not proof of successful authentication.
        return {"url": url, "http_status": error.code, "reachable": True,
                "elapsed_seconds": round(time.monotonic() - started, 3)}
    except Exception as error:
        return {"url": url, "reachable": False, "error": redact(error),
                "elapsed_seconds": round(time.monotonic() - started, 3)}


def doctor(explicit, offline):
    try:
        cli = cli_path(explicit)
        version = checked_version(cli)
        cli_state = {"path": cli, "version": version, "status": "OK"}
    except RuntimeError as error:
        cli_state = {"status": "UNAVAILABLE", "error": str(error)}
    config = config_dir() / "config.json"
    result = {"status": "DIAGNOSTIC_ONLY", "cli": cli_state,
              "saved_config_present": config.is_file(),
              "auth_environment_names_ignored": [key for key in AUTH_ENV if os.environ.get(key)],
              "note": "Neither a config file nor HTTP 200 proves Copilot access; run ping."}
    if not offline:
        result["network"] = [probe("https://github.com/login/device"), probe("https://api.github.com/")]
    return result


def config_dir():
    custom = os.environ.get("COPILOT_HOME")
    return Path(custom).expanduser().absolute() if custom else Path.home() / ".copilot"


def harden_config():
    directory = config_dir()
    config = directory / "config.json"
    if directory.is_symlink() or config.is_symlink():
        raise RuntimeError("REFUSING_SYMLINKED_AUTH_CONFIG")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    if config.exists():
        config.chmod(0o600)


def login(cli):
    checked_version(cli)
    harden_config()
    print("Keep this command and the current assistant turn alive until login finishes.\n"
          "Show the device code in commentary; poll within the same turn.\n"
          "Without a system keychain the CLI may offer an unencrypted config file.\n"
          "The directory is owner-only; accept that option only in a trusted environment.",
          file=sys.stderr, flush=True)
    # Interactive stdin/stdout intentionally remain attached to the PTY. No code
    # or OAuth token is intercepted, serialized, or copied into this repository.
    try:
        result = subprocess.run([cli, "login", "--device-code"], env=child_env())
    finally:
        harden_config()
    return {"status": "LOGIN_FINISHED_RUN_PING" if result.returncode == 0 else "LOGIN_FAILED",
            "returncode": result.returncode}


def install():
    if not shutil.which("npm"):
        raise RuntimeError("NPM_MISSING: install Node.js 22+ and npm using an approved runtime")
    target = prefix()
    binary = target / "node_modules" / ".bin" / "copilot"
    if binary.is_file():
        return {"status": "OK", "path": str(binary), "cli_version": checked_version(str(binary)), "already_installed": True}
    result = captured(["npm", "install", "--prefix", str(target), "--no-audit", "--no-fund",
                       f"@github/copilot@{CLI_VERSION}"], 180)
    if result["returncode"] != 0:
        return dict(result, status=failure_status(result))
    return {"status": "OK", "path": str(binary), "cli_version": checked_version(str(binary)),
            "elapsed_seconds": result["elapsed_seconds"], "already_installed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", help="Explicit pinned CLI executable")
    parser.add_argument("--timeout", type=float, default=None,
                        help="Optional request timeout in seconds; default: wait until completion")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("install")
    diag = commands.add_parser("doctor")
    diag.add_argument("--offline", action="store_true")
    commands.add_parser("login")
    commands.add_parser("ping")
    ask = commands.add_parser("ask")
    ask.add_argument("--prompt-file", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error("--timeout must be a positive finite number")
    try:
        if args.operation == "install":
            result = install()
        elif args.operation == "doctor":
            result = doctor(args.cli, args.offline)
        elif args.operation == "login":
            result = login(cli_path(args.cli))
        else:
            expected = None
            if args.operation == "ping":
                expected = "COPILOT_OK_" + secrets.token_hex(8)
                prompt = f"Connection check only. Do not use tools or read files. Reply with exactly this single line: {expected}"
            else:
                if args.prompt_file.stat().st_size > MAX_PROMPT_BYTES:
                    raise ValueError("PROMPT_TOO_LARGE: limit is 128 KiB")
                prompt = args.prompt_file.read_text(encoding="utf-8")
            result = request(cli_path(args.cli), prompt, args.timeout, expected)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        result = {"status": "LOCAL_ERROR", "error": redact(error)}
    result.update(schema="vm-lab/copilot-bridge/v1", operation=args.operation,
                  timestamp_utc=datetime.now(timezone.utc).isoformat())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("OK", "DIAGNOSTIC_ONLY", "LOGIN_FINISHED_RUN_PING") else 1


if __name__ == "__main__":
    sys.exit(main())
