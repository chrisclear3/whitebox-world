"""Dependency-free GeoJSON/OSM import into a small, metre-based scene schema.

The scene axes are X=east, Y=north, Z=up. Geographic coordinates and ``origin``
are always ordered (longitude, latitude). Projection is local equirectangular,
appropriate for neighbourhood-sized scenes, not large regions. Building height
is the roof elevation above ground; min_height is the bottom elevation.

GeoJSON may declare ``"coordinate_system": "local"`` at collection level.
Otherwise auto mode honors a WGS84 CRS, or infers geographic coordinates if all
positions fit longitude/latitude ranges. Small local coordinates are ambiguous;
declare local explicitly. Exterior footprints are returned without a repeated
closing point, counterclockwise. Interior rings are intentionally not modelled.
Recoverable input problems are listed in the returned ``warnings`` list.
Explicit tree, power pole/tower and traffic-signal points are preserved in
``street_features`` as kind, point (local metres), osm_id and source tags.
Missing point features remain absent; decorative placements are not inferred.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET


EARTH_RADIUS_M = 6_371_008.8
DEFAULT_BUILDING_HEIGHT = 9.0
LEVEL_HEIGHT = 3.0
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright"
_ROAD_WIDTHS = {
    "motorway": 14.0, "trunk": 12.0, "primary": 10.0, "secondary": 9.0,
    "tertiary": 8.0, "residential": 6.0, "unclassified": 6.0,
    "living_street": 5.0, "service": 4.0, "track": 3.0,
    "footway": 2.0, "path": 2.0, "cycleway": 2.0, "pedestrian": 4.0,
    "steps": 2.0,
}
_LENGTH = re.compile(
    r"^\s*([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+))\s*"
    r"(m|metres?|meters?|ft|feet|foot|'|cm|mm)?\s*$", re.IGNORECASE
)
_FEET_INCHES = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:'|ft|feet)\s*"
    r"(\d+(?:\.\d+)?)\s*(?:\"|in|inches?)\s*$", re.IGNORECASE
)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def parse_length(value: Any, default: float | None = None) -> float | None:
    """Parse non-negative metres, feet, or feet/inches; return default on failure."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = _finite_number(value)
    elif isinstance(value, str):
        feet_inches = _FEET_INCHES.fullmatch(value)
        if feet_inches:
            feet, inches = map(float, feet_inches.groups())
            number = feet * 0.3048 + inches * 0.0254
        else:
            match = _LENGTH.fullmatch(value)
            if not match:
                return default
            number = float(match.group(1).replace(",", "."))
            unit = (match.group(2) or "m").lower()
            if unit in {"ft", "feet", "foot", "'"}:
                number *= 0.3048
            elif unit == "cm":
                number *= 0.01
            elif unit == "mm":
                number *= 0.001
    else:
        return default
    return number if number is not None and math.isfinite(number) and number >= 0 else default


