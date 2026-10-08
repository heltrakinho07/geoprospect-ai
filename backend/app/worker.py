"""Durable-at-least-once PostgreSQL job dispatcher.

Requests commit target records and queue entries atomically. Separate workers
claim queue entries with SELECT FOR UPDATE SKIP LOCKED; stale leases are
recoverable after process restart. In SQLite tests, the same logic runs inline
through run_once(factory). Do not run multiple SQLite workers concurrently.

Operational scope: single-running-job per worker, 15min leases, bounded retries.
Production needs separate least-privilege queue role and distributed object store.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import sessionmaker

from .db import SessionLocal
from .models import Project, ProspectivityRun, QueueTask, RasterJob

LOG = logging.getLogger("geoprospect.worker")
LEASE_MINUTES = 15

def utcnow():
    return datetime.now(timezone.utc)

def _tenant(db, organization_id: str):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.current_org_id', :tenant, true)"),
                   {"tenant": organization_id})


def claim_task(factory=SessionLocal):
    now = utcnow()
    with factory() as db:
        q = (select(QueueTask)
             .where(
                 QueueTask.attempts < QueueTask.max_attempts,
                 QueueTask.available_at <= now,
                 or_(QueueTask.status == "queued",
                     and_(QueueTask.status == "leased",
                          QueueTask.lease_until < now)))
             .order_by(QueueTask.available_at.asc(), QueueTask.created_at.asc())
             .limit(1))
        if db.bind.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        task = db.scalar(q)
        if task is None:
            return None
        task.attempts += 1
        task.status = "leased"
        task.lease_until = now + timedelta(minutes=LEASE_MINUTES)
        data = {
            "id": task.id, "kind": task.kind, "target_id": task.target_id,
            "org_id": task.organization_id, "project_id": task.project_id,
            "attempts": task.attempts, "max_attempts": task.max_attempts
        }
        db.commit()
        return data


def _finalize(factory, task: dict, complete: bool):
    with factory() as db:
        item = db.get(QueueTask, task["id"])
        if item is None:
            return
        # A late worker cannot overwrite a newer claim after a lease timeout.
        if item.status != "leased" or item.attempts != task["attempts"]:
            return
        item.lease_until = None
        if complete:
            item.status = "done"
        elif item.attempts >= item.max_attempts:
            item.status = "dead"
            item.last_error = "Processamento esgotou as tentativas"
        else:
            item.status = "queued"
            item.available_at = utcnow() + timedelta(seconds=2)
            item.last_error = "Nova tentativa após falha"

        if not complete:
            _tenant(db, task["org_id"])
            target_cls = RasterJob if task["kind"] == "raster" else ProspectivityRun
            target = db.scalar(select(target_cls).where(
                target_cls.id == task["target_id"],
                target_cls.organization_id == task["org_id"],
                target_cls.project_id == task["project_id"]))
            if target is not None:
                target.status = "failed" if item.status == "dead" else "queued"
                if item.status == "dead":
                    target.error = "Processamento não concluído após duas tentativas."
                else:
                    target.error = None
        db.commit()


def run_once(factory=SessionLocal):
    """Process at most one committed queue task; return False when queue empty."""
    task = claim_task(factory)
    if task is None:
        return False

    try:
        with factory() as db:
            _tenant(db, task["org_id"])
            project = db.scalar(select(Project).where(
                Project.id == task["project_id"],
                Project.organization_id == task["org_id"]))
            aoi = project.aoi_geojson if project else None

        if aoi is None:
            raise ValueError("Project no longer available")
        if task["kind"] == "raster":
            from .r2 import execute_job
            execute_job(task["target_id"], task["org_id"], task["project_id"], aoi, factory)
            model = RasterJob
        elif task["kind"] == "prospectivity":
            from .r3 import execute_run
            execute_run(task["target_id"], task["org_id"], task["project_id"], aoi, factory)
            model = ProspectivityRun
        else:
            raise ValueError("Unsupported job kind")
        with factory() as db:
            _tenant(db, task["org_id"])
            final = db.scalar(select(model).where(
                model.id == task["target_id"],
                model.organization_id == task["org_id"],
                model.project_id == task["project_id"]))
            success = final is not None and final.status == "completed"
        _finalize(factory, task, success)
    except Exception:
        LOG.exception("Worker failed to process a queue entry (task id redacted)")
        _finalize(factory, task, False)
    return True


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
    LOG.info("GeoProspect durable worker started")
    while True:
        try:
            if not run_once():
                time.sleep(2)
        except Exception:
            LOG.exception("Queue lookup failed")
            time.sleep(5)

if __name__ == "__main__":
    main()
