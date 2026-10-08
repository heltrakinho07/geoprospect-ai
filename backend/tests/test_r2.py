import numpy as np
from datetime import date
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from app import r2
from app.sentinel import request_body,evalscript
from .test_api import register,header

AOI={"type":"Polygon","coordinates":[[[32,-19],[32.1,-19],[32.1,-18.9],[32,-18.9],[32,-19]]]}

def fake_tiff():
    with MemoryFile() as mem:
        with mem.open(driver="GTiff",width=32,height=32,count=1,dtype="float32",crs="EPSG:4326",
            transform=from_bounds(32,-19,32.1,-18.9,32,32)) as dest:
            image=np.full((32,32),.55,dtype="float32")
            image[:3,:]=-9999
            dest.write(image,1)
        return mem.read()

def setup_project(client,email,organization):
    user=register(client,email,organization)
    oid=user["organization"]["id"]
    p=client.post(f"/v1/orgs/{oid}/projects",headers=header(user),
        json={"name":"Sentinel pilot","aoi_geojson":AOI})
    assert p.status_code==201,p.text
    return user,oid,p.json()["id"]

def test_evalscript_request():
    for i in ("ndvi","ndmi","ndwi","swir_ratio","iron_ratio"):
        assert "dataMask" in evalscript(i) and "SCL" in evalscript(i)
    x=request_body(AOI,(date(2025,1,1),date(2025,1,8)),"ndvi",(384,384),25)
    assert x["input"]["data"][0]["type"]=="sentinel-2-l2a"
    assert x["output"]["responses"][0]["format"]["type"]=="image/tiff"

def test_raster_jobs_authorization_and_missing_creds(client,monkeypatch):
    a,oid,pid=setup_project(client,"owner-r2@test.local","First")
    b=register(client,"other-r2@test.local","Second")
    base=f"/v1/orgs/{oid}/projects/{pid}/raster"
    assert client.get(base+"/config",headers=header(b)).status_code==404
    assert len(client.get(base+"/config",headers=header(a)).json()["indices"])==5
    monkeypatch.delenv("SENTINEL_HUB_CLIENT_ID",raising=False)
    monkeypatch.delenv("SENTINEL_HUB_CLIENT_SECRET",raising=False)
    assert client.post(base+"/jobs",headers=header(a),
        json={"index":"ndvi","date_from":"2025-01-01","date_to":"2025-01-08"}).status_code==503

def test_r2_geotiff_processing_and_cross_tenant(client,monkeypatch,tmp_path):
    user,oid,pid=setup_project(client,"r2-process@test.local","Private")
    other=register(client,"r2-other@test.local","Unrelated")
    base=f"/v1/orgs/{oid}/projects/{pid}/raster"
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_ID","mock")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_SECRET","mock")
    monkeypatch.setenv("RASTER_STORAGE_DIR",str(tmp_path))
    monkeypatch.setattr(r2,"fetch_index",lambda *args:fake_tiff())
    response=client.post(base+"/jobs",headers=header(user),
        json={"index":"ndvi","date_from":"2025-01-01","date_to":"2025-01-08","max_cloud":15})
    assert response.status_code==202,response.text
    jid=response.json()["id"]
    result=client.get(base+"/jobs/"+jid,headers=header(user))
    assert result.status_code==200 and result.json()["status"]=="completed",result.text
    assert result.json()["stats"]["pixels_valid"]>0
    preview=client.get(base+"/jobs/"+jid+"/preview",headers=header(user))
    tif=client.get(base+"/jobs/"+jid+"/geotiff",headers=header(user))
    assert preview.status_code==200 and preview.content[:4]==b"\x89PNG"
    assert tif.status_code==200 and tif.content[:4] in (b"II*\x00",b"MM\x00*")
    with MemoryFile(tif.content) as mem:
        with mem.open() as d:
            assert d.nodata==-9999.0 and d.width==32
    assert client.get(base+"/jobs/"+jid,headers=header(other)).status_code==404
    assert client.get(base+"/jobs/"+jid+"/preview",headers=header(other)).status_code==404
    assert client.get(base+"/jobs",headers=header(other)).status_code==404

def test_bad_request_limits(client,monkeypatch):
    user,oid,pid=setup_project(client,"r2-validation@test.local","Limits")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_ID","mock")
    monkeypatch.setenv("SENTINEL_HUB_CLIENT_SECRET","mock")
    uri=f"/v1/orgs/{oid}/projects/{pid}/raster/jobs"
    for body in [
        {"index":"unsupported","date_from":"2025-01-01","date_to":"2025-01-08"},
        {"index":"ndvi","date_from":"2025-01-01","date_to":"2025-04-01"},
        {"index":"ndvi","date_from":"2025-04-01","date_to":"2025-01-01"}
    ]:
        assert client.post(uri,headers=header(user),json=body).status_code==422