def _position(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    x, y = _finite_number(value[0]), _finite_number(value[1])
    return [x, y] if x is not None and y is not None else None


def _validate_origin(origin: Any) -> list[float]:
    result = _position(origin)
    if result is None or not (-180 <= result[0] <= 180 and -90 < result[1] < 90):
        raise ValueError("origin must be (longitude, latitude), with -180 <= lon <= 180 and -90 < lat < 90")
    return result


def project_lonlat(lon: float, lat: float, origin: tuple | list) -> list[float]:
    """Project WGS84 lon/lat into east/north metres relative to origin."""
    lon0, lat0 = _validate_origin(origin)
    point = _position([lon, lat])
    if point is None or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
        raise ValueError("WGS84 position is outside longitude/latitude bounds")
    delta_lon = (point[0] - lon0 + 180.0) % 360.0 - 180.0
    return [EARTH_RADIUS_M * math.radians(delta_lon) * math.cos(math.radians(lat0)),
            EARTH_RADIUS_M * math.radians(point[1] - lat0)]


def _system(value: str) -> str:
    normalized = str(value).lower().replace(" ", "")
    aliases = {"local": "local", "meters": "local", "metres": "local", "m": "local",
               "wgs84": "wgs84", "epsg:4326": "wgs84", "lonlat": "wgs84",
               "geographic": "wgs84", "auto": "auto"}
    if normalized not in aliases:
        raise ValueError("coordinate_system must be 'auto', 'local', or 'wgs84'")
    return aliases[normalized]


def _walk_positions(coordinates: Any):
    if not isinstance(coordinates, (list, tuple)):
        return
    if len(coordinates) >= 2 and not isinstance(coordinates[0], (list, tuple)):
        point = _position(coordinates)
        if point is not None:
            yield point
    else:
        for child in coordinates:
            yield from _walk_positions(child)


def _centroid_origin(positions: list[list[float]]) -> list[float]:
    if not positions:
        return [0.0, 0.0]
    # Circular longitude mean also works for a neighbourhood at the date line.
    longitude = math.degrees(math.atan2(
        sum(math.sin(math.radians(p[0])) for p in positions),
        sum(math.cos(math.radians(p[0])) for p in positions)))
    latitude = (min(p[1] for p in positions) + max(p[1] for p in positions)) / 2
    return _validate_origin([longitude, latitude])


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a, b, c, d):
    signs = (_cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b))
    if ((signs[0] > 0 > signs[1] or signs[1] > 0 > signs[0]) and
            (signs[2] > 0 > signs[3] or signs[3] > 0 > signs[2])):
        return True
    for value, p, q, r in ((signs[0], c, a, b), (signs[1], d, a, b),
                           (signs[2], a, c, d), (signs[3], b, c, d)):
        if abs(value) < 1e-10 and (min(q[0], r[0]) <= p[0] <= max(q[0], r[0]) and
                                   min(q[1], r[1]) <= p[1] <= max(q[1], r[1])):
            return True
    return False


def _clean_points(raw, transform, polygon, label, warnings):
    if not isinstance(raw, (list, tuple)):
        warnings.append(f"{label}: skipped malformed coordinate list")
        return None
    points = []
    for position in raw:
        point = _position(position)
        if point is None:
            warnings.append(f"{label}: skipped geometry with an invalid coordinate")
            return None
        try:
            point = transform(point)
        except ValueError as exc:
            warnings.append(f"{label}: skipped geometry: {exc}")
            return None
        if not points or point != points[-1]:
            points.append(point)
    if polygon and len(points) > 1 and points[-1] == points[0]:
        points.pop()
    if len(points) < (3 if polygon else 2):
        warnings.append(f"{label}: skipped geometry with too few distinct points")
        return None
    if polygon:
        n = len(points)
        area_twice = sum(points[i][0] * points[(i + 1) % n][1] -
                         points[(i + 1) % n][0] * points[i][1] for i in range(n))
        if not math.isfinite(area_twice) or abs(area_twice) <= 1e-8:
            warnings.append(f"{label}: skipped zero-area footprint")
            return None
        for i in range(n):
            for j in range(i + 1, n):
                if j == i + 1 or (i == 0 and j == n - 1):
                    continue
                if _segments_intersect(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]):
                    warnings.append(f"{label}: skipped self-intersecting footprint")
                    return None
        if area_twice < 0:
            points.reverse()
    return points


def _first_valid(props, keys, parser, label, warnings):
    for key in keys:
        if props.get(key) not in (None, ""):
            value = parser(props[key])
            if value is not None:
                return value
            warnings.append(f"{label}: invalid {key}={props[key]!r}; using a fallback")
    return None


def _positive_number(value):
    number = _finite_number(value)
    return number if number is not None and number > 0 else None


def _nonnegative_number(value):
    number = _finite_number(value)
    return number if number is not None and number >= 0 else None


def _heights(props, label, warnings):
    minimum = _first_valid(props, ("min_height", "building:min_height"), parse_length, label, warnings)
    if minimum is None:
        min_level = _first_valid(props, ("building:min_level", "min_level"), _nonnegative_number, label, warnings)
        minimum = (min_level or 0.0) * LEVEL_HEIGHT
    height = _first_valid(props, ("height", "building:height"),
                          lambda v: parse_length(v) if parse_length(v) else None, label, warnings)
    if height is None:
        levels = _first_valid(props, ("building:levels", "levels"), _positive_number, label, warnings)
        height = levels * LEVEL_HEIGHT if levels is not None else max(DEFAULT_BUILDING_HEIGHT, minimum + LEVEL_HEIGHT)
    if minimum >= height:
        warnings.append(f"{label}: skipped building because min_height is not below height")
        return None
    return height, minimum


