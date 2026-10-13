#!/usr/bin/env python3
"""Download OSM building/highway ways for an explicit small bounding box.

Example: python scripts/fetch_osm.py --bbox 51.50 -0.13 51.51 -0.12 --output data/london.osm
Bounding-box order is SOUTH WEST NORTH EAST. Coordinates are latitude/longitude
degrees. The official public Overpass instance is rate limited; use small areas.
API reference: https://dev.overpass-api.de/command_line.html
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def build_query(bbox, timeout=60):
    """Build a read-only Overpass QL query, including all referenced way nodes."""
    if len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox):
        raise ValueError("bbox must contain four finite numbers: SOUTH WEST NORTH EAST")
    south, west, north, east = map(float, bbox)
    if not (-90 < south < north < 90 and -180 <= west < east <= 180):
        raise ValueError("bbox must have SOUTH < NORTH and WEST < EAST within WGS84 bounds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 180:
        raise ValueError("timeout must be an integer between 1 and 180 seconds")
    box = ",".join(f"{value:.9f}" for value in (south, west, north, east))
    return (f"[out:xml][timeout:{timeout}];\n(\n"
            f'  way["building"]({box});\n'
            f'  way["building:part"]({box});\n'
            f'  way["highway"]({box});\n'
            ");\n(._;>;);\nout body;\n")


def fetch_osm(bbox, output, timeout=60):
    """Download and validate an OSM XML response, preserving existing files on failure."""
    query = build_query(bbox, timeout)
    request = Request(OVERPASS_URL, data=urlencode({"data": query}).encode("utf-8"),
                      headers={"User-Agent": "WhiteboxWorld/1.0 (OSM building/road scene importer)",
                               "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/xml"})
    with urlopen(request, timeout=timeout + 15) as response:
        body = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(body) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Response exceeded 64 MiB; choose a smaller bounding box")
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unexpected XML document type/entity declaration")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError("Overpass did not return valid OSM XML") from exc
    if root.tag != "osm":
        raise ValueError("Overpass response did not contain an OSM document")
    remark = root.findtext("remark")
    if remark and remark.strip():
        raise ValueError("Overpass returned a possibly incomplete result: " + remark.strip())
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".whitebox-osm-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(body)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    parser.add_argument("--output", "-o", type=Path, required=True, help="Destination .osm file")
    parser.add_argument("--timeout", type=int, default=60, help="Overpass query timeout, 1–180 seconds (default 60)")
    args = parser.parse_args(argv)
    try:
        path = fetch_osm(args.bbox, args.output, args.timeout)
    except (ValueError, OSError, HTTPError, URLError) as exc:
        print(f"Could not fetch OSM data: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {path}. Data © OpenStreetMap contributors, ODbL.")
    print("Attribution: https://www.openstreetmap.org/copyright")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
