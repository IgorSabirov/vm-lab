#!/usr/bin/env python3
"""Publish only this replay's outputs, preserving the complete existing tree."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "analysis/MIRROR_PARTNERS_REVIEW_20261128/galois_bridge"
EXACT = {
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/REPORT.md",
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/README.md",
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/SOURCE_MAP.json",
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/FILES.sha256",
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/checks/FILES_7aae9af5.sha256",
    "analysis/MIRROR_PARTNERS_REVIEW_20261128/r140_bridge/REPORT.md",
    "analysis/NOW_RESULTS_SYNTHESIS_20261106/R141.md",
    "analysis/NOW_RESULTS_SYNTHESIS_20261106/R146.md",
    "analysis/NOW_RESULTS_SYNTHESIS_20261106/R150.md",
    "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json",
    "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.md",
    "analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md",
    "analysis/REGISTRY_LINKS/INDEX.json",
    "analysis/REGISTRY_LINKS/INDEX.md",
    "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md",
    "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.json",
}
BRANCH = "research/mirror-partners-review-20261128"

def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    if repo != "IgorSabirov/vm-lab":
        raise AssertionError("Unexpected repository")
    token = os.environ["GITHUB_TOKEN"]
    def api(path, data=None, method=None):
        payload = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request("https://api.github.com/repos/" + repo + "/" + path,
            data=payload, method=method,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json", "User-Agent": "vm-lab-galois-h6-publisher"})
        with urllib.request.urlopen(req) as response:
            return json.load(response)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    current = api("git/ref/heads/" + BRANCH)["object"]["sha"]
    if current != source:
        raise AssertionError("Branch advanced; results retained as artifact. Publication must reconcile the new head.")
    tracked = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).splitlines()
    new = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
    candidates = sorted(set(tracked + new))
    integration_ok = os.environ.get("INTEGRATION_OUTCOME") == "success"
    if not integration_ok:
        evidence_prefix = PACKAGE + "/runs/" + os.environ["GITHUB_RUN_ID"] + "/"
        candidates = [p for p in candidates if p.startswith(evidence_prefix)]
    paths = []
    for path in candidates:
        if "__pycache__" in path or path.endswith(".pyc"):
            continue
        allowed = path in EXACT or path.startswith(PACKAGE + "/runs/") or path in {PACKAGE + "/REPORT.md", PACKAGE + "/LATEST.json"}
        if path.startswith("decisions/") and path.endswith(".md"):
            allowed = True
        if not allowed:
            raise AssertionError("Unexpected changed path: " + path)
        if not (ROOT / path).is_file():
            raise AssertionError("Deletion is forbidden in this publisher: " + path)
        paths.append(path)
    if not paths:
        print("No result changes to publish")
        return
    base_tree = api("git/commits/" + source)["tree"]["sha"]
    entries = []
    for path in paths:
        content = (ROOT / path).read_text()
        sha = api("git/blobs", {"content": content, "encoding": "utf-8"}, "POST")["sha"]
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
    tree = api("git/trees", {"base_tree": base_tree, "tree": entries}, "POST")["sha"]
    run = os.environ["GITHUB_RUN_ID"]
    commit = api("git/commits", {
        "message": "Verify Galois and full mirror register bridge; preserve run " + run,
        "tree": tree, "parents": [source],
    }, "POST")["sha"]
    api("git/refs/heads/" + BRANCH, {"sha": commit, "force": False}, "PATCH")
    print(json.dumps({"published_commit": commit, "source_commit": source,
                      "files": paths, "deleted_files": 0, "base_tree": base_tree}))
if __name__ == "__main__":
    main()