def _road_width(props, label, warnings):
    width = _first_valid(props, ("width",),
                         lambda v: parse_length(v) if parse_length(v) else None, label, warnings)
    if width is not None:
        return width
    lanes = _positive_number(props.get("lanes"))
    if lanes is not None:
        return lanes * 3.0
    return _ROAD_WIDTHS.get(str(props.get("highway", "")), 6.0)


def _truthy_tag(value):
    return value is not None and str(value).lower() not in {"", "no", "false", "0", "none"}


def _street_kind(props):
    """Only explicit mapped point tags identify actual street features."""
    if props.get("natural") == "tree":
        return "trees"
    if props.get("power") in ("pole", "tower"):
        return "utility_poles"
    if props.get("highway") == "traffic_signals":
        return "traffic_lights"
    return None


def _source_tags(props):
    return {key: value for key, value in props.items() if key != "tags"}


def _building_tags(props):
    # Preserve semantic tags without altering the legacy untagged schema.
    if any(key in props for key in ("building", "building:part", "building:use",
                                    "use", "amenity", "shop", "office")):
        return {"tags": _source_tags(props)}
    return {}


def _empty_scene(system, origin, attribution):
    return {"buildings": [], "roads": [], "street_features": [], "coordinate_system": system,
            "origin": origin, "attribution": attribution, "warnings": []}


