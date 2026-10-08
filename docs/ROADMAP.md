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

## R2 — Sentinel Hub pilot (new)
- [x] OAuth2 client credentials (server environment variables only), Process API for Sentinel-2 L2A.
- [x] NDVI, NDMI, NDWI, SWIR B11/B12 ratio and visible B04/B02 ratio; cloud SCL mask.
- [x] Background tasks with persistent tenant-scoped job records and local private GeoTIFF/PNG outputs.
- [x] Authenticated downloads, per-organization daily limit and pixel/area/time budgets.
- [ ] Production queue (Cloud Tasks/Cloud Run Jobs), object storage and recovery after server restart.
- [ ] Multi-scene selection/provenance, real provider-account smoke tests and external QA validation.

## R3 — Prospectivity Workspace pilot (outubro 2026)
- [x] Weighting of spectral GeoTIFF, fault-distance and favorable lithology with metric UTM distances.
- [x] Masked NoData intersections, GeoTIFF preview, target GeoJSON and provenance SHA-256.
- [x] Authenticated tenant-scoped jobs, results and downloads; preview in MapLibre.
- [ ] Validate real Manica datasets, method sensitivity, uncertain geology and QA/QC.
- [ ] Durable cloud jobs, migrations, backed-up object storage and production isolation checks.

## R4 — Durable worker and sensitivity (pilot)
- [x] SQL job queue, dedicated worker, atomic request+queue commit and lease recovery.
- [x] Perturbation sensitivity of normalized evidence weights (±20%) and threshold-change diagnostics.
- [ ] Production cloud object storage, lease heartbeats, least-privilege worker identity and worker telemetry.
- [ ] Geological field validation and methodology review.
