"""True PostgreSQL RLS checks using separate superuser and runtime connections.

The job runs against a throwaway PostGIS service in GitHub Actions.
SQLite unit tests alone cannot prove RLS isolation.
"""
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.db import Base
from app.models import User, Organization, Project, Dataset, RasterJob, ProspectivityRun

ADMIN_URL=os.getenv("PG_TEST_ADMIN_URL")
RUNTIME_URL=os.getenv("PG_TEST_RUNTIME_URL")
pytestmark=pytest.mark.skipif(not (ADMIN_URL and RUNTIME_URL),
                               reason="Dedicated throwaway PostGIS service required")


def test_rls_rows_and_forbidden_writes():
    admin=create_engine(ADMIN_URL)
    runtime=create_engine(RUNTIME_URL)
    Base.metadata.create_all(admin)
    with admin.begin() as db:
        db.execute(text("CREATE ROLE gp_ci_runtime LOGIN PASSWORD 'ci-ephemeral-only'"))
        db.execute(text("GRANT USAGE ON SCHEMA public TO gp_ci_runtime"))
        db.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gp_ci_runtime"))
        script=(Path(__file__).resolve().parents[1]/"db"/"security"/"rls.sql").read_text()
        for statement in script.split(";"):
            if statement.strip():
                db.execute(text(statement))

    with Session(admin) as session:
        u=User(email="postgres-test@example.test",password_hash="test-only")
        a=Organization(name="Tenant A",slug="rls-tenant-a")
        b=Organization(name="Tenant B",slug="rls-tenant-b")
        session.add_all([u,a,b])
        session.flush()
        p1=Project(organization_id=a.id,created_by=u.id,name="A1",
                   aoi_geojson={"type":"Polygon","coordinates":[[[32,-19],[33,-19],[33,-18],[32,-18],[32,-19]]]})
        p2=Project(organization_id=b.id,created_by=u.id,name="B1",
                   aoi_geojson={"type":"Polygon","coordinates":[[[32,-19],[33,-19],[33,-18],[32,-18],[32,-19]]]})
        session.add_all([p1,p2])
        session.flush()
        for org,proj in [(a,p1),(b,p2)]:
            session.add(Dataset(organization_id=org.id,project_id=proj.id,name="Data",
                geojson={"type":"FeatureCollection","features":[]},feature_count=0))
            session.add(RasterJob(organization_id=org.id,project_id=proj.id,index_name="ndvi",
                date_from=date(2025,1,1),date_to=date(2025,1,2),max_cloud=25,status="completed"))
            session.add(ProspectivityRun(organization_id=org.id,project_id=proj.id,
                status="queued",config={"raster_job_id":str(uuid4())}))
        id_a,id_b=a.id,b.id
        project_b=p2.id
        session.commit()

    tables=("projects","datasets","raster_jobs","prospectivity_runs")
    with runtime.begin() as conn:
        for table in tables:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()==0
    with runtime.begin() as conn:
        conn.execute(text("SELECT set_config('app.current_org_id', :id, true)"),{"id":id_a})
        for table in tables:
            records=conn.execute(text(f"SELECT organization_id FROM {table}")).scalars().all()
            assert records==[id_a], (table,records)
    with runtime.begin() as conn:
        # Local GUC from the previous transaction must have expired.
        for table in tables:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()==0
        conn.execute(text("SELECT set_config('app.current_org_id', :id, true)"),{"id":id_b})
        for table in tables:
            records=conn.execute(text(f"SELECT organization_id FROM {table}")).scalars().all()
            assert records==[id_b], (table,records)

    with pytest.raises(Exception):
        with runtime.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_org_id', :id, true)"),{"id":id_a})
            conn.execute(text("INSERT INTO prospectivity_runs (id, organization_id, project_id, status, config, created_at) VALUES (:id,:org,:project,'queued','{}',now())"),
                         {"id":str(uuid4()),"org":id_b,"project":project_b})

    runtime.dispose()
    admin.dispose()