def _load_geojson(data, requested, origin):
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("GeoJSON input must be a FeatureCollection with a features list")
    positions = []
    for feature in data["features"]:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if isinstance(geometry, dict):
            positions.extend(_walk_positions(geometry.get("coordinates")))
    system = requested
    inferred = False
    if system == "auto":
        declaration = data.get("coordinate_system")
        if declaration is not None:
            system = _system(declaration)
        elif data.get("crs") is not None:
            crs = data["crs"]
            properties = crs.get("properties") if isinstance(crs, dict) else None
            name = str(properties.get("name", "")) if isinstance(properties, dict) else str(crs)
            if "4326" in name or "CRS84" in name.upper():
                system = "wgs84"
            elif name.lower() in {"local", "meters", "metres"}:
                system = "local"
            else:
                raise ValueError(f"Unsupported GeoJSON CRS {name!r}; reproject to WGS84 or local metres")
        if system == "auto":
            system = "wgs84" if positions and all(-180 <= p[0] <= 180 and -90 <= p[1] <= 90 for p in positions) else "local"
            inferred = True
    origin = origin if origin is not None else data.get("origin")
    if origin is not None:
        origin = _validate_origin(origin)
    elif system == "wgs84":
        valid_positions = [p for p in positions if -180 <= p[0] <= 180 and -90 < p[1] < 90]
        origin = _centroid_origin(valid_positions)
    attribution = str(data.get("attribution") or "Source: " + str(data.get("name") or "imported GeoJSON"))
    scene = _empty_scene(system, origin, attribution)
    scene["provenance"] = data.get("provenance", {})
    scene["limitations"] = data.get("limitations", {})
    warnings = scene["warnings"]
    if inferred and system == "wgs84":
        warnings.append("Auto coordinates assumed WGS84 longitude/latitude; use coordinate_system='local' for metre coordinates")
    transform = (lambda p: project_lonlat(p[0], p[1], origin)) if system == "wgs84" else (lambda p: p)
    for index, feature in enumerate(data["features"]):
        label = f"Feature {index}"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            warnings.append(f"{label}: skipped malformed feature")
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            warnings.append(f"{label}: skipped missing or malformed geometry")
            continue
        props = feature.get("properties")
        if props is None:
            props = {}
        if not isinstance(props, dict):
            warnings.append(f"{label}: skipped malformed properties")
            continue
        # OSM exports often nest tags in properties.tags.
        if isinstance(props.get("tags"), dict):
            props = {**props["tags"], **props}
        label = str(props.get("name") or feature.get("id") or label)
        kind, coordinates = geometry.get("type"), geometry.get("coordinates")
        if not isinstance(kind, str):
            warnings.append(f"{label}: skipped missing or malformed geometry type")
            continue
        if kind in {"Point", "MultiPoint"}:
            street_kind = _street_kind(props)
            if street_kind is None:
                continue
            raw_points = [coordinates] if kind == "Point" else coordinates
            if not isinstance(raw_points, (list, tuple)):
                warnings.append(f"{label}: skipped malformed point coordinates")
                continue
            for raw in raw_points:
                point = _position(raw)
                if point is None:
                    warnings.append(f"{label}: skipped invalid street-feature coordinate")
                    continue
                try:
                    point = transform(point)
                except ValueError as exc:
                    warnings.append(f"{label}: skipped street feature: {exc}")
                    continue
                scene["street_features"].append({
                    "kind": street_kind, "point": point,
                    "osm_id": props.get("osm_id", props.get("@id", feature.get("id"))),
                    "tags": _source_tags(props),
                })
        elif kind in {"Polygon", "MultiPolygon"}:
            if "building" in props and not _truthy_tag(props["building"]) and not _truthy_tag(props.get("building:part")):
                continue
            if props.get("landuse") and not (_truthy_tag(props.get("building")) or _truthy_tag(props.get("building:part"))):
                continue
            heights = _heights(props, label, warnings)
            if heights is None:
                continue
            polygons = [coordinates] if kind == "Polygon" else coordinates
            if not isinstance(polygons, (list, tuple)):
                warnings.append(f"{label}: skipped malformed polygon coordinates")
                continue
            for part, polygon in enumerate(polygons):
                part_label = f"{label} {part + 1}" if len(polygons) > 1 else label
                if not isinstance(polygon, (list, tuple)) or not polygon:
                    warnings.append(f"{part_label}: skipped empty polygon")
                    continue
                if len(polygon) > 1:
                    warnings.append(f"{part_label}: interior rings are not modelled; using the exterior footprint")
                footprint = _clean_points(polygon[0], transform, True, part_label, warnings)
                if footprint is not None:
                    scene["buildings"].append({"name": part_label, "footprint": footprint,
                                               "height": heights[0], "min_height": heights[1],
                                               "osm_id": props.get("osm_id"), "height_source": props.get("height_source", "unspecified"),
                                               **_building_tags(props)})
        elif kind in {"LineString", "MultiLineString"}:
            lines = [coordinates] if kind == "LineString" else coordinates
            if not isinstance(lines, (list, tuple)):
                warnings.append(f"{label}: skipped malformed line coordinates")
                continue
            width = _road_width(props, label, warnings)
            for part, line in enumerate(lines):
                part_label = f"{label} {part + 1}" if len(lines) > 1 else label
                points = _clean_points(line, transform, False, part_label, warnings)
                if points is not None:
                    scene["roads"].append({"name": part_label, "points": points, "width": width, "osm_id": props.get("osm_id"), "highway": props.get("highway", ""), "oneway": str(props.get("oneway", "")), "tags": _source_tags(props)})
        else:
            warnings.append(f"{label}: skipped unsupported geometry type {kind!r}")
    return scene


