"""Worker queue lifecycle, replay and tenant-safe persisted targets."""
from datetime import timedelta
import numpy as np
from sqlalchemy import select
from app.models import QueueTask
from app.worker import claim_task,run_once,utcnow
from app.sensitivity import weight_sensitivity
from app.prospectivity import weighted_evidence
from .test_r2 import setup_project

def test_queue_persists_submission_until_worker_runs(client,monkeypatch,tmp_path):
    from app import r2
    from .test_r2 import fake_tiff
    from .test_api import header
    user,oid,pid=setup_project(client,"queue-works@test.local","Queue Co")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_ID","mock")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_SECRET","mock")
    monkeypatch.setenv("RASTER_STORAGE_DIR",str(tmp_path))
    monkeypatch.setattr(r2,"fetch_index",lambda *args:fake_tiff())
    p=f"/v1/orgs/{oid}/projects/{pid}/raster/jobs"
    r=client.post(p,headers=header(user),json={"index":"ndvi","date_from":"2025-01-01","date_to":"2025-01-04"})
    assert r.status_code==202,r.text
    assert client.get(p+"/"+r.json()["id"],headers=header(user)).json()["status"]=="queued"
    with client.test_session_factory() as db:
        tasks=db.scalars(select(QueueTask)).all()
        assert len(tasks)==1
        assert tasks[0].status=="queued" and tasks[0].attempts==0
    assert run_once(client.test_session_factory)
    assert client.get(p+"/"+r.json()["id"],headers=header(user)).json()["status"]=="completed"
    with client.test_session_factory() as db:
        task=db.scalar(select(QueueTask))
        assert task.status=="done" and task.attempts==1
    assert not run_once(client.test_session_factory)

def test_stale_lease_recovery(client,monkeypatch,tmp_path):
    from app import r2
    from .test_r2 import fake_tiff
    from .test_api import header
    user,oid,pid=setup_project(client,"queue-stale@test.local","Replay Co")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_ID","mock")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_SECRET","mock")
    monkeypatch.setenv("RASTER_STORAGE_DIR",str(tmp_path))
    monkeypatch.setattr(r2,"fetch_index",lambda *args:fake_tiff())
    p=f"/v1/orgs/{oid}/projects/{pid}/raster/jobs"
    r=client.post(p,headers=header(user),json={"index":"ndvi","date_from":"2025-01-01","date_to":"2025-01-04"})
    assert r.status_code==202
    first=claim_task(client.test_session_factory)
    assert first["attempts"]==1
    assert claim_task(client.test_session_factory) is None
    with client.test_session_factory() as db:
        task=db.get(QueueTask,first["id"])
        task.lease_until=utcnow()-timedelta(minutes=1)
        db.commit()
    assert run_once(client.test_session_factory)
    with client.test_session_factory() as db:
        task=db.get(QueueTask,first["id"])
        assert task.status=="done" and task.attempts==2

def test_weight_sensitivity_crosses_threshold():
    layers={"spectral":np.array([[0.65,0.55],[.45,np.nan]]),
            "structure":np.array([[0.2,0.9],[.9,.9]])}
    weights={"spectral":1.0,"structure":1.0}
    score,valid=weighted_evidence(layers,weights)
    report=weight_sensitivity(layers,weights,score,valid,threshold=.68)
    assert len(report["scenarios"])==4
    assert report["max_threshold_flip_fraction"]>0
    assert all(0<=s["threshold_flip_fraction"]<=1 for s in report["scenarios"])
    assert report["baseline_valid_pixels"]==3

def test_single_layer_has_no_relative_weight_sensitivity():
    layers={"spectral":np.array([[0.1,.8]])}
    score,valid=weighted_evidence(layers,{"spectral":1})
    result=weight_sensitivity(layers,{"spectral":1},score,valid,.5)
    assert not result["scenarios"] and result["max_threshold_flip_fraction"]==0
