#!/usr/bin/env python3
"""Materialize existing registry inputs through Git sparse checkout; no science."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "analysis/MIRROR_PARTNERS_REVIEW_20261128/r140_bridge"
MAIN = "analysis/NOW_RESULTS_SYNTHESIS_20261106/RESULTS_REGISTER.json"
EXT = "analysis/FOUR_CANDIDATE_INTEGRATION_20261108/SOURCE_INDEX.json"

def main():
    tracked = set(subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT, text=True).splitlines())
    register = json.loads((ROOT / MAIN).read_text())
    manifest = json.loads((ROOT / PACKAGE / "SOURCE_MANIFEST.json").read_text())
    external = json.loads((ROOT / EXT).read_text())
    needed = {
        MAIN, MAIN.replace(".json", ".md"),
        "analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.json",
        "analysis/NOW_RESULTS_SYNTHESIS_20261106/OPEN_QUESTIONS.md",
        "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.md",
        "analysis/FOUNDATIONS_LITERATURE_20261103/PREMISES_CURRENT.json",
        EXT, "tools/registry_links.py", "requirements-ci.txt",
        "analysis/REGISTRY_LINKS/INDEX.json", "analysis/REGISTRY_LINKS/INDEX.md",
        "analysis/ADD_NEIGHBOR_SYNTHESIS_20261117/verify.py",
        "analysis/R140_HAAR_SORKIN/verify.py",
        "analysis/R140_HAAR_SORKIN/HISTORIES.json",
        "analysis/R140_HAAR_SORKIN/REPORT.md",
        "analysis/NOW_RESULTS_SYNTHESIS_20261106/R140.md",
        "analysis/MIRROR_PARTNERS_REVIEW_20261128/REPORT.md",
        "analysis/MIRROR_PARTNERS_REVIEW_20261128/README.md",
        "analysis/MIRROR_PARTNERS_REVIEW_20261128/FILES.sha256",
    }
    needed.update(row["path"] for row in manifest["inputs"])
    needed.add("analysis/MIRROR_PARTNERS_REVIEW_20261128/SOURCE_MAP.json")
    items = register["results"] + register.get("external_reviews", []) + external.get("external_integrations", [])
    for item in items:
        needed.update(item.get("managed_sources", []))
        if item.get("contract"): needed.add(item["contract"])
    if register.get("model_atlas"): needed.add(register["model_atlas"])
    for path in tracked:
        if path.startswith(PACKAGE + "/") or path.startswith("decisions/") or path.startswith(".github/workflows/mirror-r140-bridge"):
            needed.add(path)
    for path in tracked:
        if path.startswith("decisions/") and path.endswith(".json"):
            data = json.loads((ROOT / path).read_text())
            reference = data.get("ratification", {}).get("reference")
            if reference: needed.add(reference)
    patterns = "".join("/" + path + "\n" for path in sorted(needed & tracked))
    subprocess.run(["git", "sparse-checkout", "set", "--no-cone", "--stdin"], cwd=ROOT,
                   input=patterns, text=True, check=True)
    print(json.dumps({"materialized_registry_and_code_paths": len(needed & tracked)}))
if __name__ == "__main__":
    main()
