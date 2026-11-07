"""Finite joint profiles, resource-matched contrasts and three-way lineage returns."""
from collections import defaultdict
import json
import math

PROFILE_FIELDS = ("function", "health", "transmitted", "decoded", "own_apparatus",
    "inherited_apparatus", "contact", "contact_origin", "spent_fuel", "remaining_fuel",
    "precursor", "unavailable_fuel", "unavailable_material", "material_waste", "costs",
    "failures", "pending_records", "stored_records", "decode_slots", "inbox_slots", "record_slots",
    "apparatus_types", "route_template", "contact_endpoints", "delivered_peers", "fragment_slots_used", "transmitted_to")


def distribution(group):
    result = []
    for row in group:
        if "outcomes" in row:
            result.extend((leaf["weight"]/len(group), leaf["result"]) for leaf in row["outcomes"])
        else:
            result.append((1/len(group), row["result"]))
    return result


def expected(group, metric):
    return sum(w*r[metric] for w,r in distribution(group))


def profile_histogram(group):
    histogram = defaultdict(float)
    for weight, result in distribution(group):
        key = json.dumps([{k:p.get(k) for k in PROFILE_FIELDS} for p in result["profile"]],
                         sort_keys=True, separators=(",", ":"))
        histogram[key] += weight
    return dict(histogram)


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row)
    summaries = {}
    for name, group in sorted(grouped.items()):
        weighted = distribution(group)
        count = len(weighted[0][1]["profile"])
        generations = []
        for i in range(count):
            qf = sum(w*r["profile"][i]["function"] for w,r in weighted)
            qt = sum(w*bool(r["profile"][i]["transmitted"]) for w,r in weighted)
            qs = sum(w*r["profile"][i]["function"]*bool(r["profile"][i]["transmitted"]) for w,r in weighted)
            children=weighted[0][1]['profile'][i].get('potential_children',
                [weighted[0][1]['profile'][i+1]['node']] if i+1<count else [])
            targets={}
            for child in children:
                denominator=sum(w*int(child in r['profile'][i].get('transmitted_to',children if r['profile'][i]['transmitted'] else [])) for w,r in weighted)
                numerator=sum(w*int(child in r['profile'][i].get('transmitted_to',children if r['profile'][i]['transmitted'] else []))*
                    next(p['function'] for p in r['profile'] if p['node']==child) for w,r in weighted)
                targets[child]=dict(p_transmitted=denominator,p_function_given_transmission=None if denominator==0 else numerator/denominator)
            generations.append(dict(generation=i,carrier=weighted[0][1]['profile'][i]['node'],p_function=qf,p_transport=qt,
                p_transfer_given_function=None if qf==0 or not children else qs/qf,
                conditional_status='terminal_no_successor' if not children else ('zero_conditioning_mass' if qf==0 else 'defined'),
                p_line_success=qs if children else None,
                p_child_function_given_transfer=next(iter(targets.values()))['p_function_given_transmission'] if len(targets)==1 else None,
                per_successor=targets,carrier_index_is_not_genealogical_depth=True))
        summaries[name] = dict(n_tasks=len(group), n_outcomes=len(weighted),
            q_parent=expected(group, "parent_function"), q_final=expected(group, "final_function"),
            q_child=None if count < 2 else expected(group, "child_function"),
            mean_cycles=expected(group, "consecutive_functional"),
            mean_health=expected(group, "mean_health"), mean_spent_fuel=expected(group, "total_spent_fuel"),
            per_generation=generations, joint_profile=profile_histogram(group),
            exact_finite_sum=all("outcomes" in r or r["sampling_mode"] == "deterministic" for r in group),
            interpretation="T is physical packet transmission, separately from child function; not a genetic invariant")
    return summaries


def metric_range(metric, groups):
    if metric in ("parent_function", "child_function", "final_function", "all_functional"):
        return 1.
    if metric == "mean_health":
        return 10.
    if metric == "consecutive_functional":
        return max(r["config"]["generations"] for group in groups for r in group)
    raise ValueError("no preregistered stochastic range for " + metric)


