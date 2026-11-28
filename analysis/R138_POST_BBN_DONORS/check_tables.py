"""Read published drft tables. Usage: python check_tables.py /path/to/drft"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import interp1d

REVISION = "e006ed28e916b3f7b87219a7cff5d0b8bd9b96be"
THERMAL = "py_vbc/recfast/planck2018_recfast.dat"
NO_STREAM = "py_vbc/plots/bias/p_vbc_rms_0.00.txt"
STREAM = "py_vbc/plots/bias/p_vbc_rms_42.03.txt"
DIGESTS = {
    THERMAL: "91faed4ae80e2649c97da7c6f4a9e09cee3cbdd87a36787ab636e45ac7ef5b82",
    NO_STREAM: "653da7aad2b2dfbdc600e384c5e190336d8d06e3ad1b6a5e231c3467345065e5",
    STREAM: "39825c9a7349e6fe8e1e008b7692684b87ba0affba00ab85d33e9399a0e1a078",
}


def read_table(root, path):
    file = root / path
    if hashlib.sha256(file.read_bytes()).hexdigest() != DIGESTS[path]:
        raise ValueError(f"Unexpected table version: {path}")
    return np.loadtxt(file)


def analyze(root):
    thermal = read_table(root, THERMAL)[::-1]
    z = thermal[:, 0]
    if not np.all(np.diff(z) > 0) or not z[0] <= 49 <= z[-1]:
        raise ValueError("Invalid redshift grid")
    # Same cubic interpolation and column convention as py_vbc/interpolations.py.
    xe, temperature = interp1d(z, thermal[:, [1, -1]], kind="cubic", axis=0)(49)
    boundary = np.searchsorted(z, 49)
    quoted = 54.17
    reference = read_table(root, NO_STREAM)
    streaming = read_table(root, STREAM)
    if not np.array_equal(reference[:, 0], streaming[:, 0]):
        raise ValueError("The power tables have different wave numbers")
    # In plot_bias.py columns are k, P_c, P_b, P_vc, P_vb.
    examples = []
    for row in [100, 150, 200]:
        ratio = streaming[row, 2] / reference[row, 2]
        examples.append({"zero_based_row": row, "k_as_tabulated": reference[row, 0],
                         "baryon_power_ratio": ratio, "baryon_amplitude_ratio": np.sqrt(ratio)})
    return {
        "upstream_revision": REVISION, "source_sha256": DIGESTS,
        "thermal_z49": {"bracketing_z": z[boundary-1:boundary+1].tolist(),
                        "RECFAST_xe": round(float(xe), 11),
                        "RECFAST_Tm_K": round(float(temperature), 7),
                        "Lumina_Tinit_eq27_K": round(2.7255 * 50**2 / (1+124.8), 7),
                        "Lumina_Tinit_as_published_K": quoted,
                        "difference_vs_published_K": round(float(temperature) - quoted, 7),
                        "relative_difference_percent": round(100*(float(temperature)/quoted-1), 6)},
        "archived_z200_power_comparison": {"zstart": 1000, "stream_km_s_at_zstart_label": 42.03,
                                          "outputs": examples},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drft_root", type=Path)
    print(json.dumps(analyze(parser.parse_args().drft_root), indent=2, allow_nan=False))
