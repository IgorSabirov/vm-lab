#!/usr/bin/env python3
"""Check whether the actual H_X coefficient embedding lies in the 5/5 region."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "ADD_LOCAL_EDGE_ENERGY_FOLLOWUP_20261120" / "CHECKS.json"


def n4(word):
    w = tuple(map(int, word)); n = len(w)
    return sum(int(all(w[(i+j) % n] & 1 for j in range(4))) for i in range(n))


def main():
    source = json.loads(PARENT.read_text())
    h, J = 1.0, 1.0  # same normalized benchmark J/h=1 as H_X scan
    # Embed H_X=h L + J N_4(a) into E=sum eps_ij + sum eta_ijkl.
    eps = {(i, j): h for i in range(4) for j in range(4)}
    eta = {(i, j, k, l): (J if all(x & 1 for x in (i,j,k,l)) else 0.0)
           for i in range(4) for j in range(4)
           for k in range(4) for l in range(4)}
    u0 = eps[(0,0)] + eta[(0,0,0,0)]
    # The 5/5 contrast on the binary 1/2 subalphabet.
    D = sum(((-1) ** motif.count(2)) * eta[motif]
            for motif in ((i,j,k,l) for i in (1,2) for j in (1,2)
                          for k in (1,2) for l in (1,2)))
    rows = []
    for p in source["pairs"]:
        a, b = p["A"], p["B"]
        da = n4(a) - n4(b)
        delta = J * da
        rows.append({
            "pair": p["pair"], "A": a, "B": b,
            "delta_N4": da, "delta_E_X": delta,
            "distinguishes": abs(delta) > 1e-12
        })
    pass_count = sum(r["distinguishes"] for r in rows)
    # Strict constant-gap + passive-Q classification in contact_balance:
    # its complete solution has contrast D=0, hence it cannot overlap D!=0.
    result = {
        "status": "PASS" if pass_count == 5 and abs(D) > 1e-12 else "FAIL",
        "model": "H_X=h L + J N_4(a), eps_ij=h, eta_ijkl=J iff all four symbols have a-bit=1, else 0",
        "normalization": {"h": h, "J": J, "J_over_h": J/h},
        "u0": {"eps_00": eps[(0,0)], "eta_0000": eta[(0,0,0,0)], "u0": u0},
        "five_pair_region": {
            "contrast_D": D,
            "region_condition": "D != 0",
            "pairs_distinguished": pass_count,
            "pairs_total": len(rows),
            "pair_results": rows
        },
        "strict_contact_gap_compatibility": {
            "status": "FAIL",
            "reason": "The exact passive-Q plus context-independent 12<->3 gap classification forces D=0 for all five witnesses. This H_X has D=J!=0, so its event gap necessarily depends on the local neighborhood.",
            "scope": "This does not invalidate the relaxed neighbor-dependent local Hamiltonian; it excludes simultaneous imposition of a constant contact gap."
        },
        "verdict": "The actual H_X coefficient embedding is inside the 5/5 distinguishing region for J!=0; u0=h is independent of the contrast coordinate D. Gate A passes for the neighbor-dependent model, not for the stricter constant-gap model."
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
