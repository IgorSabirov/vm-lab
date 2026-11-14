# Full-network conditional S1

Result: **CONDITIONAL_INVARIANCE_PASS**. Engineering: **ENGINEERING_PASS**.

| Run | Yp | D/H | Neff |
|---|---:|---:|---:|
| CONTROL | 0.2470017858883068 | 2.436612244195926e-05 | 3.043977298557918 |
| S1 | 0.2470017862896584 | 2.436612244504022e-05 | 3.043977298557918 |
| NEGATIVE | 0.05605198710761701 | 8.832217272787364e-07 | 3.043977298557918 |

Matched control: True; common-clock invariance: True; cooling-only control detected: True.

Y_i(T) is invariant within the declared numerical contract when the full reaction dynamics and cooling share the prescribed common clock. Cooling-only breaks that invariance.

- Conditional reparametrization, not a derivation of CCC microphysics
- Physical clock identification is not established
- Tiny trace species below the absolute trajectory floor have no relative-accuracy certificate
- Neutrino history and dimensionless inputs fixed; S2 and observational likelihood not tested
