import csv
import mpmath as mp

mp.mp.dps = 60

def z_scalar(y): return (y + y*y) / (1-y)**3
def z_vector(y): return (6*y*y - 2*y**3) / (1-y)**3
def z_weyl(y): return 4*y**mp.mpf("1.5") / (1-y)**3

def z_n(n, chi):
    y = mp.exp(-mp.mpf(n)/chi)
    z_b = 6*z_scalar(y) + z_vector(y)
    z_f = 4*z_weyl(y)
    return z_b + (-1)**(n+1)*z_f

def action(chi, group, nmax=300):
    total = mp.mpf("0")
    for n in range(1, nmax+1):
        z = z_n(n, chi)
        if z >= 1:
            raise ValueError("outside confined saddle")
        total += mp.log1p(-z)
        if group == "SU":
            total += z/n
    return total

def hagedorn_root():
    lo, hi = mp.mpf("0.01"), mp.mpf("2")
    for _ in range(400):
        mid = (lo+hi)/2
        if z_n(1, mid) > 1: hi = mid
        else: lo = mid
    return (lo+hi)/2

def observables(chi, group, nmax=300):
    f = lambda x: action(x, group, nmax)
    i = f(chi)
    ip = mp.diff(f, chi, 1)
    ipp = mp.diff(f, chi, 2)
    c = -chi**2*ip/(2*mp.pi**2)
    cp = -(2*chi*ip + chi**2*ipp)/(2*mp.pi**2)
    energy = lambda x: -x**2*mp.diff(f, x, 1)  # R=1
    cv_energy = mp.diff(energy, chi, 1)
    cv_from_cp = 2*mp.pi**2*cp
    return i, ip, ipp, c, cp, cv_energy, cv_from_cp

if __name__ == "__main__":
    chi_h = hagedorn_root()
    print("chi_H =", mp.nstr(chi_h, 35))
    with open("DATA.csv", "w", newline="") as stream:
        fields = ["group","fraction_chiH","chi","I_A","I_A_prime","I_A_second","C_A","C_A_prime","Cv_energy_route","Cv_from_Cprime"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for fraction in map(mp.mpf, ["0.10","0.20","0.40","0.60","0.80","0.90","0.95","0.98"]):
            chi = fraction*chi_h
            for group in ["U","SU"]:
                vals = observables(chi, group)
                writer.writerow(dict(zip(fields, [group, str(fraction)] + [mp.nstr(chi,35)] + [mp.nstr(v,35) for v in vals])))
