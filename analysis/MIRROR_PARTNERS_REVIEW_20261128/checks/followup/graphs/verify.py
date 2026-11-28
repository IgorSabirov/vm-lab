from pathlib import Path
import json
import sympy as sp

ROOT = Path(__file__).resolve().parent
CASES = {
    "P7": {
        "edges": [(0,1),(1,2),(2,3),(0,4),(4,5),(5,6)],
        "mirror": [0,4,5,6,1,2,3],
        "A": [0,2,5],
    },
    "isolated_center_plus_C6": {
        "edges": [(1,2),(2,3),(3,4),(4,5),(5,6),(6,1)],
        "mirror": [0,6,5,4,3,2,1],
        "A": [0,1,3,5],
    },
    "P5_plus_K2": {
        "edges": [(0,1),(1,2),(0,3),(3,4),(5,6)],
        "mirror": [0,3,4,1,2,6,5],
        "A": [0,2,4,5],
    },
}
results = {}
for name, case in CASES.items():
    h = sp.zeros(7)
    for u,v in case["edges"]:
        h[u,v] = h[v,u] = 1
    p = case["mirror"]
    r = sp.zeros(7)
    for i,j in enumerate(p):
        r[j,i] = 1
    a = case["A"]; b = sorted(set(range(7))-set(a))
    gamma = sp.diag(*[1 if i in a else -1 for i in range(7)])
    reached = {0}
    while True:
        new = reached | {v for u in reached for v in range(7) if h[u,v] != 0}
        if new == reached: break
        reached = new
    q = h.extract(a,b)
    zeros = h.nullspace()
    z = zeros[0]
    parity = (z.T*r*z)[0] / (z.T*z)[0]
    center_weight = z[0]**2 / (z.T*z)[0]
    assert h*gamma + gamma*h == sp.zeros(7)
    assert h*r-r*h == sp.zeros(7)
    assert r*r == sp.eye(7)
    assert len(zeros) == 1
    results[name] = {
        "edges": case["edges"], "mirror": p,
        "connected": len(reached)==7,
        "A": a, "B": b,
        "index_B_minus_A": len(b)-len(a),
        "rank_Q": q.rank(), "nullity_H": len(zeros),
        "commutes_H": h*r-r*h == sp.zeros(7),
        "commutes_Gamma": gamma*r-r*gamma == sp.zeros(7),
        "fixed_vertices": [i for i in range(7) if p[i]==i],
        "null_vector_exact": [str(x) for x in z],
        "null_mirror_parity": str(parity),
        "center_weight_exact": str(center_weight),
        "characteristic_polynomial": str(sp.factor(h.charpoly().as_expr())),
    }
print(json.dumps(results, indent=2, ensure_ascii=False))
(ROOT/"results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False)+"\n")
