"""Explicit deterministic error envelopes; no statistical significance claims."""
import numpy as np
from .plan import CONTRACT
def estimate(value,uncertainty=None,reason=None):
    value=None if value is None else float(value)
    if value is None or not np.isfinite(value):
        return dict(value=None,lower=None,upper=None,uncertainty=None,reason=reason or "nonfinite")
    if uncertainty is None:
        return dict(value=value,lower=None,upper=None,uncertainty=None,reason=reason or "no_coarse_pair")
    u=float(uncertainty)
    if not np.isfinite(u) or u<0:raise ValueError("Invalid uncertainty")
    return dict(value=value,lower=value-u,upper=value+u,uncertainty=u,reason=reason)

def linear(terms):
    if any(x["value"] is None for _,x in terms):return estimate(None,reason="undefined_operand")
    value=sum(k*x["value"] for k,x in terms)
    if any(x["uncertainty"] is None for _,x in terms):return estimate(value)
    return estimate(value,sum(abs(k)*x["uncertainty"] for k,x in terms))

def ratio(a,b,probability=False):
    floor=CONTRACT["probability_floor"] if probability else CONTRACT["primitive_absolute_floor"]
    if a["value"] is None or b["value"] is None or abs(b["value"])<=floor or (probability and b["value"]<=floor):
        return estimate(None,reason="small_denominator")
    value=a["value"]/b["value"]
    if a["uncertainty"] is None or b["uncertainty"] is None:return estimate(value)
    lo,hi=b["lower"],b["upper"]
    if lo<=0<=hi or min(abs(lo),abs(hi))<=floor or b["uncertainty"]>.1*abs(b["value"]):
        return estimate(None,reason="uncertain_denominator")
    values=[x/y for x in (a["lower"],a["upper"]) for y in (lo,hi)]
    result=estimate(value,max(value-min(values),max(values)-value))
    # Retain the true interval; the symmetric radius is only a summary.
    result.update(lower=min(values),upper=max(values))
    return result

def signed(x,eligible=True):
    if not eligible:return "INELIGIBLE"
    if x["value"] is None:return "UNDEFINED"
    if x["uncertainty"] is None:return "SCREENING_ONLY"
    if x["lower"]>0:return "RESOLVED_POSITIVE"
    if x["upper"]<0:return "RESOLVED_NEGATIVE"
    return "UNRESOLVED_AT_TOLERANCE"

def contrast(left,center,right):
    return linear([(1.,center),(-.5,left),(-.5,right)])

def sampled_minimum(left,center,right,eligible=True):
    dl=linear([(1.,left),(-1.,center)]);dr=linear([(1.,right),(-1.,center)])
    return dict(left_minus_center=dl,right_minus_center=dr,
        status="CENTER_BELOW_BOTH_SAMPLED_NEIGHBORS" if eligible and signed(dl)=="RESOLVED_POSITIVE" and signed(dr)=="RESOLVED_POSITIVE"
        else "SAMPLED_MINIMUM_NOT_RESOLVED")

