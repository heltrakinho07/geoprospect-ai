from fastapi import HTTPException
from shapely.geometry import shape
from shapely.validation import explain_validity

def validate_aoi(geom: dict) -> dict:
    if not isinstance(geom,dict) or geom.get("type") not in ("Polygon","MultiPolygon"):
        raise HTTPException(422,"AOI deve ser Polygon ou MultiPolygon GeoJSON")
    if len(str(geom)) > 150_000:
        raise HTTPException(413,"Geometria demasiado grande")
    try:
        g = shape(geom)
        if g.is_empty or not g.is_valid or g.area <= 0:
            raise ValueError(explain_validity(g))
        xmin,ymin,xmax,ymax = g.bounds
        if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
            raise ValueError("As coordenadas devem usar EPSG:4326")
    except (TypeError,ValueError,KeyError,IndexError) as exc:
        raise HTTPException(422,f"AOI inválida: {exc}") from exc
    return geom

def validate_features(collection: dict) -> int:
    if not isinstance(collection,dict) or collection.get("type") != "FeatureCollection":
        raise HTTPException(422,"Esperado GeoJSON FeatureCollection")
    features=collection.get("features")
    if not isinstance(features,list) or not 1 <= len(features) <= 1000:
        raise HTTPException(422,"Importe entre 1 e 1000 feições")
    if len(str(collection)) > 2_000_000:
        raise HTTPException(413,"GeoJSON demasiado grande")
    for feature in features:
        try:
            geom=shape(feature["geometry"])
            if geom.is_empty or not geom.is_valid:
                raise ValueError("Geometria vazia ou inválida")
            xmin,ymin,xmax,ymax=geom.bounds
            if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
                raise ValueError("Coordenadas fora de EPSG:4326")
        except (TypeError,ValueError,KeyError,IndexError) as exc:
            raise HTTPException(422,f"Feição GeoJSON inválida: {exc}") from exc
    return len(features)
