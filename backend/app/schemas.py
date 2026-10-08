from datetime import date
from typing import Any
from pydantic import BaseModel, Field, field_validator

class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=160)
    @field_validator("email")
    @classmethod
    def email_normalization(cls,v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or "." not in v.split("@")[-1]:
            raise ValueError("Endereço de e-mail inválido")
        return v

class LoginIn(BaseModel):
    email: str
    password: str

class ProjectIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    target_mineral: str | None = Field(default=None, max_length=100)
    aoi_geojson: dict[str, Any]

class DatasetIn(BaseModel):
    name: str = Field(min_length=2,max_length=200)
    geojson: dict[str, Any]

class StacSearchIn(BaseModel):
    project_id: str
    date_from: date
    date_to: date
    max_cloud: int = Field(default=25,ge=0,le=100)
    limit: int = Field(default=15,ge=1,le=30)
