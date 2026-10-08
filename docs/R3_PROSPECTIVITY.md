# R3 Prospectivity Workspace — multicriteria pilot

This feature outputs a **relative mineral-exploration favorability index**, not mineral probability, confirmed ore reserves, or a geological resource estimate.

## Inputs

1. A **completed** R2 raster index job from the same organization AND project. Set explicit spectral min/max bounds and whether to invert the scale. These fixed limits preserve reproducibility; do not infer raw index values are probabilities.
2. Optional structural line GeoJSON dataset (LineString/MultiLineString), interpreted through distance to mapped faults, with user-defined maximum influence distance in kilometres.
3. Optional lithology polygon GeoJSON dataset (Polygon/MultiPolygon), a named attribute field, and the set of attribute values considered favorable for the geological hypothesis. Pixels outside mapped lithology coverage are *missing*, not unfavorable.

For each selected evidence provide a nonnegative weight; the spectral evidence has strictly positive weight. Weights are normalized internally to sum to one.

## Scientific workflow

- Read the source Sentinel GeoTIFF and preserve its NoData values.
- Transform the source AOI and vector layers into the local WGS84 UTM CRS (metric).
- Warp the raster into the metric reference grid; compute line distance in metres using a Euclidean distance transform on rasterized faults.
- Normalize the spectral index with the geologist's declared min/max. Geology maps 1 for favorable lithology and 0 for mapped unfavorable units.
- Intersect valid pixels for all active layers and generate the normalized weighted sum. Only one common valid pixel set is used.
- Identify contiguous pixels above the specified threshold, vectorize candidate regions and suppress areas smaller than the requested pixel count. Up to 25 largest candidates are returned.
- Reproject the resulting raster back to the original Sentinel GeoTIFF grid for MapLibre preview. Export GeoTIFF and GeoJSON with recorded parameters, weights and spatial provenance.

Because model input maps may be at different resolutions, this pilot rasterizes the vector data onto the Sentinel output grid. This is a discretized relative-index model, not a calibrated exploration model. Fault distance limited by grid resolution may obscure small faults; review scale.

## Limits and transparency

- Results cannot be treated as validated probabilities of ore occurrence.
- No supervised training or validation against known deposits at this stage.
- Performance is limited to approximately one million pixels, five inputs not yet supported, and local WGS84 UTM coverage.
- Pilot in-process jobs and local storage are not durable in distributed deployments.
- Maximum six run submissions per organization per UTC day; enterprise billing/quotas are not yet implemented.
- Validate geological favorability assumptions, lithological interpretation, QA/QC and field evidence before using targets to guide drilling.

## API

POST /v1/orgs/{organization}/projects/{project}/prospectivity/runs

GET /v1/orgs/{organization}/projects/{project}/prospectivity/runs

GET /v1/orgs/{organization}/projects/{project}/prospectivity/runs/{id}

GET /v1/orgs/{organization}/projects/{project}/prospectivity/runs/{id}/preview|geotiff|targets

Authenticated downloads are always validated against organization and project. No public raster URLs are generated.

## Proveniência verificável

Cada execução guarda o algoritmo/versionamento, os parâmetros científicos, referências do job espectral, CRS e hashes SHA-256 dos dados e artefactos GeoTIFF/GeoJSON. Exporte `provenance.json` no histórico. Hashes permitem detectar alterações em ficheiros; não garantem validade mineralógica nem identificam a origem licenciada de cada mapa.

GET /v1/orgs/{organization}/projects/{project}/prospectivity/runs/{id}/provenance
