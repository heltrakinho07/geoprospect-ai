import numpy as np
import pytest
from app.prospectivity import weighted_evidence

def test_weighted_evidence_and_nodata():
    a=np.array([[1,0],[np.nan,.6]])
    b=np.array([[0,1],[.8,.4]])
    score,valid=weighted_evidence({"structure":a,"spectral":b},{"structure":3,"spectral":1})
    assert np.isclose(score[0,0],.75)
    assert np.isclose(score[0,1],.25)
    assert np.isnan(score[1,0]) and not valid[1,0]
    assert np.isclose(score[1,1],.55)

@pytest.mark.parametrize("weights",[{"a":-1},{"a":0},{"a":float("nan")}])
def test_invalid_weights(weights):
    with pytest.raises(ValueError):
        weighted_evidence({"a":np.array([1.])},weights)

def test_mismatched_grid_rejected():
    with pytest.raises(ValueError):
        weighted_evidence({"a":np.zeros((2,2)),"b":np.zeros((2,3))},{"a":1,"b":1})
