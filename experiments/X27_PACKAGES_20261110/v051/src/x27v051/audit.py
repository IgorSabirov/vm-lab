"""NC13/15/16, static policy graph audit and computed A2 fixture calibration."""
from __future__ import annotations
import ast
from copy import deepcopy
import inspect
import json
from pathlib import Path
import random
from typing import Callable

from .engine import run_b_lite, state_digest
from .model import Apparatus
from .policies import (
    POLICIES, PolicyObservation, invoke_policy, rogue_identifier_policy,
    rogue_opaque_identifier_policy, rogue_oracle_policy,
    rogue_unauthorized_payload_policy, invoke_candidate,
)
from .oracle import evaluator_tasks, evaluate
from .resources import REPAIR_COST, TASK_COST


FORBIDDEN_POLICY_NAMES = {
    "oracle", "target", "y_star", "expected", "task_id", "task_case_id", "evaluator_key",
    "tau", "opaque_id", "opaque_identifier", "evaluator_case", "task_context",
    "record_id", "creator_id", "resources", "apparatus", "task_memory",
    "residual_payload", "prod_memory", "state", "trace", "journal",
}


def static_policy_audit() -> dict[str, object]:
    """Audit production policy source and the evaluator module import boundary."""
    import x27v051.policies as policy_module
    import x27v051.oracle as oracle_module
    import x27v051.engine as engine_module

    source_path = Path(inspect.getsourcefile(policy_module) or "")
    oracle_path = Path(inspect.getsourcefile(oracle_module) or "")
    engine_path = Path(inspect.getsourcefile(engine_module) or "")
    source = source_path.read_text(encoding="utf-8")
    oracle_source = oracle_path.read_text(encoding="utf-8")
    engine_source = engine_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    oracle_tree = ast.parse(oracle_source)
    engine_tree = ast.parse(engine_source)

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden_imports = [name for name in imports if name in {
        "x27v051.oracle", "x27v051.engine", "x27v051.model", "importlib",
        "builtins", "subprocess", "os", "sys", "socket",
    } or name.endswith((".oracle", ".engine", ".model"))]

    oracle_imports = []
    for node in ast.walk(oracle_tree):
        if isinstance(node, ast.Import):
            oracle_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            oracle_imports.append(node.module)
    oracle_forbidden_imports = [name for name in oracle_imports
                                if name in {"x27v051.policies", "x27v051.engine", "x27v051.model"}
                                or name.endswith((".policies", ".engine", ".model"))]

    engine_imports = []
    for node in ast.walk(engine_tree):
        if isinstance(node, ast.Import):
            engine_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            engine_imports.append(node.module)
    engine_forbidden_imports = [name for name in engine_imports
                                if name in {"x27v051.oracle", "x27v051.evaluation"}
                                or name.endswith((".oracle", ".evaluation"))]
    engine_evaluator_identifiers = sorted({node.id for node in ast.walk(engine_tree)
                                           if isinstance(node, ast.Name)
                                           and node.id in {"evaluator_key", "oracle_target", "Y_star", "tau"}})
    run_b_lite_signature = inspect.signature(engine_module.run_b_lite)
    run_b_lite_has_evaluator_argument = any(
        name in run_b_lite_signature.parameters
        for name in ("evaluator_key", "tau", "oracle_target", "Y_star")
    )

    dangerous_calls = {"__import__", "eval", "exec", "open", "getattr", "globals",
                        "locals", "vars", "compile", "import_module"}
    per_policy = {}
    for name, fn in POLICIES.items():
        fn_ast = ast.parse(inspect.getsource(fn))
        names = {n.id for n in ast.walk(fn_ast) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(fn_ast) if isinstance(n, ast.Attribute)}
        calls = {n.func.id for n in ast.walk(fn_ast)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        calls |= {n.func.attr for n in ast.walk(fn_ast)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        violations = sorted((names | attrs) & FORBIDDEN_POLICY_NAMES)
        private_attrs = sorted(a for a in attrs if a.startswith("_"))
        dangerous = sorted(calls & dangerous_calls)
        signature = inspect.signature(fn)
        parameters = tuple(signature.parameters.values())
        interface_ok = (len(parameters) == 1 and parameters[0].name == "obs"
                        and parameters[0].kind in (inspect.Parameter.POSITIONAL_ONLY,
                                                   inspect.Parameter.POSITIONAL_OR_KEYWORD))
        per_policy[name] = {
            "forbidden_names": violations,
            "private_attribute_access": private_attrs,
            "dangerous_calls": dangerous,
            "signature": str(signature),
            "single_observation_argument": interface_ok,
            "pass": not violations and not private_attrs and not dangerous and interface_ok,
        }
    return {
        "policy_module": str(source_path.name),
        "oracle_module": str(oracle_path.name),
        "policy_imports": imports,
        "forbidden_policy_imports": forbidden_imports,
        "oracle_imports": oracle_imports,
        "forbidden_oracle_imports": oracle_forbidden_imports,
        "engine_module": str(engine_path.name),
        "engine_imports": engine_imports,
        "engine_forbidden_evaluator_imports": engine_forbidden_imports,
        "engine_evaluator_identifier_names": engine_evaluator_identifiers,
        "run_b_lite_signature": str(run_b_lite_signature),
        "run_b_lite_has_evaluator_argument": run_b_lite_has_evaluator_argument,
        "policy_field_whitelist": ["public_input", "read_task_memory() when granted", "read_residual_payload() when granted"],
        "scoring_boundary": "engine.py emits execution only; evaluation.py joins evaluator key and computes Y_correct after execution",
        "policy_checks": per_policy,
        "pass": (not forbidden_imports and not oracle_forbidden_imports
                 and not engine_forbidden_imports and not engine_evaluator_identifiers
                 and not run_b_lite_has_evaluator_argument
                 and all(v["pass"] for v in per_policy.values())),
        "limitation": "Static AST/import checks and runtime capability objects detect accidental/ordinary unauthorized access; arbitrary hostile Python requires OS/process isolation.",
    }


def run_nc13() -> dict[str, object]:
    run = run_b_lite("R_int", 3, load=1)
    from .engine import estimate_readiness

    snapshot = run.state_after_repair
    before = state_digest(snapshot)
    estimate = estimate_readiness(snapshot)
    after = state_digest(snapshot)

    # Every hostile mutation uses its own disposable deep copy. The digest is
    # evaluated on the exact object mutated, not on a live trajectory object.
    mutations = (
        ("task_memory.creator_id", "creator-mutated"),
        ("task_memory.record_id", "record-mutated"),
        ("prod_memory.creator_id", "prod-creator-mutated"),
        ("apparatus.creator_id", "app-creator-mutated"),
        ("apparatus.apparatus_id", "app-id-mutated"),
        ("apparatus.token_signature", "token-mutated"),
    )
    mutation_results = {}
    for path, replacement in mutations:
        attack_state = deepcopy(snapshot)
        root, field = path.split(".")
        nested = getattr(attack_state, root)
        digest_before = state_digest(attack_state)
        object.__setattr__(nested, field, replacement)
        digest_after = state_digest(attack_state)
        mutation_results[path] = {
            "digest_changed": digest_before != digest_after,
            "digest_before": digest_before,
            "digest_after": digest_after,
        }
    all_mutations_detected = all(v["digest_changed"] for v in mutation_results.values())
    pure = before == after and estimate.purity_pass
    return {
        "estimator_digest_before": before,
        "estimator_digest_after": after,
        "estimator_pure": pure,
        "nested_provenance_mutations": mutation_results,
        "all_nested_mutations_detected": all_mutations_detected,
        "pass": pure and all_mutations_detected,
        "scope": "Digest comparison is immediately before/after one estimator call; malicious mutations are applied only to separate disposable deep copies.",
    }


def run_nc15(seed: int = 51015, n: int = 200) -> dict[str, object]:
    if n != 200:
        raise ValueError("NC15 is frozen at 200 presentations")
    # Independent deterministic RNG streams avoid creating a shared random
    # stream from which an ID ordering could trivially encode the label shuffle.
    id_rng = random.Random(seed)
    target_rng = random.Random(seed ^ 0xA5A551015)
    opaque_ids = [f"id-{id_rng.getrandbits(64):016x}" for _ in range(n)]
    if len(set(opaque_ids)) != n:
        raise AssertionError("opaque ID collision; change the frozen ID seed")
    targets = [0] * (n // 2) + [1] * (n // 2)
    target_rng.shuffle(targets)
    public_input = (("command", "emit_the_supplied_binary_content"), ("public_hint", 0))
    obs = PolicyObservation(public_input, allowed_sources=(), readers={})
    public_keys = {key for key, _ in obs.public_input}
    forbidden_identifier_keys = {"task_id", "evaluator_key", "opaque_id", "opaque_identifier", "tau"}
    interface_blind = not (public_keys & forbidden_identifier_keys)
    outputs = []
    correct = 0
    for opaque_id, target in zip(opaque_ids, targets):
        # The evaluator-side opaque ID is deliberately not projected into the executor context.
        action, access = invoke_policy("pi_input", obs)
        if access:
            raise RuntimeError("pi_input attempted forbidden access")
        outputs.append(action)
        correct += int(action == target)
    # Relabel all opaque identifiers by an independent permutation; policy input is unchanged.
    relabelled = opaque_ids[:]
    relabel_rng = random.Random(seed ^ 0x5A5A51015)
    relabel_rng.shuffle(relabelled)
    outputs_relabelled = [invoke_policy("pi_input", obs)[0] for _ in relabelled]
    acc_num = correct
    accuracy_exact = (acc_num * 2 == n)
    invariance = outputs == outputs_relabelled and len(set(outputs)) == 1
    signature_clean = list(inspect.signature(POLICIES["pi_input"]).parameters) == ["obs"]
    return {
        "seed": seed, "id_rng_seed": seed, "target_rng_seed": seed ^ 0xA5A551015,
        "independent_rng_streams": True,
        "presentations": n, "unique_opaque_ids": len(set(opaque_ids)),
        "target_counts": {"0": targets.count(0), "1": targets.count(1)},
        "policy": "pi_input", "correct": correct, "accuracy": f"{correct}/{n}",
        "accuracy_exactly_one_half": accuracy_exact,
        "identifier_relabel_invariant": invariance,
        "identifier_not_in_policy_signature": signature_clean,
        "identifier_fields_absent_from_public_input": interface_blind,
        "public_input_keys": sorted(public_keys),
        "pass": accuracy_exact and invariance and interface_blind and signature_clean,
        "rows": [{"opaque_id": oid, "oracle_target": target, "action": action}
                 for oid, target, action in zip(opaque_ids, targets, outputs)],
        "limitation": "Exact 0.5 is a deterministic balanced-design check, not a statistical estimate of generalization error.",
    }


def run_nc16() -> dict[str, object]:
    static = static_policy_audit()
    obs_no_reads = PolicyObservation((("command", "emit_the_supplied_binary_content"), ("public_hint", 0)),
                                     allowed_sources=(), readers={})
    obs_memory_only = PolicyObservation((("command", "emit_the_supplied_binary_content"), ("public_hint", 0)),
                                        allowed_sources=("M_task",),
                                        readers={"M_task": lambda: 0, "P_res": lambda: 1})
    runtime = {}
    probes = {
        "oracle": (rogue_oracle_policy, obs_no_reads),
        "task_id": (rogue_identifier_policy, obs_no_reads),
        "opaque_identifier": (rogue_opaque_identifier_policy, obs_no_reads),
        "evaluator_key": (lambda context: getattr(context, "evaluator_key"), obs_no_reads),
        "target": (lambda context: getattr(context, "target"), obs_no_reads),
        "tau": (lambda context: getattr(context, "tau"), obs_no_reads),
        "state": (lambda context: getattr(context, "state"), obs_no_reads),
        "resources": (lambda context: getattr(context, "resources"), obs_no_reads),
        "trace": (lambda context: getattr(context, "trace"), obs_no_reads),
        "prod_memory": (lambda context: getattr(context, "prod_memory"), obs_no_reads),
        "private_readers": (lambda context: getattr(context, "_readers"), obs_no_reads),
        "record_id": (lambda context: getattr(context, "record_id"), obs_no_reads),
        "creator_id": (lambda context: getattr(context, "creator_id"), obs_no_reads),
        "apparatus": (lambda context: getattr(context, "apparatus"), obs_no_reads),
        "task_memory": (lambda context: getattr(context, "task_memory"), obs_no_reads),
        "residual_payload": (lambda context: getattr(context, "residual_payload"), obs_no_reads),
        "unauthorized_payload_capability": (rogue_unauthorized_payload_policy, obs_memory_only),
    }
    for name, (fn, context) in probes.items():
        value, attempted, blocked = invoke_candidate(fn, context)
        runtime[name] = {"blocked": blocked, "attempted_fields": attempted, "returned_value": value}
    runtime_pass = all(item["blocked"] for item in runtime.values())
    return {
        "static": static,
        "runtime_attempts": runtime,
        "policy_observation_public_fields": ["public_input"],
        "conditional_capabilities": ["read_task_memory()", "read_residual_payload()"],
        "no_oracle_target_or_identifier_access": runtime_pass and static["pass"],
        "pass": runtime_pass and static["pass"],
        "limitation": "The capability context blocks accidental and ordinary unauthorized reads. It is not a security boundary against hostile code exploiting the Python runtime; use OS/process isolation for untrusted policy plugins.",
    }


def calibrate_a2(*, a1: Apparatus | None = None, a2: Apparatus | None = None,
                 a1_cost_profile: tuple[tuple[int, ...], tuple[int, ...]] | None = None,
                 a2_cost_profile: tuple[tuple[int, ...], tuple[int, ...]] | None = None) -> dict[str, object]:
    """Compute fixture-level A1/A2 calibration checks rather than setting booleans."""
    a1 = a1 or Apparatus.a1(2)
    a2 = a2 or Apparatus.a2(2)
    a1_cost_profile = a1_cost_profile or (TASK_COST, REPAIR_COST)
    a2_cost_profile = a2_cost_profile or (TASK_COST, REPAIR_COST)
    role_match = a1.kind == "original" and a2.kind == "substitute"
    port_compat = a1.port_id == a2.port_id and a1.connected and a2.connected
    probe_pairs = []
    function_equal = True
    transition_equal = True
    for health in (1, 2):
        for load in (1, 2):
            f1 = a1.with_health(health).operational and health >= load
            f2 = a2.with_health(health).operational and health >= load
            h1 = max(0, health - 1) if f1 else health
            h2 = max(0, health - 1) if f2 else health
            function_equal &= f1 == f2
            transition_equal &= h1 == h2
            probe_pairs.append({"health": health, "load": load,
                                "A1_success": f1, "A2_success": f2,
                                "A1_health_after": h1, "A2_health_after": h2})
    cost_equal = a1_cost_profile == a2_cost_profile
    connection = a1.connected and a2.connected and a1.port_id == a2.port_id
    checks = {"object_role_validation": role_match,
              "port_compatibility": port_compat, "functional_equivalence": function_equal,
              "transition_equivalence": transition_equal, "cost_equivalence": cost_equal,
              "connection_under_frozen_protocol": connection}
    return {"checks": checks, "probe_results": probe_pairs,
            "A1_fingerprint": {"kind": a1.kind, "port": a1.port_id, "costs": a1_cost_profile},
            "A2_fingerprint": {"kind": a2.kind, "port": a2.port_id, "costs": a2_cost_profile},
            "valid": all(checks.values()),
            "claim_boundary": "Computed equivalence of declared model fixtures; not physical laboratory calibration.",
            "H_A_token": "NOT_CLAIMED"}