def _load_osm(root, requested, origin):
    if root.tag != "osm":
        raise ValueError("OSM XML input must have an <osm> root element")
    if requested == "local":
        raise ValueError("OSM XML uses WGS84 node coordinates; coordinate_system='local' is not valid")
    nodes = {}
    warnings = []
    for node in root.findall("node"):
        point = _position([node.get("lon"), node.get("lat")])
        if point is not None and -180 <= point[0] <= 180 and -90 < point[1] < 90:
            nodes[node.get("id")] = point
        else:
            warnings.append(f"OSM node {node.get('id')}: skipped invalid longitude/latitude")
    origin = _validate_origin(origin) if origin is not None else _centroid_origin(list(nodes.values()))
    scene = _empty_scene("wgs84", origin, OSM_ATTRIBUTION)
    scene["warnings"] = warnings
    transform = lambda p: project_lonlat(p[0], p[1], origin)
    for node in root.findall("node"):
        props = {tag.get("k"): tag.get("v") for tag in node.findall("tag")}
        kind = _street_kind(props)
        if kind is not None and node.get("id") in nodes:
            scene["street_features"].append({
                "kind": kind, "point": transform(nodes[node.get("id")]),
                "osm_id": node.get("id"), "tags": props,
            })
    for way in root.findall("way"):
        props = {tag.get("k"): tag.get("v") for tag in way.findall("tag")}
        building = _truthy_tag(props.get("building")) or _truthy_tag(props.get("building:part"))
        road = _truthy_tag(props.get("highway"))
        if not building and not road:
            continue
        label = str(props.get("name") or f"OSM way {way.get('id', '?')}")
        refs = [node.get("ref") for node in way.findall("nd")]
        missing = [ref for ref in refs if ref not in nodes]
        if missing:
            warnings.append(f"{label}: skipped incomplete way with {len(missing)} missing nodes")
            continue
        raw = [nodes[ref] for ref in refs]
        if building:
            if len(refs) < 4 or refs[0] != refs[-1]:
                warnings.append(f"{label}: skipped unclosed building way")
                continue
            heights = _heights(props, label, warnings)
            footprint = _clean_points(raw, transform, True, label, warnings)
            if heights is not None and footprint is not None:
                scene["buildings"].append({"name": label, "footprint": footprint,
                                           "height": heights[0], "min_height": heights[1],
                                           "osm_id": way.get("id"), **_building_tags(props)})
        elif road:
            points = _clean_points(raw, transform, False, label, warnings)
            if points is not None:
                scene["roads"].append({"name": label, "points": points,
                                       "width": _road_width(props, label, warnings), "highway": props.get("highway", ""),
                                       "oneway": str(props.get("oneway", "")), "osm_id": way.get("id"),
                                       "tags": _source_tags(props)})
    for relation in root.findall("relation"):
        props = {tag.get("k"): tag.get("v") for tag in relation.findall("tag")}
        if _truthy_tag(props.get("building")) or _truthy_tag(props.get("building:part")):
            warnings.append(f"OSM relation {relation.get('id', '?')}: building relations are not supported; export as GeoJSON MultiPolygon")
    remark = root.findtext("remark")
    if remark and remark.strip():
        warnings.append("OSM server remark: " + remark.strip())
    return scene


def load_map(path: str | Path, coordinate_system: str = "auto", origin=None) -> dict:
    """Load GeoJSON or OSM XML; invalid documents raise ValueError.

    Geometry-level errors skip that feature and add a warning. ``origin`` is an
    optional explicit (lon, lat) projection anchor. In local mode coordinates
    pass through unchanged; an optional origin is stored as georeference only.
    """
    requested = _system(coordinate_system)
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if text.lstrip().startswith("<"):
        # Never permit entity expansion or external entity declarations.
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("OSM XML document type/entity declarations are not supported")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid OSM XML: {exc}") from exc
        return _load_osm(root, requested, origin)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid GeoJSON: {exc}") from exc
    return _load_geojson(data, requested, origin)


def mapped_actors(data):
    """Create explicit illustrative routes from mapped centre-lines, never demo axes."""
    actors = []
    for kind, kinds, speed in [('person', {'footway', 'pedestrian', 'path'}, 1.4),
                               ('vehicle', {'primary', 'secondary', 'tertiary', 'residential'}, 4.0)]:
        candidates = [r for r in data['roads'] if r.get('highway') in kinds and
                      sum(math.dist(a, b) for a, b in zip(r['points'], r['points'][1:])) >= 25]
        if not candidates:
            continue
        r = min(candidates, key=lambda r: min(math.hypot(*p) for p in r['points']))
        points = r['points'] if r.get('oneway') != '-1' else list(reversed(r['points']))
        actors.append({'name': 'Mapped_' + kind.title(), 'kind': kind, 'speed': speed,
                       'loop': False, 'source_osm_way': r.get('osm_id'),
                       'path': [[*p, .08] for p in points]})
    return actors
