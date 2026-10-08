"""Reproducible AOI mask, GTiff export and PNG map preview."""
import io
import os
from pathlib import Path
import numpy as np
from PIL import Image
import rasterio
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from .sentinel import NODATA

def safe_job_dir(org_id:str,project_id:str,job_id:str)->Path:
    from uuid import UUID
    # Explicit UUID parsing prevents traversal even if a future endpoint is changed.
    for v in (org_id,project_id,job_id):
        UUID(v)
    root = Path(os.getenv("RASTER_STORAGE_DIR","/tmp/geoprospect-private-rasters")).resolve()
    return root / org_id / project_id / job_id

def process_tiff(tiff_bytes:bytes,aoi:dict,org_id:str,project_id:str,job_id:str)->dict:
    with MemoryFile(tiff_bytes) as mem:
        with mem.open() as src:
            if src.count != 1 or src.width > 1024 or src.height > 1024 or not src.crs:
                raise ValueError("Resposta raster incompatível")
            data = src.read(1).astype("float32")
            inside = geometry_mask([aoi],transform=src.transform,invert=True,out_shape=data.shape)
            valid = inside & np.isfinite(data) & (data!=NODATA)
            data[~valid] = NODATA
            fraction = float(valid.sum()) / max(int(inside.sum()),1)
            if valid.sum()==0:
                raise ValueError("A análise não contém pixels válidos: reveja nuvens, datas e AOI")
            values=data[valid]
            stats={"min":round(float(values.min()),5),"max":round(float(values.max()),5),
                   "mean":round(float(values.mean()),5),"valid_fraction":round(fraction,4),
                   "pixels_valid":int(valid.sum()),"pixels_total":int(inside.sum()),
                   "crs":str(src.crs),"width":src.width,"height":src.height,
                   "bounds":[float(src.bounds.left),float(src.bounds.bottom),
                             float(src.bounds.right),float(src.bounds.top)]}
            directory=safe_job_dir(org_id,project_id,job_id)
            directory.mkdir(parents=True,exist_ok=True,mode=0o700)
            output=directory/"index.tif"
            profile=src.profile.copy()
            profile.update(driver="GTiff",count=1,dtype="float32",nodata=NODATA,compress="deflate")
            profile.pop("blockxsize",None);profile.pop("blockysize",None);profile["tiled"]=False
            with rasterio.open(output,"w",**profile) as dest:
                dest.write(data,1)
                dest.update_tags(source="Copernicus Sentinel Hub Process API",
                                 notes="Index screening; not a mineral deposit probability")
            # Fixed statistical stretch for normalized indices; robust for unconstrained ratios.
            low,high=np.percentile(values,[2,98])
            if high<=low:high=low+0.00001
            scaled=np.clip((data-low)/(high-low),0,1)
            r=np.asarray(255*scaled,dtype=np.uint8)
            b=255-r
            g=np.asarray(210*(1-np.abs(2*scaled-1)),dtype=np.uint8)
            alpha=(valid*190).astype(np.uint8)
            rgba=np.stack([r,g,b,alpha],axis=-1)
            Image.fromarray(rgba,"RGBA").save(directory/"preview.png",format="PNG")
            return stats
