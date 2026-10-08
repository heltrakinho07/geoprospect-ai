# Architecture — GeoProspect AI R0/R1

GeoProspect is independent of GeoMoz Explorer; no GeoMoz runtime is required.

- Frontend: React + TypeScript + MapLibre + Vite.
- API: FastAPI with per-organization membership checks.
- Database: PostgreSQL/PostGIS for local Docker development; SQLite used only in tests.
- Authentication: Argon2 password hashing, JWT development flow; production sessions and MFA still required.
- Spatial input: WGS84 AOI, GeoJSON datasets, Shapely geometry validation.
- Earth observation: fixed Copernicus Data Space STAC endpoint returning Sentinel-2 L2A scene metadata.
- Scientific kernel: NumPy weighted combination of normalized evidence rasters (not yet used by the map).

## Planned components

Versioned project datasets, private object storage, COG raster tiles, STAC catalogs, TiTiler with tenant authorization, geoscience QA/QC, asynchronous worker jobs, cost limits and auditable job provenance.

## Deployment disclaimer

The supplied Docker Compose setup is intended for local development. Production must separate migration/runtime database roles, use properly tested PostgreSQL RLS, encrypt storage, implement organization-scoped object access, backups, rate limiting and central logging.
