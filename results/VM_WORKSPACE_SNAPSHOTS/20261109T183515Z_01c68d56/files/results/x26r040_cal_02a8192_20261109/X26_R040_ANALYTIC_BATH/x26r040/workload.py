"""Exact operation inventory from a frozen spectral manifest."""
from __future__ import annotations


def workload_inventory(manifest: dict) -> dict:
    scan = manifest.get("continuum_scan", {})
    numerics = manifest.get("numerics", {})
    poles = manifest.get("pole_search", {})
    sizes = scan.get("ring_sizes", [])
    zpoints = scan.get("resolvent_test_points", [])
    seeds = poles.get("seeds", [])
    density_energies = manifest.get("diagnostics", {}).get("spectral_density_energies", [])
    feshbach_points = numerics.get("feshbach_test_points", [])
    static_cfg = manifest.get("loading", {}).get("static_no_load_control", {})
    static_times = static_cfg.get("times", [])
    static_sites = static_cfg.get("bath_ring_sites")
    n_models = 1
    items = {
        "models": n_models,
        "ring_sizes": len(sizes),
        "complex_resolvent_points_per_ring": len(zpoints),
        "second_sheet_root_seeds_per_model": len(seeds),
        "feshbach_identity_points_per_model": len(feshbach_points),
        "effective_density_energy_points_per_model": len(density_energies),
        "ring_green_evaluations": n_models * len(sizes) * len(zpoints),
        "second_sheet_root_solves": n_models * len(seeds),
        "feshbach_identity_pairs": n_models * len(feshbach_points),
        "effective_density_evaluations": n_models * len(density_energies),
        "static_no_load_exponential_actions": len(static_times) if static_cfg.get("enabled") else 0,
        "static_no_load_hilbert_dimension": (3 + static_sites) if isinstance(static_sites, int) else None,
        "loading_trajectories": 0,
        "adaptive_spectral_measure_integrals": 1,
    }
    items["total_declared_scalar_work_items"] = sum(v for k,v in items.items()
        if k in {"ring_green_evaluations","second_sheet_root_solves","feshbach_identity_pairs","effective_density_evaluations",
                 "static_no_load_exponential_actions","adaptive_spectral_measure_integrals"})
    frozen = (manifest.get("freeze_state") == "FROZEN"
              and bool(manifest.get("freeze_record_ref"))
              and isinstance(manifest.get("freeze_record_sha256"),str)
              and len(manifest.get("freeze_record_sha256")) == 64)
    return {
        "status": "FROZEN_MANIFEST_OPERATION_COUNT" if frozen else "PROVISIONAL_TEMPLATE_COUNTS_NOT_SUBMIT_READY",
        "formula": "models*ring_sizes*resolvent_points + models*root_seeds + models*feshbach_points + models*density_points + static_no_load_time_points + one_adaptive_matrix_measure_integral",
        "counts": items,
        "runtime_seconds": None,
        "runtime_status": "NOT_EVALUABLE_UNTIL_TARGET_VM_CALIBRATION",
    }
