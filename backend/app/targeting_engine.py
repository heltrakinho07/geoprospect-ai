"""R3: auditable evidence-weighted *relative favorability* raster, not ore probability.

All geometric distance calculations take place in a local WGS84 / UTM metric CRS.
Computed scores are reprojected back to the original Sentinel scene grid for
WebGIS preview. No spectral index is treated as evidence of mineralization alone.
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, rasterize, shapes
from rasterio.transform import array_bounds
from rasterio.warp import calculate_default_transform, reproject
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape, mapping
from shapely.ops import transform as transform_geometry

from .prospectivity import weighted_evidence
from .sensitivity import weight_sensitivity
from .sentinel import NODATA
from .raster_processing import safe_job_dir

MAX_PIXELS = 1024 * 1024

class EvidenceError(ValueError):
    """User-supplied evidence cannot be evaluated consistently."""


def local_utm(aoi: dict) -> CRS:
    centroid = shape(aoi).centroid
    zone = max(1, min(60, int((centroid.x + 180) // 6) + 1))
    epsg = (32600 if centroid.y >= 0 else 32700) + zone
    if not (-80 <= centroid.y <= 84):
        raise EvidenceError("Área fora dos limites UTM do piloto científico")
    return CRS.from_epsg(epsg)


def geometries(dataset: dict, permitted: set[str], dst_crs: CRS) -> list[tuple[Any, dict]]:
    transform = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True).transform
    features = dataset.get("features", [])
    result = []
    for f in features:
        g = shape(f["geometry"])
        if g.geom_type in permitted:
            result.append((transform_geometry(transform, g), f.get("properties") or {}))
    if not result:
        raise EvidenceError("Camada não contém geometrias compatíveis com o tipo de evidência")
    return result


def _metric_raster(source: rasterio.io.DatasetReader, dst_crs: CRS) -> tuple[np.ndarray, Any]:
    tr, width, height = calculate_default_transform(
        source.crs, dst_crs, source.width, source.height, *source.bounds
    )
    if not (1 <= width * height <= MAX_PIXELS):
        raise EvidenceError("Grelha de processamento excede o limite do piloto")
    arr = np.full((height, width), NODATA, dtype="float32")
    reproject(
        source=rasterio.band(source, 1),
        destination=arr,
        src_transform=source.transform, src_crs=source.crs, src_nodata=source.nodata,
        dst_transform=tr, dst_crs=dst_crs, dst_nodata=NODATA,
        resampling=Resampling.nearest
    )
    return arr, tr


def _target_polygons(score: np.ndarray, valid: np.ndarray, transform, dst_crs: CRS,
                     threshold: float, min_pixels: int) -> dict:
    to_wgs = Transformer.from_crs(dst_crs, "EPSG:4326", always_xy=True).transform
    flag = valid & (score >= threshold)
    features = []
    if not flag.any():
        return {"type": "FeatureCollection", "features": []}
    for geometry, v in shapes(flag.astype("uint8"), mask=flag, transform=transform):
        if v != 1:
            continue
        polygon = shape(geometry)
        inside = geometry_mask([geometry], out_shape=score.shape, transform=transform, invert=True) & flag
        pixel_count = int(inside.sum())
        if pixel_count < min_pixels:
            continue
        samples = score[inside]
        features.append({
            "type": "Feature", "geometry": mapping(transform_geometry(to_wgs, polygon)),
            "properties": {
                "pixels": pixel_count,
                "area_km2": round(float(polygon.area / 1_000_000), 5),
                "mean_score": round(float(samples.mean()), 5),
                "max_score": round(float(samples.max()), 5),
                "threshold": threshold,
            }
        })
    features.sort(key=lambda f: (-f["properties"]["area_km2"], -f["properties"]["max_score"]))
    for i, feature in enumerate(features[:25], start=1):
        feature["properties"]["rank"] = i
    return {"type": "FeatureCollection", "features": features[:25]}


def analyze(source_path: Path, aoi: dict, settings: dict,
            structural_geojson: dict | None, geology_geojson: dict | None,
            organization_id: str, project_id: str, run_id: str) -> dict:
    """Combine Sentinel screening raster, faults, and mapped favorable lithologies."""
    with rasterio.open(source_path) as src:
        if src.count != 1 or not src.crs or src.nodata is None:
            raise EvidenceError("Raster de origem deve ter uma banda, CRS e NoData definidos")
        if src.width * src.height > MAX_PIXELS:
            raise EvidenceError("O raster excede o limite de pixels")
        dst_crs = local_utm(aoi)
        metric, tr = _metric_raster(src, dst_crs)
        project_utm = transform_geometry(
            Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True).transform, shape(aoi))
        inside = geometry_mask([mapping(project_utm)], out_shape=metric.shape,
                               transform=tr, invert=True)
        low, high = settings["spectral_min"], settings["spectral_max"]
        spectral = np.clip((metric.astype("float64") - low) / (high - low), 0, 1)
        if settings["spectral_invert"]:
            spectral = 1 - spectral
        spectral[(metric == NODATA) | ~np.isfinite(metric) | ~inside] = np.nan
        layers = {"spectral": spectral}
        weights = {"spectral": settings["spectral_weight"]}

        if settings["structural_dataset_id"]:
            if structural_geojson is None:
                raise EvidenceError("A camada de falhas seleccionada não existe")
            lines = geometries(structural_geojson, {"LineString", "MultiLineString"}, dst_crs)
            fault_grid = rasterize(
                [(mapping(g), 1) for g, _ in lines], out_shape=metric.shape, transform=tr,
                fill=0, dtype="uint8", all_touched=True)
            if not np.any(fault_grid):
                raise EvidenceError("Não foram encontradas falhas dentro da grelha de estudo")
            distances = distance_transform_edt(fault_grid == 0,
                                               sampling=(abs(tr.e), abs(tr.a)))
            cutoff = settings["fault_distance_km"] * 1000
            proximity = 1 - np.clip(distances / cutoff, 0, 1)
            proximity[~inside] = np.nan
            layers["structure"] = proximity
            weights["structure"] = settings["structural_weight"]

        if settings["geology_dataset_id"]:
            if geology_geojson is None:
                raise EvidenceError("A camada geológica seleccionada não existe")
            polygons = geometries(geology_geojson, {"Polygon", "MultiPolygon"}, dst_crs)
            field = settings["lithology_field"]
            if not any(field in properties for _, properties in polygons):
                raise EvidenceError("Campo de classificação ausente nos polígonos")
            shapes_all = [(mapping(g), 1) for g, _ in polygons]
            coverage = rasterize(shapes_all, out_shape=metric.shape,
                                 transform=tr, fill=0, dtype="uint8") == 1
            favorite = set(settings["favorable_values"])
            selected = [(mapping(g), 1) for g, props in polygons if str(props.get(field)) in favorite]
            if not selected:
                raise EvidenceError("Nenhum polígono corresponde às classes litológicas favoráveis")
            favorable = rasterize(
                selected,
                out_shape=metric.shape, transform=tr, fill=0, dtype="uint8") if favorite else np.zeros(metric.shape, dtype="uint8")
            lithology = favorable.astype("float64")
            lithology[~coverage | ~inside] = np.nan
            layers["lithology"] = lithology
            weights["lithology"] = settings["geology_weight"]

        score, valid = weighted_evidence(layers, weights)
        valid &= inside
        score[~valid] = np.nan
        if not valid.any():
            raise EvidenceError("As camadas não partilham pixels válidos; reveja cobertura e NoData")
        threshold = settings["target_threshold"]
        sensitivity = weight_sensitivity(layers, weights, score, valid, threshold)
        targets = _target_polygons(score, valid, tr, dst_crs, threshold, settings["min_target_pixels"])

        # Reproject the scientific result back onto the source grid for accurate WebGIS overlays.
        source_score = np.full((src.height, src.width), NODATA, dtype="float32")
        metric_score = np.where(valid, score, NODATA).astype("float32")
        reproject(
            source=metric_score, destination=source_score,
            src_transform=tr, src_crs=dst_crs, src_nodata=NODATA,
            dst_transform=src.transform, dst_crs=src.crs, dst_nodata=NODATA,
            resampling=Resampling.nearest
        )
        dest = safe_job_dir(organization_id, project_id, run_id)
        dest.mkdir(parents=True, exist_ok=True, mode=0o700)
        output = dest / "prospectivity.tif"
        profile = src.profile.copy()
        profile.update(driver="GTiff", count=1, dtype="float32",
                       nodata=NODATA, compress="deflate", tiled=False)
        profile.pop("blockxsize", None)
        profile.pop("blockysize", None)
        with rasterio.open(output, "w", **profile) as writer:
            writer.write(source_score, 1)
            writer.update_tags(
                classification="relative_favorability_index_not_mineral_probability",
                input_raster_job=settings["raster_job_id"],
                provenance=json.dumps(settings, sort_keys=True)
            )

        valid_src = (source_score != NODATA) & np.isfinite(source_score)
        stretch = np.clip(source_score, 0, 1)
        red = np.uint8(255 * stretch)
        green = np.uint8(220 * (1 - abs(2 * stretch - 1)))
        blue = np.uint8(220 * (1 - stretch))
        alpha = np.uint8(valid_src * 205)
        Image.fromarray(np.stack([red, green, blue, alpha], axis=-1), "RGBA").save(dest / "preview.png")
        (dest / "targets.geojson").write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")
        (dest / "sensitivity.json").write_text(json.dumps(sensitivity, indent=2, ensure_ascii=False), encoding="utf-8")
        provenance = {
            "algorithm": "geoprospect_weighted_evidence_r3_v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "interpretation": "relative_favorability_not_deposit_probability",
            "source_job_id": settings["raster_job_id"],
            "source_geotiff_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "parameters": settings,
            "structural_dataset_sha256": hashlib.sha256(
                json.dumps(structural_geojson, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest() if structural_geojson is not None else None,
            "geology_dataset_sha256": hashlib.sha256(
                json.dumps(geology_geojson, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest() if geology_geojson is not None else None,
            "output_geotiff_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "output_targets_sha256": hashlib.sha256((dest / "targets.geojson").read_bytes()).hexdigest(),
            "output_sensitivity_sha256": hashlib.sha256((dest / "sensitivity.json").read_bytes()).hexdigest(),
            "crs_metric": dst_crs.to_string(),
            "valid_data_fraction": round(float(valid.sum()) / max(int(inside.sum()), 1), 5),
        }
        (dest / "provenance.json").write_text(
            json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        bounds = rasterio.warp.transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        return {
            "min": round(float(score[valid].min()), 5),
            "max": round(float(score[valid].max()), 5),
            "mean": round(float(score[valid].mean()), 5),
            "valid_fraction": round(float(valid.sum()) / max(int(inside.sum()), 1), 5),
            "pixels_valid": int(valid.sum()),
            "targets": len(targets["features"]),
            "target_threshold": threshold,
            "crs": str(src.crs),
            "metric_crs": dst_crs.to_string(),
            "bounds": [float(v) for v in bounds],
            "width": src.width, "height": src.height,
            "inputs": sorted(layers),
            "weights_normalized": {k: round(v / sum(weights.values()), 6) for k, v in weights.items()},
            "sensitivity": {"scenarios":len(sensitivity["scenarios"]),"max_threshold_flip_fraction":sensitivity["max_threshold_flip_fraction"],"relative_perturbation":sensitivity["relative_perturbation"]},
            "method": "masked_weighted_linear_combination",
            "interpretation": "relative_favorability_not_deposit_probability",
        }
