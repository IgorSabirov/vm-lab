"""Declared operation inventory for the optional integrated X26 pipeline."""
from __future__ import annotations


def integrated_workload_inventory(manifest: dict) -> dict:
    spectral = manifest.get("spectral", {})
    scan = spectral.get("continuum_scan", {})
    numerics = spectral.get("numerics", {})
    density = spectral.get("diagnostics", {}).get("spectral_density_energies", [])
    seeds = spectral.get("pole_search", {}).get("seeds", [])
    sizes = scan.get("ring_sizes", [])
    zpoints = scan.get("resolvent_test_points", [])
    loading = manifest.get("loading", {})
    transfer = manifest.get("transfer", {})
    return {
        "status": "DECLARED_COUNTS_ADAPTIVE_SOLVER_STEPS_NOT_KNOWN_PRE_RUN",
        "carrier_steps": 1,
        "local_feature_sites_before_after": 6,
        "phi_mappings": 2,
        "K_preserving_permutation_controls": 1,
        "projector_transport_checks": 1 if transfer.get("enabled") else 0,
        "spectral": {
            "ring_sizes": len(sizes),
            "resolvent_points_per_ring": len(zpoints),
            "ring_green_evaluations": len(sizes) * len(zpoints),
            "feshbach_identity_points": len(numerics.get("feshbach_test_points", [])),
            "pole_root_seeds": len(seeds),
            "density_sample_points": len(density),
            "adaptive_measure_integrals": 1,
        },
        "loading": {
            "enabled": bool(loading.get("enabled")),
            "declared_time_samples": len(loading.get("times", [])),
            "adaptive_ode_internal_steps": None,
            "status": "ADAPTIVE_STEPS_DEPEND_ON_SOLVER_AND_ACCEPTANCE_TOLERANCES" if loading.get("enabled") else "DISABLED",
        },
        "runtime_seconds": None,
        "runtime_status": "NOT_EVALUABLE_UNTIL_TARGET_VM_CALIBRATION_OF_THIS_EXACT_PIPELINE",
    }
