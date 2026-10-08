"""Optional private Cloud Storage for raster artifacts.

All API calls authenticate and authorize tenant/project *before* invoking
get_local_artifact. GCS objects are never public; no signed external download
URLs are returned. Uses service-account ADC; never client credentials.
"""
from __future__ import annotations
import os
from pathlib import Path

from .raster_processing import safe_job_dir

MIME={
    "index.tif":"image/tiff",
    "prospectivity.tif":"image/tiff",
    "preview.png":"image/png",
    "targets.geojson":"application/geo+json",
    "provenance.json":"application/json",
    "sensitivity.json":"application/json",
}

def _bucket_name():
    return os.getenv("GCS_PRIVATE_BUCKET","").strip()

def _blob(organization_id:str,project_id:str,run_id:str,filename:str):
    if filename not in MIME:
        raise ValueError("Unsupported artifact type")
    # Validate all UUIDs, precluding GCS-prefix injection and filesystem traversal.
    safe_job_dir(organization_id,project_id,run_id)
    from google.cloud import storage
    bucket=storage.Client().bucket(_bucket_name())
    object_name=f"organizations/{organization_id}/projects/{project_id}/runs/{run_id}/{filename}"
    return bucket.blob(object_name)

def publish_artifacts(organization_id:str,project_id:str,run_id:str,filenames:list[str]):
    """Upload output files before marking their job as completed."""
    if not _bucket_name():
        return
    directory=safe_job_dir(organization_id,project_id,run_id)
    for filename in filenames:
        if filename not in MIME:
            raise ValueError("Unsupported artifact type")
        local=directory/filename
        if not local.is_file():
            raise FileNotFoundError("Artifact missing before upload")
        blob=_blob(organization_id,project_id,run_id,filename)
        blob.cache_control="private, no-store"
        blob.upload_from_filename(str(local),content_type=MIME[filename],
                                  timeout=90)

def get_local_artifact(organization_id:str,project_id:str,run_id:str,filename:str)->Path:
    """Hydrate a local private cache from GCS when API and worker do not share disk."""
    if filename not in MIME:
        raise ValueError("Unsupported artifact type")
    target=safe_job_dir(organization_id,project_id,run_id)/filename
    if target.is_file():
        return target
    if not _bucket_name():
        return target
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=target.with_suffix(target.suffix+".partial")
    try:
        _blob(organization_id,project_id,run_id,filename).download_to_filename(str(temp),timeout=90)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target
