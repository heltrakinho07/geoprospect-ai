# geoprospect-ai

**GeoProspect AI — Mineral Exploration Intelligence Platform**
Independent product by GEOLÍTHICA · Technical preview R0 / early R1.

A private-project WebGIS and FastAPI starter for managing mineral exploration areas, uploading GeoJSON layers and searching **Sentinel-2 L2A metadata** using the Copernicus STAC API. The numeric prospectivity kernel is implemented and tested but **is not yet connected to the map**.

## Features already coded

- Organization registration/login with Argon2 password hashing and 8-hour JWT; tenant-scoped project APIs.
- Project AOIs in WGS84 (EPSG:4326) with validation, polygon drawing and GeoJSON import.
- GeoJSON dataset storage and MapLibre layer display.
- Sentinel-2 L2A STAC metadata searches by AOI, date and cloud cover.
- Weighted multicriteria evidence kernel that preserves NoData.
- PostgreSQL RLS starter policies, FastAPI and React/Vite scaffolding, CI tests.

**Not implemented:** actual satellite raster download or processing, COG, mineral targeting maps, AI assistant, payments, full security hardening or validated production deployment. Example geometries are fictitious.

## Local development

Prerequisites: Docker Engine and Compose.

1. Copy the environment template: cp .env.example .env
2. Replace all placeholder passwords and JWT_SECRET with strong independent secrets.
3. Start the development stack: docker compose up --build
4. WebGIS: http://localhost:5173 ; API docs: http://localhost:8000/docs

The development stack is bound to loopback and is **not suitable for public deployment**. The database initializes with a developer bootstrap schema, not audited production migrations.

Backend tests (requires Python 3.11+ and dependencies):

    cd backend
    pip install -r requirements-dev.txt
    python -m pytest -q

Frontend build (requires Node.js 22+):

    cd frontend
    npm install
    npm run build

## Engineering documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security limitations](docs/SECURITY.md)
- [Scientific guarantees](docs/SCIENCE.md)
- [Roadmap](docs/ROADMAP.md)

## Project ownership

Independent of GeoMoz Explorer. Copyright GEOLÍTHICA. No open-source license is granted by this repository. This public repository should **never** receive commercial customer datasets, secret keys or restricted third-party software.

Repository: https://github.com/heltrakinho07/geoprospect-ai

## R2 raster pilot

Real Sentinel Hub raster requests require configured server OAuth credentials. See [R2 instructions](docs/R2_SENTINEL_PROCESSING.md). This is not yet a production worker queue.

## R3 prospectivity (pilot)

The [R3 multicriteria workflow](docs/R3_PROSPECTIVITY.md) combines a completed R2 spectral index, optional line fault evidence and mapped favorable lithologies with user-specified weights. It creates relative favorability GeoTIFF, PNG, candidate-target GeoJSON and integrity/provenance metadata. It is **not** validated mineral prediction or a resource estimate.

## R4: queued computation and sensitivity

The API commits an internal queue entry with each raster/prospectivity job. A separate worker will claim tasks with `SKIP LOCKED` and bounded retry; Docker Compose runs it separately. R3 exports `sensitivity.json` reporting ±20% relative-weight perturbations and changed threshold classifications. This is **not** a probabilistic uncertainty estimate.

### Optional Cloud Storage

Set `GCS_PRIVATE_BUCKET` on the server and worker and provide Google Cloud Application Default Credentials to activate remote private object storage. Georeferenced outputs are uploaded *before* the job completes; authenticated API requests retrieve missing artifacts from tenant-scoped prefixes. Leave it unset for Docker local volume development. The repository does not create a bucket or deploy cloud resources automatically.
