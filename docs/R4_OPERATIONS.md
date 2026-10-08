# R4 operational architecture

## Development mode

Run docker compose up --build with the API, PostgreSQL, dedicated worker and a private raster volume. The web app submits R2 and R3 jobs as SQL rows and the worker claims them separately. The API returns a queued response without executing the job in the web request.

All API and worker processes use the same PostgreSQL database. Workers consume jobs in PostgreSQL with FOR UPDATE SKIP LOCKED; only one worker claims each queued row at a time. The claim is time-limited. On a crash a later worker may reclaim the task, so processing is at-least-once and derived artifact writes must be idempotent.

## Google Cloud deployment *blueprint*, not an executed deployment

- Host the API (FastAPI) on Cloud Run services or equivalent; use Cloud SQL PostgreSQL with PostGIS.
- Put generated GeoTIFF, PNG, GeoJSON and JSON artifacts in a private Google Cloud Storage bucket.
- Set GCS_PRIVATE_BUCKET and application-default identity credentials on both the API and worker.
- Grant the runtime service account least-privilege access to objects; keep Uniform Bucket-Level Access and Public Access Prevention configured at the bucket policy layer.
- Run python -m app.worker --once as a scheduled Cloud Run Job, or use a continuously running worker service where supported. Cloud Run Jobs require an external trigger (for example, Cloud Scheduler); merely deploying the worker image does not start an automatic queue consumer.
- Provision secrets outside Git and configure per-service identities and quotas. Do not make the storage bucket publicly readable or expose signed URLs.
- Run actual PostGIS migrations with separate privileged migration and restricted runtime identities; there is currently only a development create_all bootstrap.
- Implement periodic lease renewal/heartbeat before enabling long-running raster jobs; lease expiry may produce duplicate computations. Keep attempts bounded.
- Expand the RLS threat model: queue_tasks stores tenant identifiers in an internal cross-tenant dispatch ledger; the worker currently shares the development DB identity with the API. Use restricted SQL role/grants (or a worker-only claim service) in production.
- Configure Cloud Logging/Monitoring, dead-letter handling, retry policy, GCS bucket lifecycle, region selection and financial limits.
- Run real Copernicus OAuth smoke tests with budget/quota limits and reconcile satellite scene provenance with returned files.

This repository does not provision a cloud project, bucket, service account, Cloud Run job or database instance. The GCS adapter is tested with a fake private bucket client, not a real cloud account.

## Scientific checks

For each completed R3 run the platform generates:
- prospectivity.tif — normalized index of relative favorability.
- targets.geojson — thresholded contiguous candidate areas.
- provenance.json — parameters, dataset references and SHA-256 hashes.
- sensitivity.json — 20% positive and negative perturbation of each active normalized evidence weight.

The sensitivity report gives pixel fractions whose threshold classification changes and absolute changes to index values. It is a robustness diagnostic for subjective weights, **not an uncertainty map, mineral occurrence probability, or geological model validation**.

Field validation in Manica with checked license constraints, sample locations and deposit records is still required before commercial geological claims.
