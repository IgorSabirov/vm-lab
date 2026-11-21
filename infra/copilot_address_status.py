#!/usr/bin/env python3
"""Classify changed GitHub addresses using existing scientific registries."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "analysis/REGISTRY_LINKS/INDEX.json"
PIPELINE = ROOT / "infra/r135/PIPELINE.json"

TECHNICAL_PREFIXES = (
    ".github/", "tests/", "tools/", "scripts/", "infra/copilot/",
    "infra/copilot_", "infra/workflows/", "docs/technical/",
)
TECHNICAL_NAMES = {
    "README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml",
    "requirements.txt", "Makefile",
}
SCIENTIFIC_ROOTS = (
    "analysis/", "decisions/", "infra/external/contracts/",
    "infra/r135/research/", "infra/r135/evidence/",
)


def load_registry():
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    pipeline = json.loads(PIPELINE.read_text(encoding="utf-8"))
    registered = set(index.get("sources", {})) | set(index.get("managed_review_sources", {}))
    issue_numbers = {int(task["issue_number"]) for task in pipeline.get("tasks", [])
                     if isinstance(task.get("issue_number"), int)}
    return registered, issue_numbers


def classify(change, registered, issue_numbers):
    path = change.get("path") or change.get("previous_path")
    number = change.get("number")
    kind = change.get("kind")
    if path:
        if path.startswith(TECHNICAL_PREFIXES) or Path(path).name in TECHNICAL_NAMES:
            return "technical"
        if path in registered:
            return "scientific"
        if path.startswith(SCIENTIFIC_ROOTS):
            return "candidate"
        return "technical"
    if kind in {"issue", "pull_request", "issue_comment", "pull_request_review",
                "pull_request_review_comment"}:
        if number is not None and int(number) in issue_numbers:
            return "scientific"
        text = (change.get("text") or "").lower()
        if any(root in text for root in SCIENTIFIC_ROOTS):
            return "candidate"
    return "technical"


def route_changes(events):
    registered, issue_numbers = load_registry()
    routed, skipped = [], []
    for change in events.get("changes", []):
        status = classify(change, registered, issue_numbers)
        item = dict(change)
        item["address_status"] = status
        if status in {"scientific", "candidate"}:
            routed.append(item)
        else:
            skipped.append({"id": change.get("id"), "address": change.get("path") or change.get("url"),
                            "status": "technical"})
    events["changes"] = routed
    events["address_routing"] = {
        "schema": "vm-lab-address-routing-v1",
        "sent_to_copilot": len(routed),
        "scientific": sum(x["address_status"] == "scientific" for x in routed),
        "candidate": sum(x["address_status"] == "candidate" for x in routed),
        "technical_skipped": len(skipped),
        "skipped": skipped,
    }
    return events
