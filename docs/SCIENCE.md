# Scientific rules and limitations

GeoProspect is a decision-support system for geological exploration, not a claim that satellites can directly detect gold or prove economically recoverable ore reserves.

1. Spectral alteration indicators provide *indirect* evidence about surface materials and require independent verification.
2. Preserve input provenance, quality masks, cloud conditions, acquisition dates, native resolution, sensor bands and algorithms.
3. Verify historical ASTER SWIR band availability before proposing mineral indices.
4. Weighted evidence produces a relative index, not a calibrated probability of a deposit.
5. Before combining input rasters, validate CRS, pixel size, grid, extent, normalization and NoData masks.
6. ML prospectivity training requires representative labels and spatial cross-validation; avoid spatial leakage.
7. Geology, geoochemistry, geophysics, field investigation and laboratory assays remain essential to validate targets.

Current R0/R1 code contains geometry validation and a reusable numeric kernel only. Spectral raster processing and 3D mineral models are not implemented.
