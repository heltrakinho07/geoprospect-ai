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
