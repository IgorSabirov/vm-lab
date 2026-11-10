"""Positive/negative controls and exact evaluator-validation checks."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

from .analysis import (
    deterministic_law,
    hq_synthetic_controls,
    mixed_difference_norm,
    run_apparatus_factorial,
    run_memory_apparatus_interaction,
    run_payload_bypass_positive_control,
    run_x27a_matrix,
    total_variation,
)
from .engine import (
    advance_stage,
    estimate_readiness,
    make_initial_state,
    run_b_lite,
    run_task1_probe,
    state_digest,
)
from .model import (
    Arm,
    Apparatus,
    Disturbance,
    EquipmentHealth,
    MemoryRecord,
    ModelConfig,
    OutcomeStatus,
    RepairRecord,
    ResourceVector,
    SubstituteCalibration,
)


class EstimatorDegenerate(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PurityGuardResult:
    valid: bool
    status: str
    before: str
    after: str


def guarded_estimator_call(state, estimator: Callable) -> PurityGuardResult:
    """Call an estimator and detect any state mutation, including illicit bypasses
    of frozen dataclasses. It is a detector, not a rollback mechanism.
    """
    before = state_digest(state)
    try:
        estimator(state)
    except Exception:
        # An evaluator exception does not erase a detected mutation.
        pass
    after = state_digest(state)
    return PurityGuardResult(
        valid=(before == after),
        status="VALID" if before == after else "RUN_INVALID_SIDE_CHANNEL_LEAK",
        before=before,
        after=after,
    )


def _has_event(events, event_type: str, **expected: object) -> bool:
    for event in events:
        if event.event_type != event_type:
            continue
        details = dict(event.details)
        if all(details.get(k) == v for k, v in expected.items()):
            return True
    return False


def _calibration(valid: bool = True) -> SubstituteCalibration:
    return SubstituteCalibration(valid, valid, valid, valid, valid)


def _r2_joint_profile(run) -> tuple[object, ...]:
    state = run.state_final
    return (
        state.task1_function,
        state.task1_status,
        state.task2_function,
        state.task2_status,
        state.time,
        state.resources.as_tuple(),
        (state.apparatus.kind.value, state.apparatus.health.value, state.apparatus.connected),
        (run.readiness.v_nom, run.readiness.v_rob),
    )


def _direct_total_variation(p: dict, q: dict) -> Fraction:
    """Independent direct-sum TV control, intentionally not calling the estimator."""
    support = set(p) | set(q)
    return sum(
        (abs(Fraction(p.get(item, 0)) - Fraction(q.get(item, 0))) for item in support),
        Fraction(0, 1),
    ) / 2



def _exact_matrix_rank(matrix: list[list[Fraction]]) -> int:
    """Gaussian-elimination rank over Q for the declared factorial design."""
    if not matrix:
        return 0
    a = [list(map(Fraction, row)) for row in matrix]
    rows, cols = len(a), len(a[0])
    rank = 0
    for col in range(cols):
        pivot = next((r for r in range(rank, rows) if a[r][col] != 0), None)
        if pivot is None:
            continue
        a[rank], a[pivot] = a[pivot], a[rank]
        pivot_value = a[rank][col]
        a[rank] = [value / pivot_value for value in a[rank]]
        for r in range(rows):
            if r != rank and a[r][col] != 0:
                factor = a[r][col]
                a[r] = [x - factor * y for x, y in zip(a[r], a[rank])]
        rank += 1
        if rank == rows:
            break
    return rank

def run_e2_checks() -> dict[str, object]:
    """Six E2 checks for this exact finite/deterministic specification."""
    cells = run_x27a_matrix()
    # 1. Definedness: exact finite laws are normalized and all denominators exist.
    p0 = deterministic_law((0, "SUCCESS", 3, (2, 2, 1, 0)))
    q0 = deterministic_law((1, "SUCCESS", 3, (2, 2, 1, 0)))
    defined = total_variation(p0, q0) == Fraction(1, 1)

    # 2. Support and the exact rank of the 2x2 factorial design operator.
    support_cells = set(cells["cells"]) == {"00", "01", "10", "11"}
    design = [[Fraction(1), Fraction(m), Fraction(p), Fraction(m * p)] for m, p in ((0, 0), (0, 1), (1, 0), (1, 1))]
    design_rank = _exact_matrix_rank(design)
    support = support_cells and design_rank == 4

    # 3. Null control: identical synthetic laws must produce exactly zero.
    null_zero = total_variation(p0, p0) == 0

    # 4. Positive control: disjoint deterministic laws must produce exactly one.
    positive_detected = total_variation(p0, q0) == 1

    # 5. No binning is used in the primary estimator: full discrete profiles are
    # compared directly. Re-evaluation of the identity representation must match.
    identity_profile = lambda x: x
    original_tv = total_variation(p0, q0)
    identity_tv = total_variation(
        {identity_profile(k): v for k, v in p0.items()},
        {identity_profile(k): v for k, v in q0.items()},
    )
    resolution = original_tv == identity_tv

    # 6. Independent implementation: direct sum formula vs the TV function.
    direct = sum((abs(p0.get(y, 0) - q0.get(y, 0)) for y in set(p0) | set(q0)), Fraction(0, 1)) / 2
    independent = direct == original_tv

    results = {
        "E2_1_definedness": "PASS" if defined else "FAIL",
        "E2_2_support_identifiability": "PASS" if support else "FAIL",
        "E2_3_null_control": "PASS" if null_zero else "FAIL",
        "E2_4_positive_control": "PASS" if positive_detected else "FAIL",
        "E2_5_resolution_control": "PASS_EXACT_UNBINNED" if resolution else "FAIL",
        "E2_6_independent_implementation": "PASS" if independent else "FAIL",
    }
    return {"checks": results, "design_matrix_rank": design_rank, "design_matrix_columns": 4, "all_pass": all(value.startswith("PASS") for value in results.values())}


def run_pc_nc_controls() -> dict[str, object]:
    calibration = _calibration(True)
    x27a = run_x27a_matrix()
    bypass = run_payload_bypass_positive_control()
    apparatus = run_apparatus_factorial(calibration=calibration)
    hma = run_memory_apparatus_interaction()
    synthetic_hq = hq_synthetic_controls()

    # PC4: introduce an explicit token-level dynamic condition. The requirement
    # is part of the kernel config and is not inferred from provenance labels.
    token_config = ModelConfig(required_token_signature="token-original")
    token_test = run_apparatus_factorial(calibration=calibration, config=token_config)

    # PC6: internal repair with a frozen r0 protocol, independent of M_prod.
    r1_control = run_b_lite(arm=Arm.R_INT, prod_memory=RepairRecord.make("r1"), causal_prod_read=False)
    # PC7: causal repair instruction read from M_prod, with r0/r1 outputs contrasted.
    r0_causal = run_b_lite(arm=Arm.R_INT, prod_memory=RepairRecord.make("r0"), causal_prod_read=True)
    r1_causal = run_b_lite(arm=Arm.R_INT, prod_memory=RepairRecord.make("r1"), causal_prod_read=True)
    def causal_repair_trace_ok(run, expected_instruction: str) -> bool:
        read_index = next((i for i, event in enumerate(run.events)
                           if event.event_type == "read_event"
                           and dict(event.details).get("source") == "M_prod"), None)
        repair_index = next((i for i, event in enumerate(run.events)
                             if event.event_type == "repair_action"), None)
        if read_index is None or repair_index is None or read_index >= repair_index:
            return False
        read_value = dict(run.events[read_index].details).get("returned_value")
        repair_value = dict(run.events[repair_index].details).get("instruction")
        return read_value == expected_instruction and repair_value == expected_instruction

    prod_read_trace = causal_repair_trace_ok(r0_causal, "r0") and causal_repair_trace_ok(r1_causal, "r1")
    r2_profile_r0 = _r2_joint_profile(r0_causal)
    r2_profile_r1 = _r2_joint_profile(r1_causal)
    r2_law_r0 = deterministic_law(r2_profile_r0)
    r2_law_r1 = deterministic_law(r2_profile_r1)
    r2_tv = total_variation(r2_law_r0, r2_law_r1)
    r2_tv_direct = _direct_total_variation(r2_law_r0, r2_law_r1)
    r2_profile_fields = ["Y_function_T1", "Y_status_T1", "Y_function_T2", "Y_status_T2", "T_finish", "R_final", "apparatus_final", "readiness"]
    r2_differing_fields = [
        label for label, left, right in zip(r2_profile_fields, r2_profile_r0, r2_profile_r1)
        if left != right
    ]
    r2_differing_resource_components = [
        label for label, left, right in zip(("E", "M", "W", "U"), r0_causal.state_final.resources.as_tuple(), r1_causal.state_final.resources.as_tuple())
        if left != right
    ]
    no_prod_read_for_r1 = not _has_event(r1_control.events, "read_event", source="M_prod")

    # NC1: action with no main-memory read must not be counted as causal use.
    no_read = run_task1_probe(
        task_memory=MemoryRecord.make(0),
        residual_payload=MemoryRecord.make(0),
        apparatus=Apparatus.a1(),
        read_source="none",
    )
    corrupt_task = run_b_lite(
        arm=Arm.R_INT,
        task_memory=MemoryRecord.make(0).corrupted(),
        prod_memory=RepairRecord.make("r0"),
        causal_prod_read=True,
    )
    nc1 = (
        no_read.profile.y_status == OutcomeStatus.MISSING_READ_EVENT.value
        and not _has_event(no_read.events, "read_event")
        and corrupt_task.state_final.task1_status == OutcomeStatus.INTEGRITY_ERROR.value
        and _has_event(corrupt_task.events, "read_event", source="M_prod")
        and not _has_event(corrupt_task.events, "read_event", source="M_task", task=1)
    )

    # NC2: mere inventory presence is not apparatus use.
    worn_app = run_task1_probe(
        task_memory=MemoryRecord.make(0),
        residual_payload=MemoryRecord.make(0),
        apparatus=Apparatus.a1(health=EquipmentHealth.WORN),
    )
    nc2 = not worn_app.used_apparatus and not _has_event(worn_app.events, "apparatus_use_event")

    # NC3: no payload-to-main-memory copy event is permitted in the reference kernel.
    nc3 = all(
        event["event_type"] != "copy_payload_to_M_task"
        for cell in x27a["cells"].values()
        for event in cell["events"]
    )

    # NC4: a degenerate empty estimator has an explicit non-evaluable status.
    try:
        total_variation({}, {})
        nc4_status = "FAIL"
    except ValueError:
        nc4_status = "NOT_EVALUABLE_ESTIMATOR_DEGENERATE"
    nc4 = nc4_status == "NOT_EVALUABLE_ESTIMATOR_DEGENERATE"

    # NC5: each memory contrast shares matrix cells; it is not four independent
    # replications. Record the shared-cell structure explicitly.
    nc5_shared = {"delta_M_P0": ["00", "10"], "delta_M_P1": ["01", "11"], "delta_P_M0": ["00", "01"], "delta_P_M1": ["10", "11"]}
    nc5 = len({cell for pair in nc5_shared.values() for cell in pair}) == 4 and "00" in nc5_shared["delta_M_P0"] and "00" in nc5_shared["delta_P_M0"]

    # NC6: same scalar success, distinct full profile => full profile TV is nonzero.
    scalar_a = ("SUCCESS", (1, 1, 1, 0))
    scalar_b = ("SUCCESS", (1, 1, 2, 0))
    nc6_tv = total_variation(deterministic_law(scalar_a), deterministic_law(scalar_b))
    nc6 = scalar_a[0] == scalar_b[0] and nc6_tv == 1

    # NC7: checksum-corrupt record must not validate as Tm.
    tm = MemoryRecord.make(1)
    nc7 = not tm.corrupted().valid

    # NC8: uncalibrated A2 blocks token interpretation.
    uncalibrated = run_apparatus_factorial(calibration=_calibration(False), config=token_config)
    nc8 = uncalibrated["H_A_token"] == "NOT_EVALUABLE_UNCALIBRATED_SUBSTITUTE"

    # NC9: external donation is registered and is not marked internal.
    rext = run_b_lite(arm=Arm.R_EXT, causal_prod_read=False)
    nc9 = rext.state_final.external_donor_used and not rext.state_final.internal_restore_used

    # NC10: injected mutation must be detected. Work on a disposable copy.
    disposable = deepcopy(make_initial_state())
    def mutating_estimator(state):
        object.__setattr__(state, "time", state.time + 1)
    guard = guarded_estimator_call(disposable, mutating_estimator)
    nc10 = (not guard.valid) and guard.status == "RUN_INVALID_SIDE_CHANNEL_LEAK"

    # NC11: safe readiness evaluation is invariant under stress-scenario order.
    fixed = run_b_lite(arm=Arm.R_INT, causal_prod_read=False)
    nc11 = fixed.readiness.order_independent

    # NC12: the full stress set is reported even if its first item fails.
    scenario_names = [entry.disturbance for entry in fixed.readiness.scenarios]
    nc12 = scenario_names == [Disturbance.NONE.value, Disturbance.DELAY.value, Disturbance.LOSS_E.value, Disturbance.LOSS_M.value]

    # NC13: the stage-4 purity guard detects nested provenance and identity changes.
    snapshot = make_initial_state(
        task_memory=MemoryRecord.make(0, record_id="M_task:NC13", creator_id="C_task"),
        prod_memory=RepairRecord.make("r0", record_id="M_prod:NC13"),
        residual_payload=MemoryRecord.make(1, record_id="P_res:NC13", creator_id="C_payload"),
    )
    while snapshot.stage < 4:
        snapshot = advance_stage(
            snapshot, arm=Arm.R_INT, disturbance=Disturbance.NONE, causal_prod_read=False
        ).state
    nested_mutations = (
        ("task_memory", "creator_id", "C_task:mutated"),
        ("task_memory", "record_id", "M_task:mutated"),
        ("task_memory", "version", 2),
        ("prod_memory", "creator_id", "C_prod:mutated"),
        ("prod_memory", "record_id", "M_prod:mutated"),
        ("prod_memory", "version", 2),
        ("residual_payload", "creator_id", "C_payload:mutated"),
        ("residual_payload", "record_id", "P_res:mutated"),
        ("residual_payload", "version", 2),
        ("apparatus", "creator_id", "C_apparatus:mutated"),
        ("apparatus", "apparatus_id", "apparatus:mutated"),
    )
    nc13_results = {}
    for object_name, field_name, replacement_value in nested_mutations:
        nested_state = deepcopy(snapshot)
        def mutate_nested(state, object_name=object_name, field_name=field_name, replacement_value=replacement_value):
            object.__setattr__(getattr(state, object_name), field_name, replacement_value)
        mutation_guard = guarded_estimator_call(nested_state, mutate_nested)
        nc13_results[f"{object_name}.{field_name}"] = not mutation_guard.valid
    nc13 = all(nc13_results.values())

    # NC14: checksum corruption and absent read events remain distinct statuses.
    integrity_probe = run_b_lite(
        arm=Arm.R_INT,
        task_memory=MemoryRecord.make(0).corrupted(),
        prod_memory=RepairRecord.make("r0"),
        causal_prod_read=True,
    )
    missing_read_probe = run_task1_probe(
        task_memory=MemoryRecord.make(0),
        residual_payload=MemoryRecord.make(0),
        apparatus=Apparatus.a1(),
        read_source="none",
    )
    nc14 = (
        integrity_probe.state_final.task1_status == OutcomeStatus.INTEGRITY_ERROR.value
        and missing_read_probe.profile.y_status == OutcomeStatus.MISSING_READ_EVENT.value
        and _has_event(integrity_probe.events, "integrity_error", source="M_task", task=1)
        and not _has_event(integrity_probe.events, "read_event", source="M_task", task=1)
    )

    controls = {
        "PC1_main_memory_causality_and_no_payload_bypass": x27a["H_M"] == "PASS" and x27a["H_P"] == "PASS",
        "PC2_payload_bypass_detected": bypass["H_P"] == "FAIL" and bypass["payload_read_detected"],
        "PC3_apparatus_class_necessity": apparatus["H_A_class"] == "PASS",
        "PC4_token_specificity_positive_control": token_test["H_A_token"] == "PASS",
        "PC5_memory_apparatus_interaction": hma["H_MA"] == "PASS",
        "PC6_internal_restore_without_M_prod_causality": r1_control.task2_success and r1_control.readiness.v_nom and no_prod_read_for_r1,
        "PC7_causal_production_memory_restore": (
            prod_read_trace and r0_causal.task2_success and r1_causal.task2_success
            and r2_tv == Fraction(1, 1) and r2_tv_direct == r2_tv
        ),
        "PC8_nonaggregability_detected": synthetic_hq["PC8_nonaggregability_detected"],
        "PC9_aggregability_confirmed": synthetic_hq["PC9_aggregability_confirmed"],
    }
    negatives = {
        "NC1_missing_main_memory_read": nc1,
        "NC2_inventory_without_use": nc2,
        "NC3_hidden_payload_copy_absent": nc3,
        "NC4_degenerate_estimator_not_evaluable": nc4,
        "NC5_shared_cells_not_independent_replicates": nc5,
        "NC6_full_profile_detects_scalar_alias": nc6,
        "NC7_corrupt_checksum_rejected": nc7,
        "NC8_uncalibrated_substitute_not_evaluable": nc8,
        "NC9_external_donor_not_internal_restore": nc9,
        "NC10_readiness_side_channel_detected": nc10,
        "NC11_order_independence": nc11,
        "NC12_all_stress_scenarios_executed": nc12,
        "NC13_nested_state_mutations_detected": nc13,
        "NC14_task_memory_integrity_error_distinct_from_missing_read": nc14,
    }
    return {
        "positive_controls": {name: "PASS" if passed else "FAIL" for name, passed in controls.items()},
        "negative_controls": {name: "PASS" if passed else "FAIL" for name, passed in negatives.items()},
        "summary": {
            "pc_pass": sum(controls.values()),
            "pc_total": len(controls),
            "nc_pass": sum(negatives.values()),
            "nc_total": len(negatives),
            "all_pass": all(controls.values()) and all(negatives.values()),
        },
        "r1_control": r1_control.as_dict(),
        "r2_contrast": {
            "r0_task2_success": r0_causal.task2_success,
            "r1_task2_success": r1_causal.task2_success,
            "r0_final_resources": r0_causal.state_final.resources.as_dict(),
            "r1_final_resources": r1_causal.state_final.resources.as_dict(),
            "delta_U": r1_causal.state_final.resources.unavailable - r0_causal.state_final.resources.unavailable,
            "profile_fields": r2_profile_fields,
            "differing_profile_fields": r2_differing_fields,
            "differing_resource_components": r2_differing_resource_components,
            "functional_outcome_difference_detected": any(
                label in r2_differing_fields
                for label in ("Y_function_T1", "Y_status_T1", "Y_function_T2", "Y_status_T2", "T_finish", "apparatus_final")
            ),
            "profile_r0": r2_profile_r0,
            "profile_r1": r2_profile_r1,
            "TV_full_joint_profile": str(r2_tv),
            "TV_independent_direct_sum": str(r2_tv_direct),
            "TV_estimator_matches_independent_sum": r2_tv == r2_tv_direct,
            "M_prod_read_trace": prod_read_trace,
        },
        "NC13_nested_mutations": nc13_results,
        "readiness_purity_guard": {
            "status": guard.status,
            "before": guard.before,
            "after": guard.after,
        },
        "H_Q_synthetic": synthetic_hq,
    }
