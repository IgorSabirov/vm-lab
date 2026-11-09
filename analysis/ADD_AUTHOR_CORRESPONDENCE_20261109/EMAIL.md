To: Pablo Arrighi <pablo.arrighi@inria.fr>
Cc: Amélia Durbec <amelia.durbec@junia.com>
Subject: Clarification of Definition 4 versus Fig. 2(a), arXiv:2306.07121v2
Status: PREPARED_NOT_SENT — no email account connected

Dear Professor Arrighi and Dr Durbec,

I am independently studying your paper "Time arrow without past hypothesis: a toy model explanation" (arXiv:2306.07121v2). I would appreciate clarification of an apparent inconsistency between Definition 4 (PDF page 5), Fig. 2(a), and the stated identity Q² = tau, where Q denotes the half-shift.

Take a directed ring u_i:b -- u_(i+1):a, with indices modulo L. The printed vertex names give w_i = u_i.r vee u_(i+1).l. The printed edge formula then appears to connect w_i:b to w_(i-1):a, reversing the cyclic order. Reading the bit clause with its apparent x/x-prime typo corrected in the natural way gives the state (a_i, b_(i+1)) at w_i.

With those two conventions together, applying Q twice restores the original directed state word, rather than transporting the a and b particles to their respective neighbouring vertices.

A three-vertex C1 example makes the distinction independent of name bookkeeping. List states as (a,b), following b->a edges:

    X                   = [(1,0), (0,1), (0,0)]
    literal Q²(X)       = [(1,0), (0,1), (0,0)]
    port transport tau(X)= [(0,0), (0,0), (1,1)]

The two particles remain on separate vertices under the literal reading but occupy the same vertex under tau. Rotation or vertex renaming cannot reconcile these outcomes. No interaction I is applied in this example.

A convention consistent with my reading of Fig. 2(a) is instead:

    w_i:b -- w_(i+1):a
    a(w_i) = a(u_(i+1)),  b(w_i) = b(u_i).

The second half-shift then reconstructs the name u_(i+1), and on the original vertex names the bits obey a'_i = a_(i+1), b'_i = b_(i-1), as required by tau.

Could you confirm whether Definition 4 contains indexing/incidence typographical errors, or point out the convention I have missed? If a corrected specification or reference implementation is available, I would be grateful for a pointer.

This is a question about the written specification. I am not claiming that your intended model, expansion theorems, or numerical implementation are invalid. Results from my own modified two-channel model are not being attributed to your C2 model.

A short dependency-free Python reproduction is included in the accompanying reproduce.py; the discrepancy can also be checked directly from the three states above.

Best regards,
Igor Sabirov
