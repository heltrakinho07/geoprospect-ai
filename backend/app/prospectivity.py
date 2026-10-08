"""Numeric kernel. Prospectivity index is NOT a calibrated ore probability."""
from collections.abc import Mapping
import numpy as np

def weighted_evidence(layers: Mapping[str,np.ndarray], weights: Mapping[str,float]) -> tuple[np.ndarray,np.ndarray]:
    """Combine co-registered normalized [0,1] evidence rasters; preserve NoData."""
    if not layers or set(layers) != set(weights):
        raise ValueError("Layers and weights must have identical nonempty keys")
    ws=np.array([weights[k] for k in layers],dtype="float64")
    if not np.all(np.isfinite(ws)) or np.any(ws<0) or ws.sum()<=0:
        raise ValueError("Weights must be finite, nonnegative and not all zero")
    arrays=[np.asarray(layer,dtype="float64") for layer in layers.values()]
    if any(a.shape!=arrays[0].shape for a in arrays):
        raise ValueError("Evidence rasters are not aligned")
    valid=np.logical_and.reduce([np.isfinite(a) & (a>=0) & (a<=1) for a in arrays])
    result=np.full(arrays[0].shape,np.nan,dtype="float64")
    if valid.any():
        total=np.zeros(int(valid.sum()),dtype="float64")
        for w,a in zip(ws/ws.sum(),arrays):
            total+=w*a[valid]
        result[valid]=total
    return result,valid
