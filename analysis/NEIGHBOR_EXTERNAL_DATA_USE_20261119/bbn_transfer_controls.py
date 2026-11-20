"""Arithmetic controls for BBN_METHOD_TRANSFER.md. No BBN solver is invoked."""

from math import isclose


def compare_nuclear_responses():
    # Columns: Y_fid and dY/dp (Burns, PRIMAT rates, tau_n normalization),
    # then d ln Y/dq from S3 at h=0.125. The sources are pinned in the report.
    rows = [
        ("D/H", "ddHe3n", 2.445397608, -0.01476710452, -0.00598610731548),
        ("D/H", "ddtp", 2.445393820, -0.01204416835, -0.00506481139034),
        ("Yp", "ddHe3n", 0.2469143134, 1.63e-5, 6.57331758305e-5),
        ("Yp", "ddtp", 0.2469140171, 1.69e-5, 5.68554448561e-5),
    ]
    print("Observable  reaction  atlas_dlogY/dp  S3_dlogY/dq  difference_vs_atlas_%")
    for observable, reaction, fiducial, slope, s3_slope in rows:
        atlas_slope = slope / fiducial
        distance = 100 * abs(s3_slope - atlas_slope) / abs(atlas_slope)
        print(f"{observable:10} {reaction:7} {atlas_slope:14.8g} {s3_slope:12.8g} {distance:9.4f}")


def compare_expansion_histories():
    # Bambi et al., Eqs. (15)-(18), for fractional changes in H, not G.
    print("History     relative_He4_%   relative_D/H_%")
    helium_shifts = []
    for name, early, late in [("early", 0.003, 0.0), ("late", 0.0, 0.0055)]:
        helium = 2 * (0.22 * early + 0.12 * late)
        deuterium = 2 * (0.12 * early + 0.80 * late)
        print(f"{name:10} {100 * helium:15.3f} {100 * deuterium:16.3f}")
        helium_shifts.append(helium)
    assert isclose(*helium_shifts, rel_tol=1e-12)


def compare_radiation_and_spectra():
    # Equal fractional energy injections into photons and preexisting nonphoton
    # radiation at fixed a, with photon thermalization and conserved baryons.
    fractional_injection = 0.04
    print("eta_after/eta_before", (1 + fractional_injection) ** (-0.75))
    # Froustey et al., Table 2, oscillations included, T_nu_e with/without
    # spectral distortions. The deuterium table entries are 1e5 D/H.
    print("delta_Yp", f"{0.24721 - 0.24713:.5f}")
    print("delta_D/H", f"{(2.4261 - 2.4256) * 1e-5:.2e}")


if __name__ == "__main__":
    compare_nuclear_responses()
    compare_expansion_histories()
    compare_radiation_and_spectra()
