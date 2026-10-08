"""R3 integrates real geometry rasterization with mocked upstream Sentinel files."""
import json

from app import r2
from app.worker import run_once
from .test_api import register, header
from .test_r2 import fake_tiff, AOI

def setup(client, email, name):
    user = register(client, email, name)
    org = user["organization"]["id"]
    response = client.post(f"/v1/orgs/{org}/projects", headers=header(user),
        json={"name": "Geological screening study", "aoi_geojson": AOI})
    assert response.status_code == 201, response.text
    return user,org,response.json()["id"]

def add_layer(client, user, org, project, name, features):
    response=client.post(f"/v1/orgs/{org}/projects/{project}/datasets",
        headers=header(user),json={"name":name,"geojson":{
            "type":"FeatureCollection","features":features
        }})
    assert response.status_code == 201, response.text
    return response.json()["id"]

def test_r3_complete_model_and_isolation(client,monkeypatch,tmp_path):
    user,org,project=setup(client,"geologist-r3@test.local","Mineral Client A")
    outsider,_,_=setup(client,"outsider-r3@test.local","Mineral Client B")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_ID","mock")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_SECRET","mock")
    monkeypatch.setenv("RASTER_STORAGE_DIR",str(tmp_path))
    monkeypatch.setattr(r2,"fetch_index",lambda *args:fake_tiff())
    r2_path=f"/v1/orgs/{org}/projects/{project}/raster/jobs"
    raster=client.post(r2_path,headers=header(user),json={
        "index":"ndvi","date_from":"2025-01-01","date_to":"2025-01-08"
    })
    assert raster.status_code == 202, raster.text
    raster_id=raster.json()["id"]
    assert run_once(client.test_session_factory)
    fault=add_layer(client,user,org,project,"Falhas",[
        {"type":"Feature","properties":{"name":"Fault A"},
         "geometry":{"type":"LineString","coordinates":[[32.03,-19.0],[32.03,-18.9]]}}])
    geo=add_layer(client,user,org,project,"Litologias",[
        {"type":"Feature","properties":{"unit":"mafic"},
         "geometry":{"type":"Polygon","coordinates":[[[32,-19],[32.05,-19],[32.05,-18.9],[32,-18.9],[32,-19]]]}},
        {"type":"Feature","properties":{"unit":"granitic"},
         "geometry":{"type":"Polygon","coordinates":[[[32.05,-19],[32.1,-19],[32.1,-18.9],[32.05,-18.9],[32.05,-19]]]}}
    ])
    path=f"/v1/orgs/{org}/projects/{project}/prospectivity"
    request={"raster_job_id":raster_id,"spectral_min":0,"spectral_max":1,
      "spectral_weight":2,"structural_dataset_id":fault,"structural_weight":1,
      "fault_distance_km":6,"geology_dataset_id":geo,"geology_weight":2,
      "lithology_field":"unit","favorable_values":["mafic"],
      "target_threshold":0.55,"min_target_pixels":2}
    response=client.post(path+"/runs",headers=header(user),json=request)
    assert response.status_code==202,response.text
    run_id=response.json()["id"]
    assert run_once(client.test_session_factory)
    completed=client.get(path+"/runs/"+run_id,headers=header(user))
    assert completed.status_code==200,completed.text
    outcome=completed.json()
    assert outcome["status"]=="completed",outcome
    assert outcome["stats"]["pixels_valid"]>0
    assert outcome["stats"]["targets"]>=1
    assert outcome["stats"]["inputs"]==["lithology","spectral","structure"]
    assert outcome["stats"]["weights_normalized"]["spectral"]==0.4
    targets=client.get(path+"/runs/"+run_id+"/targets",headers=header(user))
    assert targets.status_code==200
    for feature in json.loads(targets.content)["features"]:
        assert feature["properties"]["rank"]>=1
        assert feature["properties"]["area_km2"]>0
    preview=client.get(path+"/runs/"+run_id+"/preview",headers=header(user))
    raster_download=client.get(path+"/runs/"+run_id+"/geotiff",headers=header(user))
    provenance=client.get(path+"/runs/"+run_id+"/provenance",headers=header(user))
    assert provenance.status_code==200
    detail=provenance.json()
    assert detail["algorithm"]=="geoprospect_weighted_evidence_r3_v1"
    assert len(detail["output_geotiff_sha256"])==64
    assert detail["source_job_id"]==raster_id
    assert len(detail["output_sensitivity_sha256"])==64
    sensitivity=client.get(path+"/runs/"+run_id+"/sensitivity",headers=header(user))
    assert sensitivity.status_code==200
    report=sensitivity.json()
    assert len(report["scenarios"])==6
    assert 0<=report["max_threshold_flip_fraction"]<=1
    assert preview.status_code==200 and preview.content.startswith(b"\x89PNG")
    assert raster_download.status_code==200 and raster_download.content[:4] in (b"II*\x00",b"MM\x00*")
    for endpoint in ["/runs","/runs/"+run_id,"/runs/"+run_id+"/preview","/runs/"+run_id+"/targets","/runs/"+run_id+"/sensitivity"]:
        assert client.get(path+endpoint,headers=header(outsider)).status_code==404
    assert client.post(path+"/runs",headers=header(outsider),json=request).status_code==404

def test_r3_validation_and_cross_project_sources(client,monkeypatch,tmp_path):
    user,org,project=setup(client,"validation-r3@test.local","Project isolation")
    _,_,other_project=setup(client,"other-owner-r3@test.local","Another organization")
    base=f"/v1/orgs/{org}/projects/{project}/prospectivity"
    assert client.post(base+"/runs",headers=header(user),json={
      "raster_job_id":"not-uuid","spectral_min":1,"spectral_max":1}).status_code==422
    assert client.post(base+"/runs",headers=header(user),json={
      "raster_job_id":"ce5d0327-4b65-4cf4-94cb-48c711639b5c",
      "structural_weight":1}).status_code==422
    assert client.post(base+"/runs",headers=header(user),json={
      "raster_job_id":"ce5d0327-4b65-4cf4-94cb-48c711639b5c",
      "geology_dataset_id":"ce5d0327-4b65-4cf4-94cb-48c711639b5c",
      "geology_weight":1}).status_code==422
    missing=client.post(base+"/runs",headers=header(user),json={
      "raster_job_id":"ce5d0327-4b65-4cf4-94cb-48c711639b5c"})
    assert missing.status_code==422
