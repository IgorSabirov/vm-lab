import numpy as np

def rates(jumps, gamma):
    jumps = np.asarray(jumps)
    delta = jumps[:, :, None] - jumps[:, None, :]
    return gamma / 2 * np.sum(delta**2, axis=0)

g = 1.7

# mask2,node5 <-> mask4,node6: скорости равны gamma
target = np.array([[1, 0], [0, -1]])
control = np.array([[1, 0], [0,  1]])
assert np.isclose(rates(target, g)[0, 1], g)
assert np.isclose(rates(control, g)[0, 1], g)

# Обе edge-метки mask2, узлы 5 и 6: target 2*gamma, control 0
target = np.array([[1, -1], [0, 0]])
control = np.array([[1,  1], [0, 0]])
assert np.isclose(rates(target, g)[0, 1], 2*g)
assert np.isclose(rates(control, g)[0, 1], 0)
