"""Read the two pinned PRIMAT tables distributed by CAMB; pass 2021 and 2024 files in order."""
import argparse
from hashlib import sha1, sha256
import json
from pathlib import Path

COMMIT = "c0f5a1e571e6a1c7da021d13594127332696c66c"
BLOBS = {"2021": "4ddb74e60b9ee086aa61f794634a8b27d8b798af",
         "2024": "a9f98b377106be073ad4fdca07bf7602710316d7"}


def read_table(year, path):
    data = path.read_bytes()
    git_blob = sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if git_blob != BLOBS[year]:
        raise ValueError(f"{year}: unexpected table blob {git_blob}")
    rows = {}
    for line in data.decode().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        omega, eta, delta, y_mass, y_bbn, sigma_y, dh, sigma_dh = map(float, line.split())
        key = (omega, delta)
        if key in rows:
            raise ValueError(f"Repeated row {key}")
        rows[key] = dict(eta10=eta, Yp_mass=y_mass, Yp_BBN=y_bbn, sigma_Yp_BBN=sigma_y,
                         D_over_H=dh, sigma_D_over_H=sigma_dh)
    mass_ratio = 4*1.00782503223/4.0026032541
    residual = max(abs(r["Yp_mass"] - 1/(1+mass_ratio*(1/r["Yp_BBN"]-1))) for r in rows.values())
    assert len(rows) == 1300 and residual < 0.000002
    return rows, dict(git_blob=git_blob, sha256=sha256(data).hexdigest(), nodes=len(rows),
                      max_mass_conversion_absolute_residual=residual, reference_row=rows[.022, 0])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table_2021", type=Path)
    parser.add_argument("table_2024", type=Path)
    args = parser.parse_args()
    a, summary_a = read_table("2021", args.table_2021)
    b, summary_b = read_table("2024", args.table_2024)
    assert a.keys() == b.keys()
    key = (.022, 0)
    print(json.dumps(dict(CAMB_commit=COMMIT, common_nodes=len(a), omega_b_h2=key[0], DeltaN=key[1],
                          tables={"2021": summary_a, "2024": summary_b},
                          change_Yp_mass=b[key]["Yp_mass"]-a[key]["Yp_mass"],
                          change_DH_percent=100*(b[key]["D_over_H"]/a[key]["D_over_H"]-1)), indent=2))
