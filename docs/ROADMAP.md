# Development roadmap

## R0 — SaaS foundation
- [x] Independent repository, backend, UI and local container setup.
- [x] Registration, login, organizations, project-scoped APIs and basic tests.
- [x] Initial PostgreSQL RLS policies.
- [ ] Separate migration and runtime roles, real PostGIS isolation tests, MFA and audit.

## R1 — WebGIS
- [x] AOI drawing, project persistence, GeoJSON datasets, map rendering.
- [x] Copernicus STAC Sentinel-2 metadata search.
- [ ] GeoPackage, zipped Shapefile, GeoTIFF/COG import, private object storage and versioned catalogs.

## R2 — Remote sensing engine
- [ ] Sentinel-2 reflectance download, quality masks, indices, raster QA and STAC provenance.
- [ ] Async processing workers, raster alignment, COG output, secured tile delivery.

## R3 — Targeting
- [x] NoData-aware weighted evidence numeric algorithm (not exposed via map).
- [ ] Multi-source geoscience prospectivity, sensitivity analysis, classified targets and evidence reports.
- [ ] Validation using real reference studies and field data.

## R4 — AI / ML
- [ ] Authorized geoscience tool registry, auditable assistant, tenant-scoped RAG.
- [ ] Supervised ML with proper spatial validation and uncertainty reporting.
