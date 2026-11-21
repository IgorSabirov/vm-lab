"""First-contact geometry for P7's Poisson events with one shared growth law."""
import numpy as np


def first_contacts(events, times, wall_distance, box_size):
    """Use time_s, chi in comoving cm, and a periodic cube of side box_size cm.

    events is the result of pockets.sample_nucleations. The caller supplies the
    wall distance from pockets.avrami_geometry on the same history. Output rows
    keep the original birth index. A null contact is censored at times[-1].
    """
    t, chi = np.asarray(times, float), np.asarray(wall_distance, float)
    births = np.asarray(events["birth_time_s"], float)
    centers = np.asarray(events["centers_comoving_cm"], float)
    if (t.ndim != 1 or len(t) < 2 or t.shape != chi.shape or np.any(np.diff(t) <= 0)
            or np.any(np.diff(chi) < 0) or not np.isfinite(box_size) or box_size <= 0
            or not np.isfinite(t).all() or not np.isfinite(chi).all()):
        raise ValueError("Expected a common, monotone comoving wall distance and time grid")
    if (births.ndim != 1 or centers.shape != (len(births), 3)
            or not np.isfinite(centers).all() or not np.isfinite(births).all()
            or np.any((births < t[0]) | (births > t[-1])) or np.any(np.diff(births) < 0)):
        raise ValueError("Expected ordered events inside the retained time interval")
    birth_chi = np.interp(births, t, chi)
    if len(births) and 2*(chi[-1]-birth_chi[0]) >= box_size:
        raise ValueError("Enlarge the box or shorten the interval to exclude self-image contact")
    accepted = []
    contact_chi = np.full(len(births), np.inf)
    for j, value in enumerate(birth_chi):
        delta = centers[accepted] - centers[j]
        delta -= box_size * np.rint(delta / box_size)
        distance = np.linalg.norm(delta, axis=1)
        if np.any(distance <= value - birth_chi[accepted]):
            continue
        # With common chi(t), a covered candidate cannot outrun its parent.
        contact = (distance + value + birth_chi[accepted])/2
        contact_chi[accepted] = np.minimum(contact_chi[accepted], contact)
        if len(contact):
            contact_chi[j] = contact.min()
        accepted.append(j)

    rows = []
    for j in accepted:
        target = contact_chi[j]
        contact_time = None
        if target <= chi[-1]:
            # First arrival, including a plateau at exactly the contact distance.
            i = np.searchsorted(chi, target, side="left")
            contact_time = float(t[i] if chi[i] == target else
                                 np.interp(target, chi[i-1:i+1], t[i-1:i+1]))
        rows.append({"event_index": j, "birth_time_s": float(births[j]),
                     "first_contact_time_s": contact_time,
                     "comoving_radius_at_contact_cm":
                         float(target-birth_chi[j]) if contact_time is not None else None})
    return rows
