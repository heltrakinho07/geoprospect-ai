"""Sensitivity to geologist-assigned relative weights; not uncertainty probability."""
from collections.abc import Mapping
import numpy as np
from .prospectivity import weighted_evidence

def weight_sensitivity(layers: Mapping[str,np.ndarray],weights:Mapping[str,float],
                       baseline:np.ndarray,valid:np.ndarray,threshold:float,
                       delta:float=0.2)->dict:
    if not 0<delta<1 or not np.any(valid):
        raise ValueError("Invalid delta or empty valid mask")
    if len(layers)<2:
        return {"method":"one_at_a_time_renormalized","relative_perturbation":delta,
                "baseline_valid_pixels":int(valid.sum()),"scenarios":[],
                "max_threshold_flip_fraction":0.0,
                "note":"Single evidence: relative weights do not affect a normalized model"}
    scenarios=[]
    for key in layers:
        for factor in (1-delta,1+delta):
            trial=dict(weights);trial[key]*=factor
            simulated,mask=weighted_evidence(layers,trial)
            if not np.array_equal(mask,valid):
                raise ValueError("Inconsistent valid data mask")
            diff=np.abs(simulated[valid]-baseline[valid])
            flips=np.logical_xor(simulated[valid]>=threshold,baseline[valid]>=threshold)
            scenarios.append({
                "changed_weight":key,"multiplier":round(factor,3),
                "mean_abs_index_change":round(float(diff.mean()),6),
                "p95_abs_index_change":round(float(np.percentile(diff,95)),6),
                "threshold_flip_fraction":round(float(flips.mean()),6),
            })
    return {"method":"one_at_a_time_renormalized","relative_perturbation":delta,
            "baseline_valid_pixels":int(valid.sum()),"scenarios":scenarios,
            "max_threshold_flip_fraction":max(s["threshold_flip_fraction"] for s in scenarios),
            "note":"Only assumption-weight sensitivity; not calibration or geological uncertainty"}
