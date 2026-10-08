"""R2 Sentinel raster pilot: tenant-scoped persistent jobs and protected results."""
import os
import uuid
from datetime import date
from pathlib import Path
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from sqlalchemy import select,text,func
from sqlalchemy.orm import Session,sessionmaker
from shapely.geometry import shape
from .db import SessionLocal,get_db
from .models import RasterJob,User
from .sentinel import INDEXES,credentials_available,fetch_index
from .raster_processing import safe_job_dir,process_tiff

router=APIRouter(prefix="/v1/orgs/{org_id}/projects/{project_id}/raster",tags=["Raster R2"])

class RasterRequest(BaseModel):
    index: str = Field(default="ndvi")
    date_from: date
    date_to: date
    max_cloud: int = Field(default=25,ge=0,le=100)

def use_tenant(db:Session,user:User,org_id:str,project_id:str,write:bool=False):
    # Delayed import avoids circular imports. Tenant function sets the RLS context.
    from .main import tenant_project
    return tenant_project(db,user,org_id,project_id,writable=write)

def as_public(job:RasterJob) -> dict:
    return {
        "id":job.id,"index":job.index_name,"status":job.status,
        "date_from":job.date_from.isoformat(),"date_to":job.date_to.isoformat(),
        "max_cloud":job.max_cloud,"stats":job.stats,"error":job.error,
        "created_at":job.created_at.isoformat(),
    }

def get_authorized_job(db:Session,user:User,org_id:str,project_id:str,job_id:str)->RasterJob:
    use_tenant(db,user,org_id,project_id)
    job=db.scalar(select(RasterJob).where(RasterJob.id==job_id,RasterJob.organization_id==org_id,RasterJob.project_id==project_id))
    if job is None:
        raise HTTPException(404,"Processamento não encontrado")
    return job

def execute_job(job_id:str,org_id:str,project_id:str,aoi:dict,session_factory=None) -> None:
    with (session_factory or SessionLocal)() as db:
        try:
            if db.bind.dialect.name=="postgresql":
                db.execute(text("SELECT set_config('app.current_org_id', :org, true)"),{"org":org_id})
            job=db.scalar(select(RasterJob).where(RasterJob.id==job_id,RasterJob.organization_id==org_id))
            if not job:
                return
            job.status="running"
            db.commit()
            raw=fetch_index(aoi,(job.date_from,job.date_to),job.index_name,(384,384),job.max_cloud)
            result=process_tiff(raw,aoi,org_id,project_id,job_id)
            job.stats=result
            job.status="completed"
            job.error=None
            db.commit()
        except Exception:
            db.rollback()
            if db.bind.dialect.name=="postgresql":
                db.execute(text("SELECT set_config('app.current_org_id', :org, true)"),{"org":org_id})
            failed=db.scalar(select(RasterJob).where(RasterJob.id==job_id,RasterJob.organization_id==org_id))
            if failed:
                failed.status="failed"
                failed.error="Processamento indisponível. Confirme imagens, datas e configuração do serviço."
                db.commit()
            # Do not leak provider response, client credentials or file paths.

from fastapi import Header
def authenticated(authorization:str|None=Header(default=None),db:Session=Depends(get_db)) -> User:
    from .main import current_user
    return current_user(authorization=authorization,db=db)

@router.get("/config")
def index_config(org_id:str,project_id:str,user:User=Depends(authenticated),db:Session=Depends(get_db)):
    use_tenant(db,user,org_id,project_id)
    return {"configured":credentials_available(),"indices":[{"id":k,"description":v["description"]} for k,v in INDEXES.items()],
            "limits":{"pixels":[384,384],"max_days":31,"max_bbox_deg2":0.25,"daily_jobs":8},
            "notice":"Sentinel Hub OAuth2 necessário; resultados espectrais são indicadores indirectos."}

@router.post("/jobs",status_code=202)
def create_job(org_id:str,project_id:str,data:RasterRequest,background:BackgroundTasks,user:User=Depends(authenticated),db:Session=Depends(get_db)):
    project=use_tenant(db,user,org_id,project_id,write=True)
    if not credentials_available():
        raise HTTPException(503,"Credenciais SENTINEL_HUB_CLIENT_ID e SENTINEL_HUB_CLIENT_SECRET necessárias no servidor")
    if data.index not in INDEXES:
        raise HTTPException(422,"Índice espectral não suportado")
    if data.date_to<data.date_from or (data.date_to-data.date_from).days>31:
        raise HTTPException(422,"Intervalo máximo de 31 dias")
    xmin,ymin,xmax,ymax=shape(project.aoi_geojson).bounds
    if (xmax-xmin)*(ymax-ymin)>0.25 or abs(xmax-xmin)>1 or abs(ymax-ymin)>1:
        raise HTTPException(422,"Área demasiado extensa para o processamento piloto: reduza a AOI")
    # Mitigate accidental paid-API calls; replace with durable quota ledger in enterprise phase.
    from datetime import datetime,timezone
    today=datetime.now(timezone.utc).date()
    count=db.scalar(select(func.count(RasterJob.id)).where(
        RasterJob.organization_id==org_id,RasterJob.created_at>=datetime(today.year,today.month,today.day,tzinfo=timezone.utc)))
    if count >=8:
        raise HTTPException(429,"Limite de oito processamentos diários por organização")
    job=RasterJob(organization_id=org_id,project_id=project_id,index_name=data.index,
                  date_from=data.date_from,date_to=data.date_to,max_cloud=data.max_cloud,status="queued")
    db.add(job);db.flush()
    public=as_public(job)
    db.commit()
    background.add_task(execute_job,job.id,org_id,project_id,project.aoi_geojson,sessionmaker(bind=db.get_bind(),expire_on_commit=False))
    return public

@router.get("/jobs")
def list_jobs(org_id:str,project_id:str,user:User=Depends(authenticated),db:Session=Depends(get_db)):
    use_tenant(db,user,org_id,project_id)
    records=db.scalars(select(RasterJob).where(RasterJob.organization_id==org_id,RasterJob.project_id==project_id).order_by(RasterJob.created_at.desc()).limit(40)).all()
    return [as_public(j) for j in records]

@router.get("/jobs/{job_id}")
def get_job(org_id:str,project_id:str,job_id:str,user:User=Depends(authenticated),db:Session=Depends(get_db)):
    return as_public(get_authorized_job(db,user,org_id,project_id,job_id))

@router.get("/jobs/{job_id}/{kind}")
def download_job_asset(org_id:str,project_id:str,job_id:str,kind:str,user:User=Depends(authenticated),db:Session=Depends(get_db)):
    job=get_authorized_job(db,user,org_id,project_id,job_id)
    if job.status!="completed":
        raise HTTPException(409,"Processamento ainda não concluído")
    if kind not in ("preview","geotiff"):
        raise HTTPException(404,"Formato indisponível")
    try:
        directory=safe_job_dir(org_id,project_id,job_id)
    except ValueError:
        raise HTTPException(404,"Identificador inválido")
    path=directory/("preview.png" if kind=="preview" else "index.tif")
    if not path.is_file():
        raise HTTPException(404,"Ficheiro não encontrado no armazenamento configurado")
    return FileResponse(path,media_type="image/png" if kind=="preview" else "image/tiff",
                        filename=None if kind=="preview" else job.index_name+"-"+job.id+".tif")