def paired_contrasts(rows, definitions, profile_tolerance=None):
    if profile_tolerance is None:
        from .state import scientific_thresholds
        profile_tolerance = scientific_thresholds()["profile_equivalence_tv"]
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row)
    results = {}
    for definition in definitions:
        names, weights = definition["cases"], definition["weights"]
        if len(names) != len(weights):
            raise ValueError("contrast weights do not match branches")
        groups = [grouped[c] for c in names]
        if any(not group for group in groups):
            results[definition["id"]] = dict(status="NOT_EVALUABLE", reason="missing case")
            continue
        totals = [r["initial_totals"] for group in groups for _,r in distribution(group)]
        if definition.get("require_equal_initial_totals", True) and any(t != totals[0] for t in totals):
            raise ValueError("different total budgets in " + definition["id"])
        exact = all("outcomes" in row or row["sampling_mode"] == "deterministic" for group in groups for row in group)
        metric = definition.get("metric", "final_function")
        average = sum(w*expected(group, metric) for w,group in zip(weights, groups))
        values, half, se = [], 0., None
        if not exact:
            indices = [{r["seed"]:r for r in group} for group in groups]
            if any(set(index) != set(indices[0]) for index in indices[1:]):
                results[definition["id"]] = dict(status="NOT_EVALUABLE", reason="unpaired sampled cases")
                continue
            values = [sum(w*index[seed]["result"][metric] for w,index in zip(weights,indices)) for seed in sorted(indices[0])]
            n = len(values)
            half = metric_range(metric, groups)*sum(abs(w) for w in weights)*math.sqrt(math.log(40)/(2*n))
            se = math.sqrt(sum((v-average)**2 for v in values)/(n*(n-1))) if n>1 else None
        tv = None
        if len(groups) == 2:
            a,b = (profile_histogram(group) for group in groups)
            tv = .5*sum(abs(a.get(k,0)-b.get(k,0)) for k in a.keys() | b.keys())
        results[definition["id"]] = dict(status="EXECUTED_DESCRIPTIVE", mean=average,
            nominal_bounded_95_halfwidth=half, sample_standard_error=se,
            sampling_mode="finite_enumeration" if exact else "seed_ensemble",
            n=[len(group) for group in groups], raw_paired_values=values,
            joint_profile_tv=tv, profile_fields=PROFILE_FIELDS,
            profile_comparison_tolerance=profile_tolerance,
            profile_within_tolerance=None if tv is None or not exact else tv <= profile_tolerance,
            profile_tv_status="exact_on_declared_finite_observables" if exact else "empirical_only_no_population_TV_claim",
            uncertainty_assumption="Finite sums have numerical error but no sampling error; sampled bounds assume independent master seeds",
            inference="No scientific confirmation from smoke; no family-wide discovery claim")
    return results


def ancestor_report(contracts, rows, summaries, contrasts):
    reports = []
    for contract in contracts:
        item = {k:contract[k] for k in ("id", "ancestor", "before", "promised_delta", "prediction",
                "evidence_refs", "positive_return", "negative_return", "unresolved_return", "relation")}
        item["preregistered_evidence_refs"] = item["evidence_refs"]
        item["evidence_refs"] = ["ROWS_INDEX.json" if ref == "TRAJECTORIES.json" else ref
                                 for ref in item["evidence_refs"]]
        item.update(original_question_resolved=False, scientific_status_promoted=False)
        rule = contract["evaluation"]
        if rule["kind"] == "scope_only":
            item.update(status="NOT_EVALUABLE_IN_THIS_KERNEL", actual=rule["reason"])
        elif rule["kind"] == "contrast":
            value = contrasts.get(rule["id"], {})
            if value.get("status") != "EXECUTED_DESCRIPTIVE":
                item.update(status="NOT_EVALUABLE", actual=value, realized_return=contract["unresolved_return"])
            else:
                average, half = value["mean"], value["nominal_bounded_95_halfwidth"]
                low, high = average-half, average+half
                status = "SUPPORTED" if low >= rule["lower"] and high <= rule["upper"] else (
                    "REFUTED" if high < rule["lower"] or low > rule["upper"] else "INCONCLUSIVE")
                item.update(status=status, actual=average, interval=[low,high], contrast_id=rule["id"],
                    realized_return=contract[{"SUPPORTED":"positive_return", "REFUTED":"negative_return", "INCONCLUSIVE":"unresolved_return"}[status]],
                    scope="Preregistered candidate prediction only; shared contrasts are not independent evidence")
        elif rule["kind"] == "technical_all":
            ok = bool(rows) and all(r["material_and_credit_balance"] == r["initial_totals"] for _,r in distribution(rows))
            item.update(status="TECHNICAL_CHECK_MET" if ok else "TECHNICAL_CHECK_FAILED", actual=ok)
        else:
            raise ValueError("unknown ancestor evaluation")
        additional = []
        for requirement in contract.get("additional_requirements", []):
            value = contrasts.get(requirement["contrast"], {})
            actual = value.get(requirement.get("field", "mean"))
            half = value.get("nominal_bounded_95_halfwidth", 0.)
            if requirement.get("field") == "joint_profile_tv":
                half = 0. if value.get("sampling_mode") == "finite_enumeration" else float("inf")
            status = "INCONCLUSIVE"
            if actual is not None:
                if actual-half >= requirement["lower"] and actual+half <= requirement["upper"]:
                    status = "SUPPORTED"
                elif actual+half < requirement["lower"] or actual-half > requirement["upper"]:
                    status = "REFUTED"
            additional.append(dict(requirement=requirement, actual=actual, status=status))
        if additional:
            item["additional_requirements"] = additional
            statuses = [item["status"]]+[r["status"] for r in additional]
            aggregate = "REFUTED" if "REFUTED" in statuses else ("SUPPORTED" if all(s=="SUPPORTED" for s in statuses) else "INCONCLUSIVE")
            item["status"] = aggregate
            item["realized_return"] = contract[{"SUPPORTED":"positive_return", "REFUTED":"negative_return", "INCONCLUSIVE":"unresolved_return"}[aggregate]]
        reports.append(item)
    return reports


def finite_closure(viable, transitions):
    v = set(viable)
    if not v or any(z not in transitions or not transitions[z] for z in v):
        return {"status":"NOT_EVALUABLE", "reason":"empty viability set or missing transitions"}
    return dict(status="FINITE_ENUMERATED_CHECK", universal=all(set(transitions[z]) <= v for z in v),
                exists_successor=all(bool(set(transitions[z]) & v) for z in v),
                scope="Conditional on complete transition support and independently defined viability")
