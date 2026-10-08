"""GCS adapter integration test with fake private object blobs (no cloud credentials)."""
import uuid
import pytest
from google.cloud import storage
from app.object_store import get_local_artifact,publish_artifacts

def test_private_cloud_publish_and_remote_cache(monkeypatch,tmp_path):
    objects={}
    class FakeBlob:
        def __init__(self,key):
            self.key=key;self.cache_control=None
        def upload_from_filename(self,filename,content_type=None,timeout=None):
            with open(filename,"rb") as stream:
                objects[self.key]=stream.read()
            assert content_type=="image/png"
            assert self.cache_control=="private, no-store"
        def download_to_filename(self,path,timeout=None):
            if self.key not in objects:
                raise FileNotFoundError("Not available in private tenant prefix")
            with open(path,"wb") as target:
                target.write(objects[self.key])
    class FakeClient:
        def bucket(self,name):
            assert name=="r4-test-private"
            class Bucket:
                def blob(self,key):
                    return FakeBlob(key)
            return Bucket()
    monkeypatch.setattr(storage,"Client",lambda:FakeClient())
    monkeypatch.setenv("GCS_PRIVATE_BUCKET","r4-test-private")
    monkeypatch.setenv("RASTER_STORAGE_DIR",str(tmp_path))
    org,project,run=[str(uuid.uuid4()) for _ in range(3)]
    file_path=get_local_artifact(org,project,run,"preview.png")
    file_path.parent.mkdir(parents=True,exist_ok=True)
    file_path.write_bytes(b"png-private")
    publish_artifacts(org,project,run,["preview.png"])
    assert len(objects)==1
    file_path.unlink()
    restored=get_local_artifact(org,project,run,"preview.png")
    assert restored.read_bytes()==b"png-private"
    other_org=str(uuid.uuid4())
    with pytest.raises(FileNotFoundError):
        get_local_artifact(other_org,project,run,"preview.png")
    with pytest.raises(ValueError):
        get_local_artifact(org,project,run,"../preview.png")
