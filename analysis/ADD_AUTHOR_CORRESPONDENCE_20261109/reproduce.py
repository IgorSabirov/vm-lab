"""Definition-4 port/bit convention check, C1; no dependencies; no interaction I."""
def q_literal(w):
    # Old direction: u_i:b -- u_(i+1):a.
    # Printed names: w_i = u_i.r vee u_(i+1).l.
    # Printed incidence: w_i:b -- w_(i-1):a.
    h=[(s[0],w[(i+1)%len(w)][1]) for i,s in enumerate(w)]
    return list(reversed(h))  # list always follows directed b->a edges

def tau(w):
    # a particles move to predecessor, b particles to successor.
    return [(w[(i+1)%len(w)][0],w[(i-1)%len(w)][1]) for i in range(len(w))]

def q_fig2a(w):
    # Proposed consistent convention: preserve incidence, swap bit sources.
    return [(w[(i+1)%len(w)][0],s[1]) for i,s in enumerate(w)]

def canon(w):
    return min(tuple(w[i:]+w[:i]) for i in range(len(w)))

w=[(1,0),(0,1),(0,0)]
q2=q_literal(q_literal(w)); expected=tau(w)
assert q2==w
assert canon(q2)!=canon(expected)
# Twice Q_fig shifts the list origin by one vertex; recover old vertex names.
fig=q_fig2a(q_fig2a(w)); fig_on_old_names=fig[-1:]+fig[:-1]
assert fig_on_old_names==expected
print('Initial:',w)
print('Literal Q^2:',q2)
print('Port shift tau:',expected)
print('Particles occupy distinct vs same vertices: mismatch survives renaming.')
print('Fig-2a convention Q^2 on original vertex names:',fig_on_old_names)
