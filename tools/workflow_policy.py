#!/usr/bin/env python3
"""Repository-specific workflow policy; not a general security audit."""
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_GUARD = "github.repository == 'IgorSabirov/vm-lab'"

# Scientific execution stays bound to its declared request and repository.
LONG_EXECUTION_ALLOWLIST = {
    "s3-dd-covariance.yml": {
        "job": "response",
        "branch": "science/autonomous-bbn-identity-v4-20261115",
        "path": "analysis/CCC_BBN_NETWORK_20261114/s3_standard/dd_covariance_20261115/RUN_REQUEST.json",
    },
    "p2-fullnet-execute.yml": {
        "job": "fullnet",
        "branch": "s0-fullnet",
        "path": "analysis/CCC_BBN_NETWORK_20261114/p2_fullnet/RUN_REQUEST.json",
    },
    "research-pipeline.yml": {
        "job": "research",
        "branch": "science/autonomous-bbn-identity-v4-20261115",
        "path": "analysis/CCC_BBN_NETWORK_20261114/pipeline/RUN_REQUEST.json",
    },
    "s0-n1-execute.yml": {
        "job": "convergence",
        "branch": "s0-n1-design-20261114",
        "path": "analysis/CCC_BBN_NETWORK_20261114/s0_n1/RUN_REQUEST.json",
    },
    "s0-n1-followup.yml": {
        "job": "followup",
        "branch": "s0-n1-design-20261114",
        "path": "analysis/CCC_BBN_NETWORK_20261114/s0_n1_followup/RUN_REQUEST.json",
    },
}


def _triggers(workflow):
    # PyYAML's YAML 1.1 resolver may parse the key "on" as boolean True.
    return workflow.get("on", workflow.get(True))


def validate_runtime_contract(filename, workflow, triggers, job_name, job):
    """Check request provenance; computation duration is not an admission rule."""
    rule = LONG_EXECUTION_ALLOWLIST.get(filename)
    if rule is None or job_name != rule["job"]:
        return
    if "timeout-minutes" in job:
        raise ValueError("Scientific execution must not impose a project duration timer")
    expected_triggers = {
        "push": {
            "branches": [rule["branch"]],
            "paths": [rule["path"]],
        }
    }
    if triggers != expected_triggers:
        raise ValueError(f"Long execution trigger must be exact push/RUN_REQUEST contract: {filename}")
    if job.get("if") != REPOSITORY_GUARD:
        raise ValueError(f"Long execution must be repository-scoped: {filename}:{job_name}")

    concurrency = workflow.get("concurrency")
    if not isinstance(concurrency, dict) or concurrency.get("cancel-in-progress") is not False:
        raise ValueError(f"Long execution must not be cancelled by a newer run: {filename}")


def check(root=ROOT):
    workflow_dir = root / ".github" / "workflows"
    files = sorted(workflow_dir.glob("*.yml"))
    if not files:
        raise ValueError("No workflows")

    for path in files:
        raw = path.read_text()
        workflow = yaml.safe_load(raw)
        if not isinstance(workflow, dict):
            raise ValueError("Workflow must be a YAML mapping: " + path.name)
        if not isinstance(workflow.get("permissions"), dict):
            raise ValueError("Explicit top-level permissions required: " + path.name)
        if "pull_request_target:" in raw:
            raise ValueError("Privileged PR execution forbidden")

        triggers = _triggers(workflow)
        jobs = workflow.get("jobs")
        if not isinstance(jobs, dict):
            raise ValueError("Workflow jobs mapping required: " + path.name)

        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                raise ValueError(f"Job must be a mapping: {path.name}:{job_name}")
            if "uses" in job:
                if not re.fullmatch(r"\./\.github/workflows/[a-z0-9_-]+\.yml", job["uses"]):
                    raise ValueError("Only repository-local reusable jobs are allowed")
                if not (root / job["uses"]).is_file():
                    raise ValueError("Missing reusable workflow")
                continue  # Validate each called workflow's concrete jobs separately.

            validate_runtime_contract(path.name, workflow, triggers, job_name, job)
            for step in job.get("steps", []):
                use = step.get("uses", "")
                if use and not re.fullmatch(
                    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}", use
                ):
                    raise ValueError("Pin external actions by full SHA")
                if "run" in step and "${{" in step["run"]:
                    raise ValueError("Pass expressions through environment, never shell interpolation")

    development = yaml.safe_load((workflow_dir / "development.yml").read_text())
    triggers = _triggers(development)
    if (
        not isinstance(triggers, dict)
        or "pull_request" not in triggers
        or isinstance(triggers["pull_request"], dict) and "paths" in triggers["pull_request"]
    ):
        raise ValueError("Stable check must observe every PR")
    if "merge-gate" not in development.get("jobs", {}):
        raise ValueError("Missing stable merge gate")

    print("Workflow policy PASS (pinning, permissions, owner placement, allowlisted execution, PR coverage, shell boundaries)")


if __name__ == "__main__":
    check()
