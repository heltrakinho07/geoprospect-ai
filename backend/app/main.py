import os,re,uuid
from contextlib import asynccontextmanager
import httpx,jwt
from fastapi import Depends,FastAPI,Header,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core import check_configuration,create_token,decode_token,hash_password,verify_password
from app.db import Base,engine,get_db
from app.models import Dataset,Membership,Organization,Project,User
from app.schemas import DatasetIn,LoginIn,ProjectIn,RegisterIn,StacSearchIn
from app.spatial import validate_aoi,validate_features

@asynccontextmanager
async def lifespan(app:FastAPI):
    check_configuration()
    if os.getenv("APP_ENV","development")=="development":
        Base.metadata.create_all(bind=engine)
    yield

app=FastAPI(title="GeoProspect AI API",version="0.1.0",lifespan=lifespan)
origins=[v.strip() for v in os.getenv("CORS_ORIGINS","http://localhost:5173").split(",") if v.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type"])

def serial_project(p:Project):
    return {"id":p.id,"organization_id":p.organization_id,"name":p.name,"target_mineral":p.target_mineral,"aoi_geojson":p.aoi_geojson,"created_at":p.created_at.isoformat()}

def current_user(authorization:str|None=Header(default=None),db:Session=Depends(get_db))->User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401,"Autenticação necessária")
    try:
        uid=decode_token(authorization.removeprefix("Bearer ").strip())
    except jwt.PyJWTError as exc:
        raise HTTPException(401,"Token inválido ou expirado") from exc
    user=db.get(User,uid)
    if user is None:
        raise HTTPException(401,"Utilizador desconhecido")
    return user

def tenant_membership(db:Session,user:User,org_id:str,*,writable=False)->Membership:
    member=db.get(Membership,(org_id,user.id))
    if not member:
        raise HTTPException(404,"Organização não encontrada")
    if writable and member.role not in ("owner","admin","analyst"):
        raise HTTPException(403,"Sem permissão para modificar")
    if db.bind.dialect.name=="postgresql":
        db.execute(text("SELECT set_config('app.current_org_id', :org, true)"),{"org":org_id})
    return member

def tenant_project(db:Session,user:User,org_id:str,project_id:str,*,writable=False)->Project:
    tenant_membership(db,user,org_id,writable=writable)
    p=db.scalar(select(Project).where(Project.id==project_id,Project.organization_id==org_id))
    if not p:
        raise HTTPException(404,"Projecto não encontrado")
    return p

@app.get("/health")
def health():
    return {"status":"ok","service":"geoprospect-ai","version":"0.1.0"}

@app.get("/health/ready")
def readiness(db:Session=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503,"Base de dados indisponível") from exc
    return {"status":"ready","database":"connected"}

@app.post("/v1/auth/register",status_code=201)
def register(data:RegisterIn,db:Session=Depends(get_db)):
    if db.scalar(select(User.id).where(User.email==data.email)):
        raise HTTPException(409,"E-mail já registado")
    slug=re.sub(r"[^a-z0-9]+","-",data.organization_name.lower()).strip("-")[:70] or "org"
    user=User(email=data.email,password_hash=hash_password(data.password))
    org=Organization(name=data.organization_name.strip(),slug=f"{slug}-{uuid.uuid4().hex[:8]}")
    db.add_all([user,org])
    try:
        db.flush()
        db.add(Membership(organization_id=org.id,user_id=user.id,role="owner"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,"E-mail já registado") from exc
    return {"access_token":create_token(user.id),"token_type":"bearer","user":{"id":user.id,"email":user.email},"organization":{"id":org.id,"name":org.name}}

@app.post("/v1/auth/login")
def login(data:LoginIn,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==data.email.strip().lower()))
    if not user or not verify_password(user.password_hash,data.password):
        raise HTTPException(401,"Credenciais inválidas")
    return {"access_token":create_token(user.id),"token_type":"bearer","user":{"id":user.id,"email":user.email}}

