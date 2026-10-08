# R2 Sentinel-2 raster processing pilot

### Real processing and credentials

Metadata search uses the public Copernicus STAC. Spectral analysis uses the Sentinel Hub Process API, authenticating with an OAuth2 client from the Copernicus Data Space Ecosystem.

Configure the backend environment variables SENTINEL_HUB_CLIENT_ID and SENTINEL_HUB_CLIENT_SECRET. Never place these secrets in the browser or in GitHub.

Endpoints are fixed server-side:
- https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
- https://sh.dataspace.copernicus.eu/process/v1

OAuth authentication and image processing may consume your Sentinel Hub account quota.

### Processing pipeline

Select project AOI -> select index, period and maximum cloud cover -> submit -> background job retrieves GeoTIFF -> applies an AOI mask -> saves masked Float32 GeoTIFF and transparent PNG -> authenticated preview and download.

Implemented indices: NDVI, NDMI, NDWI, visible B04/B02 ratio and SWIR B11/B12 ratio. Sentinel-2 L2A reflectance samples use least-cloud-cover selection in the requested interval and mask SCL classes 0,1,3,8,9,10,11 plus dataMask.

The pilot limits output to 384 × 384 pixels, date windows to 31 days, AOI to 0.25 square degrees and eight jobs per organization per UTC day. Resampling is not improved physical sensor resolution.

### Not production ready

Jobs use FastAPI BackgroundTasks, not durable Cloud Tasks/Cloud Run Jobs. Restarting the server may interrupt jobs. Files are in a private local Docker volume, not cloud object storage. CI tests use mocked provider GeoTIFFs rather than external credentials. Production requires a distributed queue, object storage, cloud quota controls, migrations, RLS integration tests and actual credentialed smoke tests.

Ratios and indices are exploratory surface indicators; none detects ore deposits directly.
