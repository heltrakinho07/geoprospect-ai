"""Sentinel Hub Process API client: fixed endpoints, server-owned credentials.

This is *reflectance-index screening*, not direct mineral detection.
"""
from datetime import date
import os
import httpx

TOKEN_ENDPOINT = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_ENDPOINT = "https://sh.dataspace.copernicus.eu/process/v1"
NODATA = -9999.0

INDEXES = {
    "ndvi": {"description": "Vegetation index (B08/B04)", "expression": "(s.B08 - s.B04) / Math.max(s.B08 + s.B04, 0.000001)", "bands": ["B08", "B04"]},
    "ndmi": {"description": "Moisture index (B08/B11)", "expression": "(s.B08 - s.B11) / Math.max(s.B08 + s.B11, 0.000001)", "bands": ["B08", "B11"]},
    "ndwi": {"description": "Water index (B03/B08)", "expression": "(s.B03 - s.B08) / Math.max(s.B03 + s.B08, 0.000001)", "bands": ["B03", "B08"]},
    "swir_ratio": {"description": "SWIR B11/B12 screening ratio", "expression": "s.B11 / Math.max(s.B12, 0.000001)", "bands": ["B11", "B12"]},
    "iron_ratio": {"description": "Visible B04/B02 screening ratio", "expression": "s.B04 / Math.max(s.B02, 0.000001)", "bands": ["B04", "B02"]},
}

class SentinelConfigurationError(RuntimeError):
    pass

class SentinelProcessingError(RuntimeError):
    pass

def credentials_available() -> bool:
    return bool(os.getenv("SENTINEL_HUB_CLIENT_ID") and os.getenv("SENTINEL_HUB_CLIENT_SECRET"))

def evalscript(index: str) -> str:
    cfg = INDEXES[index]
    inputs = list(dict.fromkeys(cfg["bands"] + ["SCL", "dataMask"]))
    return (
        "//VERSION=3\n"
        "function setup() { return { input: " + str(inputs).replace("'", '"') +
        ', output: {bands: 1, sampleType: "FLOAT32"} }; }\n'
        "function evaluatePixel(s) {\n"
        " if (!s.dataMask || [0,1,3,8,9,10,11].includes(s.SCL)) return [-9999];\n"
        " const value = " + cfg["expression"] + ";\n"
        " return [Number.isFinite(value) ? value : -9999];\n"
        "}\n"
    )

def request_body(aoi: dict, interval: tuple[date,date], index: str, size: tuple[int,int], cloud: int) -> dict:
    from shapely.geometry import shape
    xmin,ymin,xmax,ymax = shape(aoi).bounds
    return {
        "input": {
            "bounds": {"bbox": [xmin,ymin,xmax,ymax],
                       "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
                       "geometry": aoi},
            "data": [{"type": "sentinel-2-l2a",
                      "dataFilter": {"timeRange": {"from": interval[0].isoformat()+"T00:00:00Z",
                                                 "to": interval[1].isoformat()+"T23:59:59Z"},
                                     "maxCloudCoverage": cloud, "mosaickingOrder":"leastCC"}}]},
        "output": {"width": size[0], "height": size[1],
                   "responses":[{"identifier":"default","format":{"type":"image/tiff"}}]},
        "evalscript": evalscript(index),
    }

def fetch_index(aoi: dict, interval: tuple[date,date], index: str, size: tuple[int,int], cloud: int) -> bytes:
    """Obtain georeferenced TIFF pixels from a real Sentinel Hub request."""
    client_id = os.getenv("SENTINEL_HUB_CLIENT_ID")
    secret = os.getenv("SENTINEL_HUB_CLIENT_SECRET")
    if not client_id or not secret:
        raise SentinelConfigurationError("Credenciais Sentinel Hub não configuradas")
    try:
        with httpx.Client(timeout=httpx.Timeout(75,connect=12),follow_redirects=False) as client:
            token_response = client.post(TOKEN_ENDPOINT, data={
                "grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
            token_response.raise_for_status()
            access_token=token_response.json().get("access_token")
            if not access_token or not isinstance(access_token,str):
                raise SentinelProcessingError("Resposta OAuth inválida")
            response = client.post(PROCESS_ENDPOINT,
                headers={"Authorization": "Bearer "+access_token, "Accept": "image/tiff"},
                json=request_body(aoi,interval,index,size,cloud))
            response.raise_for_status()
            if len(response.content) > 16_000_000 or not response.content[:4] in (b"II*\x00", b"MM\x00*"):
                raise SentinelProcessingError("Resposta raster inválida ou demasiado grande")
            return response.content
    except (httpx.HTTPError,ValueError) as exc:
        # Do not include provider response bodies, tokens or secrets in the API response.
        raise SentinelProcessingError("O serviço Sentinel Hub não conseguiu fornecer os dados") from exc
