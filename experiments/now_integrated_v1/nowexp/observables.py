"""Descriptive profiles and paired contrasts; no universal invariant claim."""
from collections import Counter, defaultdict
import math


def mean(values):
    return sum(values)/len(values) if values else None


def summarize(rows):
    by_case = defaultdict(list)
    for row in rows:
        by_case[row["case_id"]].append(row)
    summary = {}
    for name, group in sorted(by_case.items()):
        histogram = Counter(tuple(p["function"] for p in r["result"]["profile"]) for r in group)
        summary[name] = dict(n=len(group),
            q_parent=mean([r["result"]["parent_function"] for r in group]),
            q_child=mean([r["result"]["child_function"] for r in group if r["result"]["child_function"] is not None]),
            q_final=mean([r["result"]["final_function"] for r in group]),
            mean_cycles=mean([r["result"]["consecutive_functional"] for r in group]),
            mean_spent_fuel=mean([sum(p["spent_fuel"] for p in r["result"]["profile"]) for r in group]),
            mean_health=mean([sum(p["health"] for p in r["result"]["profile"])/len(r["result"]["profile"]) for r in group]),
            joint_function_profile={"".join(map(str,k)):v/len(group) for k,v in sorted(histogram.items())},
            exact_weighted_probability=False,
            descriptive_sample=True)
    return summary


def paired_contrasts(rows, definitions):
    index = {(r["case_id"], r["seed"]):r for r in rows}
    result = {}
    for contrast in definitions:
        cases = contrast["cases"]
        if len(cases) != len(contrast["weights"]):
            raise ValueError("contrast weights do not match branches")
        seedsets = [{r["seed"] for r in rows if r["case_id"] == c} for c in cases]
        if not seedsets or any(s != seedsets[0] for s in seedsets[1:]) or not seedsets[0]:
            result[contrast["id"]] = dict(status="NOT_EVALUABLE", reason="incomplete paired cases")
            continue
        values = []
        for seed in sorted(seedsets[0]):
            rs = [index[(c,seed)]["result"] for c in cases]
            totals = [r["initial_totals"] for r in rs]
            if contrast.get("require_equal_initial_totals", True) and any(t != totals[0] for t in totals):
                raise ValueError("different total budgets in " + contrast["id"])
            metric = contrast.get("metric", "final_function")
            value = sum(w*r[metric] for w,r in zip(contrast["weights"],rs))
            values.append(value)
        n = len(values)
        deterministic = all(index[(c,seed)].get("sampling_mode")=="deterministic" for c in cases for seed in seedsets[0])
        var = sum((x-mean(values))**2 for x in values)/(n-1) if n>1 else None
        result[contrast["id"]] = dict(status="EXECUTED_DESCRIPTIVE", mean=mean(values), n=n,
            nominal_bounded_95_halfwidth=0.0 if deterministic else sum(abs(w) for w in contrast["weights"])*math.sqrt(math.log(40)/(2*n)),
            sampling_mode="deterministic_case" if deterministic else "seed_ensemble",
            uncertainty_assumption="Independent master seeds are the sampling model; hash addressing is not an independence proof",
            sample_standard_error=None if var is None else math.sqrt(var/n),
            raw_paired_values=values, inference="No significance claim from smoke or uncalibrated sample")
    return result


def ancestor_report(contracts, rows, summaries, contrasts):
    """Evaluate the preregistered promise separately from stage and scientific truth."""
    reports = []
    for contract in contracts:
        item = dict(contract_id=contract["id"], ancestor=contract["ancestor"],
                    before=contract["before"], promised_delta=contract["promised_delta"],
                    prediction=contract["prediction"], evidence_refs=contract["evidence_refs"],
                    positive_return=contract["positive_return"], negative_return=contract["negative_return"],
                    unresolved_return=contract["unresolved_return"], relation=contract["relation"],
                    original_question_resolved=False, scientific_status_promoted=False)
        rule = contract["evaluation"]
        if rule["kind"] == "scope_only":
            item.update(status="NOT_EVALUABLE_IN_THIS_KERNEL", actual=rule["reason"],
                        planning_verdict="Explicitly not promised as an experimental gain")
        elif rule["kind"] == "contrast":
            v = contrasts.get(rule["id"], {})
            if v.get("status") != "EXECUTED_DESCRIPTIVE":
                item.update(status="NOT_EVALUABLE", actual=v)
            else:
                value = v["mean"]
                holds = rule["lower"] <= value <= rule["upper"]
                half = v["nominal_bounded_95_halfwidth"]
                item.update(status="PREDICTION_MET_DESCRIPTIVELY" if holds else "PREDICTION_MISSED_DESCRIPTIVELY",
                            actual=value, uncertainty=v["sample_standard_error"],
                            nominal_95_interval=[value-half,value+half],
                            statistical_interpretation="UNRESOLVED" if value-half < rule["lower"] or value+half > rule["upper"] else "INTERVAL_INSIDE_PREDICTION_BAND",
                            realized_return=contract["positive_return"] if holds else contract["negative_return"],
                            planning_verdict="Descriptive alignment only; main inference needs declared uncertainty and implementation review")
        elif rule["kind"] == "technical_all":
            if not rows:
                item.update(status="NOT_EVALUABLE", actual="no trajectories")
            else:
                ok = all(r["result"]["material_and_credit_balance"] == r["result"]["initial_totals"] for r in rows)
                item.update(status="TECHNICAL_CHECK_MET" if ok else "TECHNICAL_CHECK_FAILED", actual=ok)
        else:
            raise ValueError("unknown ancestor evaluation")
        reports.append(item)
    return reports


def finite_closure(viable, transitions):
    """Universal closure and existence of a viable successor are DIFFERENT checks.

    transitions must enumerate all positive-probability outcomes under every
    allowed damage/action for this finite model. Completeness is a caller obligation.
    """
    v = set(viable)
    if not v or any(z not in transitions or not transitions[z] for z in v):
        return {"status":"NOT_EVALUABLE", "reason":"empty viability set or missing transitions"}
    return dict(status="FINITE_ENUMERATED_CHECK", universal=all(set(transitions[z]) <= v for z in v),
                exists_successor=all(bool(set(transitions[z]) & v) for z in v),
                scope="Conditional on complete transition support and independently defined viability")
