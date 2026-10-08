"""R3 pilot: tenant-scoped, evidence-traceable multicriteria prospectivity."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db
from .models import Dataset, ProspectivityRun, QueueTask, RasterJob, User
from .raster_processing import safe_job_dir
from .targeting_engine import EvidenceError, analyze

router = APIRouter(prefix="/v1/orgs/{org_id}/projects/{project_id}/prospectivity",
                   tags=["Mineral prospectivity R3"])


class ProspectivityRequest(BaseModel):
    raster_job_id: str
    spectral_min: float = Field(default=-1, ge=-1000, le=1000)
    spectral_max: float = Field(default=1, ge=-1000, le=1000)
    spectral_invert: bool = False
    spectral_weight: float = Field(default=1, gt=0, le=100)
    structural_dataset_id: str | None = None
    structural_weight: float = Field(default=0, ge=0, le=100)
    fault_distance_km: float = Field(default=3, gt=0, le=100)
    geology_dataset_id: str | None = None
    geology_weight: float = Field(default=0, ge=0, le=100)
    lithology_field: str = Field(default="lithology", min_length=1, max_length=100)
    favorable_values: list[str] = Field(default_factory=list, max_length=30)
    target_threshold: float = Field(default=0.7, ge=0.05, le=1)
    min_target_pixels: int = Field(default=5, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_model(self):
        if self.spectral_min >= self.spectral_max:
            raise ValueError("Intervalo espectral inválido: máximo deve exceder mínimo")
        if bool(self.structural_dataset_id) != (self.structural_weight > 0):
            raise ValueError("Evidência estrutural requer uma camada e peso positivo")
        if bool(self.geology_dataset_id) != (self.geology_weight > 0):
            raise ValueError("Evidência geológica requer uma camada e peso positivo")
        if self.geology_dataset_id and not self.favorable_values:
            raise ValueError("Seleccione ao menos um valor litológico favorável")
        if any(not v.strip() or len(v) > 120 for v in self.favorable_values):
            raise ValueError("Valor litológico inválido")
        for identifier in (self.raster_job_id, self.structural_dataset_id, self.geology_dataset_id):
            if identifier:
                try:
                    UUID(identifier)
                except ValueError as exc:
                    raise ValueError("Identificador de camada inválido") from exc
        return self


def authenticated(authorization: str | None = Header(default=None),
                  db: Session = Depends(get_db)) -> User:
    from .main import current_user
    return current_user(authorization=authorization, db=db)


def scoped_project(db: Session, user: User, org_id: str, project_id: str, *, write=False):
    from .main import tenant_project
    return tenant_project(db, user, org_id, project_id, writable=write)


def get_scoped_run(db: Session, user: User, org_id: str,
                   project_id: str, run_id: str) -> ProspectivityRun:
    scoped_project(db, user, org_id, project_id)
    run = db.scalar(select(ProspectivityRun).where(
        ProspectivityRun.id == run_id, ProspectivityRun.organization_id == org_id,
        ProspectivityRun.project_id == project_id))
    if run is None:
        raise HTTPException(404, "Modelo de prospectividade não encontrado")
    return run


def response_data(run: ProspectivityRun) -> dict:
    return {
        "id": run.id, "status": run.status, "config": run.config, "stats": run.stats,
        "error": run.error, "created_at": run.created_at.isoformat(),
    }


def execute_run(run_id: str, org_id: str, project_id: str, aoi: dict,
                session_factory=None) -> None:
    with (session_factory or SessionLocal)() as db:
        try:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": org_id})
            run = db.scalar(select(ProspectivityRun).where(
                ProspectivityRun.id == run_id, ProspectivityRun.organization_id == org_id,
                ProspectivityRun.project_id == project_id))
            if not run:
                return
            cfg = dict(run.config)
            source = db.scalar(select(RasterJob).where(
                RasterJob.id == cfg["raster_job_id"], RasterJob.organization_id == org_id,
                RasterJob.project_id == project_id, RasterJob.status == "completed"))
            if source is None:
                raise EvidenceError("Raster espectral não encontrado ou incompleto")
            vector_data = {}
            for key in ("structural_dataset_id", "geology_dataset_id"):
                if cfg.get(key):
                    dataset = db.scalar(select(Dataset).where(
                        Dataset.id == cfg[key], Dataset.organization_id == org_id,
                        Dataset.project_id == project_id))
                    if not dataset:
                        raise EvidenceError("Camada de evidência não encontrada")
                    vector_data[key] = dataset.geojson

            run.status = "running"
            db.commit()
            input_tiff = safe_job_dir(org_id, project_id, source.id) / "index.tif"
            if not input_tiff.is_file():
                raise EvidenceError("O GeoTIFF de origem não está disponível no armazenamento")
            stats = analyze(input_tiff, aoi, cfg,
                            vector_data.get("structural_dataset_id"),
                            vector_data.get("geology_dataset_id"),
                            org_id, project_id, run_id)
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": org_id})
            run.stats = stats
            run.status = "completed"
            run.error = None
            db.commit()
        except Exception:
            # Never expose secret provider diagnostics or file paths to web clients.
            db.rollback()
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": org_id})
            failed = db.scalar(select(ProspectivityRun).where(
                ProspectivityRun.id == run_id, ProspectivityRun.organization_id == org_id,
                ProspectivityRun.project_id == project_id))
            if failed:
                failed.status = "failed"
                failed.error = "Não foi possível combinar as evidências; confirme as camadas, cobertura e parâmetros."
                db.commit()


@router.get("/config")
def config(org_id: str, project_id: str,
           user: User = Depends(authenticated), db: Session = Depends(get_db)):
    scoped_project(db, user, org_id, project_id)
    return {"method": "weighted_linear_combination",
            "max_runs_per_org_per_day": 6,
            "description": "Índice relativo de favorabilidade, não probabilidade de depósito."}


@router.post("/runs", status_code=202)
def create_run(org_id: str, project_id: str, data: ProspectivityRequest,
               user: User = Depends(authenticated),
               db: Session = Depends(get_db)):
    project = scoped_project(db, user, org_id, project_id, write=True)
    raster = db.scalar(select(RasterJob).where(
        RasterJob.id == data.raster_job_id,
        RasterJob.organization_id == org_id, RasterJob.project_id == project_id,
        RasterJob.status == "completed"))
    if not raster:
        raise HTTPException(422, "Seleccione um raster concluído deste projecto")

    for key in ("structural_dataset_id", "geology_dataset_id"):
        dataset_id = getattr(data, key)
        if dataset_id:
            record = db.scalar(select(Dataset).where(
                Dataset.id == dataset_id, Dataset.organization_id == org_id,
                Dataset.project_id == project_id))
            if not record:
                raise HTTPException(422, "A camada seleccionada não pertence ao projecto")

    utc = datetime.now(timezone.utc)
    count = db.scalar(select(func.count(ProspectivityRun.id)).where(
        ProspectivityRun.organization_id == org_id,
        ProspectivityRun.created_at >= utc.replace(hour=0, minute=0, second=0, microsecond=0)))
    if count >= 6:
        raise HTTPException(429, "Limite diário de seis modelos por organização")
    run = ProspectivityRun(organization_id=org_id, project_id=project_id,
                           status="queued", config=data.model_dump())
    db.add(run)
    db.flush()
    db.add(QueueTask(organization_id=org_id,project_id=project_id,kind="prospectivity",target_id=run.id))
    response = response_data(run)
    db.commit()
    return response


@router.get("/runs")
def list_runs(org_id: str, project_id: str,
              user: User = Depends(authenticated), db: Session = Depends(get_db)):
    scoped_project(db, user, org_id, project_id)
    runs = db.scalars(select(ProspectivityRun).where(
        ProspectivityRun.organization_id == org_id,
        ProspectivityRun.project_id == project_id
    ).order_by(ProspectivityRun.created_at.desc()).limit(40)).all()
    return [response_data(r) for r in runs]


@router.get("/runs/{run_id}")
def read_run(org_id: str, project_id: str, run_id: str,
             user: User = Depends(authenticated), db: Session = Depends(get_db)):
    return response_data(get_scoped_run(db, user, org_id, project_id, run_id))


@router.get("/runs/{run_id}/{kind}")
def download_run(org_id: str, project_id: str, run_id: str, kind: str,
                 user: User = Depends(authenticated), db: Session = Depends(get_db)):
    run = get_scoped_run(db, user, org_id, project_id, run_id)
    files = {"preview": ("preview.png", "image/png"),
             "geotiff": ("prospectivity.tif", "image/tiff"),
             "targets": ("targets.geojson", "application/geo+json"),
             "provenance": ("provenance.json", "application/json"),
             "sensitivity": ("sensitivity.json", "application/json")}
    if kind not in files:
        raise HTTPException(404, "Formato indisponível")
    if run.status != "completed":
        raise HTTPException(409, "Modelo ainda não concluído")
    try:
        folder = safe_job_dir(org_id, project_id, run_id)
    except ValueError:
        raise HTTPException(404, "Identificador inválido")
    filename, media_type = files[kind]
    path = folder / filename
    if not path.is_file():
        raise HTTPException(404, "Ficheiro não encontrado")
    return FileResponse(path, media_type=media_type,
                        filename=None if kind == "preview" else filename)
