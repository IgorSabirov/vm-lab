"""Plot the archived nuclear trajectory and the hypothetical graph response."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import cumulative_trapezoid

root = Path(__file__).resolve().parent
results = json.loads((root / "results.json").read_text())["trajectory"]
with (root / "control.csv").open() as f:
    data = sorted(csv.DictReader(f), key=lambda row: float(row["t_s"]))
def values(key):
    return np.array([float(row[key]) for row in data])
time, temp = values("t_s"), values("T_MeV")
d, he = values("Y_D"), 4 * values("Y_He4")
cuts = [row["t_s"] for row in results["helium_10_50_90"]]
fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.8), layout="constrained")
ax, bx = axes
ax.plot(time, he / results["helium_reference_at_0p015_MeV"], label="Гелий-4 / конечное содержание")
ax.plot(time, d / max(d), label="Дейтерий / максимум", color="#ba4c27")
ax.axvspan(cuts[0], cuts[-1], alpha=.13, color="#507e8f", label="10–90% накопления гелия")
ax.set(xlim=(160,345), ylim=(0,1.05), title="Ядерная сеть · CONTROL", xlabel="Время, с", ylabel="Нормированное содержание")
grid = np.linspace(cuts[0], cuts[-1], 8193)
for c, color in [(24,"#256f81"), (26,"#ba4c27"), (28,"#69518a")]:
    rate = .15 / 6.582119569e-22 * np.exp(-c*.15 / np.interp(grid,time,temp))
    exposure = -cumulative_trapezoid(rate[::-1],grid[::-1],initial=0)[::-1]
    bx.plot(grid,-np.expm1(-exposure),label=f"c = {c}",color=color)
bx.set(xlim=(cuts[0],cuts[-1]),ylim=(-.02,1.04),title="Граф · L = 7, J = 0,15 МэВ",xlabel="Время формирования ядра, с",ylabel="Вероятность ещё одной попытки до конца окна")
for axis in axes:
    axis.spines[["top","right"]].set_visible(False)
    axis.legend(frameon=False,fontsize=8)
    axis.grid(axis="y",alpha=.18)
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["svg.hashsalt"] = "r150-formation"
fig.savefig(root / "formation.svg", metadata={"Date":None})