@app.get("/v1/me")
def me(user:User=Depends(current_user),db:Session=Depends(get_db)):
    pairs=db.execute(select(Membership,Organization).join(Organization).where(Membership.user_id==user.id)).all()
    return {"id":user.id,"email":user.email,"organizations":[{"id":o.id,"name":o.name,"role":m.role} for m,o in pairs]}

@app.post("/v1/orgs/{org_id}/projects",status_code=201)
def create_project(org_id:str,data:ProjectIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    tenant_membership(db,user,org_id,writable=True)
    validate_aoi(data.aoi_geojson)
    p=Project(organization_id=org_id,name=data.name.strip(),target_mineral=data.target_mineral,aoi_geojson=data.aoi_geojson,created_by=user.id)
    db.add(p);db.flush()
    output=serial_project(p);db.commit()
    return output

@app.get("/v1/orgs/{org_id}/projects")
def list_projects(org_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    tenant_membership(db,user,org_id)
    return [serial_project(p) for p in db.scalars(select(Project).where(Project.organization_id==org_id).order_by(Project.created_at.desc())).all()]

@app.get("/v1/orgs/{org_id}/projects/{project_id}")
def get_project(org_id:str,project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return serial_project(tenant_project(db,user,org_id,project_id))

@app.post("/v1/orgs/{org_id}/projects/{project_id}/datasets",status_code=201)
def upload_geojson(org_id:str,project_id:str,data:DatasetIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    tenant_project(db,user,org_id,project_id,writable=True)
    count=validate_features(data.geojson)
    d=Dataset(organization_id=org_id,project_id=project_id,name=data.name.strip(),geojson=data.geojson,feature_count=count)
    db.add(d);db.flush()
    output={"id":d.id,"name":d.name,"feature_count":count}
    db.commit()
    return output

@app.get("/v1/orgs/{org_id}/projects/{project_id}/datasets")
def list_datasets(org_id:str,project_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    tenant_project(db,user,org_id,project_id)
    records=db.scalars(select(Dataset).where(Dataset.organization_id==org_id,Dataset.project_id==project_id).order_by(Dataset.created_at.desc())).all()
    return [{"id":d.id,"name":d.name,"geojson":d.geojson,"feature_count":d.feature_count} for d in records]

@app.post("/v1/orgs/{org_id}/stac/search")
async def search_stac(org_id:str,data:StacSearchIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    project=tenant_project(db,user,org_id,data.project_id)
    if data.date_to<data.date_from or (data.date_to-data.date_from).days>366:
        raise HTTPException(422,"Datas devem estar ordenadas e limitadas a 366 dias")
    payload={"collections":["sentinel-2-l2a"],"intersects":project.aoi_geojson,
             "datetime":f"{data.date_from.isoformat()}T00:00:00Z/{data.date_to.isoformat()}T23:59:59Z",
             "query":{"eo:cloud_cover":{"lte":data.max_cloud}},"limit":data.limit}
    try:
        async with httpx.AsyncClient(timeout=22) as client:
            response=await client.post("https://stac.dataspace.copernicus.eu/v1/search",json=payload)
            response.raise_for_status()
            catalog=response.json()
    except (httpx.HTTPError,ValueError) as exc:
        raise HTTPException(502,"Catálogo Sentinel indisponível") from exc
    features=catalog.get("features",[]) if isinstance(catalog,dict) else []
    return {"items":[{"id":f.get("id"),"datetime":f.get("properties",{}).get("datetime"),"cloud_cover":f.get("properties",{}).get("eo:cloud_cover"),"bbox":f.get("bbox"),"collection":f.get("collection")} for f in features[:data.limit]],"note":"Apenas metadados; processamento raster em R2."}

# R2 routes are isolated from R0 API resources.
from app.r2 import router as raster_router
app.include_router(raster_router)

from app.r3 import router as prospectivity_router
app.include_router(prospectivity_router)
