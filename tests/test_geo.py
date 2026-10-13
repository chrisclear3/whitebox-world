"""Pure standard-library tests: python -m unittest discover -s tests -v."""

import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from whitebox_world.geo import EARTH_RADIUS_M, load_map, parse_length, project_lonlat


SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]


def feature(kind="Polygon", coordinates=None, properties=None):
    return {"type": "Feature", "properties": properties or {},
            "geometry": {"type": kind, "coordinates": coordinates if coordinates is not None else [SQUARE]}}


class GeoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "map.geojson"

    def read(self, features, **kwargs):
        data = {"type": "FeatureCollection", "coordinate_system": "local", "features": features}
        data.update(kwargs.pop("metadata", {}))
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return load_map(self.path, **kwargs)

    def read_osm(self, body, **kwargs):
        self.path.write_text('<osm version="0.6">' + body + '</osm>', encoding="utf-8")
        return load_map(self.path, **kwargs)

    def test_local_meters_do_not_move(self):
        result = self.read([feature(properties={"name": "Tower", "height": 18})])
        self.assertEqual(result["buildings"][0], {"name": "Tower", "footprint": SQUARE[:-1],
                                                  "height": 18.0, "min_height": 0.0, "osm_id": None, "height_source": "unspecified"})
        self.assertEqual(result["warnings"], [])
        self.assertIsNone(result["origin"])

    def test_projection_origin_axes_and_scale(self):
        self.assertEqual(project_lonlat(-73, 40, (-73, 40)), [0.0, 0.0])
        east = project_lonlat(-72.999, 40, (-73, 40))
        north = project_lonlat(-73, 40.001, (-73, 40))
        self.assertAlmostEqual(east[0], EARTH_RADIUS_M * math.radians(.001) * math.cos(math.radians(40)), places=5)
        self.assertAlmostEqual(north[1], EARTH_RADIUS_M * math.radians(.001), places=5)
        self.assertEqual(east[1], 0)
        self.assertEqual(north[0], 0)

    def test_explicit_origin_applied_to_geojson(self):
        result = self.read([feature("LineString", [[-73, 40], [-72.999, 40.001]])],
                           coordinate_system="wgs84", origin=(-73, 40))
        self.assertEqual(result["origin"], [-73.0, 40.0])
        self.assertEqual(result["roads"][0]["points"][0], [0.0, 0.0])

    def test_projection_crosses_date_line_locally(self):
        result = project_lonlat(-179.999, 0, (179.999, 0))
        self.assertAlmostEqual(result[0], 222.39016046, places=5)

    def test_invalid_origin_and_coordinates_raise(self):
        for origin in [(0, 90), (181, 0), (float("nan"), 0), "0,0"]:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                project_lonlat(0, 0, origin)
        with self.assertRaises(ValueError):
            project_lonlat(999, 20, (0, 0))

    def test_height_units(self):
        expected = {"12.5": 12.5, "12,5 m": 12.5, "10 ft": 3.048,
                    "10'6\"": 3.2004, "3 meters": 3, "250 cm": 2.5, "1000 mm": 1}
        for value, meters in expected.items():
            with self.subTest(value=value):
                self.assertAlmostEqual(parse_length(value), meters)
        for value in ["tall", None, "NaN", float("inf"), -4, True, "-3m", "12;14"]:
            with self.subTest(value=value):
                self.assertIsNone(parse_length(value))
                self.assertEqual(parse_length(value, 9), 9)

    def test_levels_and_min_level(self):
        result = self.read([feature(properties={"building:levels": "4", "building:min_level": "1"})])
        building = result["buildings"][0]
        self.assertEqual((building["height"], building["min_height"]), (12.0, 3.0))

    def test_explicit_height_overrides_levels(self):
        result = self.read([feature(properties={"height": "50 ft", "building:levels": 10, "min_height": "2 m"})])
        building = result["buildings"][0]
        self.assertAlmostEqual(building["height"], 15.24)
        self.assertEqual(building["min_height"], 2)

    def test_invalid_height_falls_back_with_warning(self):
        result = self.read([feature(properties={"height": "unknown", "building:levels": 2})])
        self.assertEqual(result["buildings"][0]["height"], 6)
        self.assertIn("invalid height", " ".join(result["warnings"]))

    def test_min_height_cannot_reach_roof(self):
        result = self.read([feature(properties={"height": 4, "min_height": 4})])
        self.assertFalse(result["buildings"])
        self.assertIn("min_height", " ".join(result["warnings"]))

    def test_default_roof_above_high_minimum(self):
        result = self.read([feature(properties={"min_height": 20})])
        self.assertEqual(result["buildings"][0]["height"], 23)

    def test_multipolygon_separate_buildings(self):
        second = [[x + 20, y] for x, y in SQUARE]
        result = self.read([feature("MultiPolygon", [[SQUARE], [second]], {"name": "Apartments", "levels": 2})])
        self.assertEqual(len(result["buildings"]), 2)
        self.assertEqual([b["name"] for b in result["buildings"]], ["Apartments 1", "Apartments 2"])
        self.assertEqual(result["buildings"][1]["footprint"], second[:-1])

    def test_holes_are_explicitly_reported(self):
        result = self.read([feature(coordinates=[SQUARE, [[2, 2], [3, 2], [3, 3], [2, 2]]])])
        self.assertEqual(len(result["buildings"]), 1)
        self.assertIn("interior rings", " ".join(result["warnings"]))

    def test_counterclockwise_winding(self):
        result = self.read([feature(coordinates=[list(reversed(SQUARE))])])
        ring = result["buildings"][0]["footprint"]
        area = sum(ring[i][0] * ring[(i + 1) % 4][1] - ring[(i + 1) % 4][0] * ring[i][1] for i in range(4))
        self.assertGreater(area, 0)

    def test_degenerate_and_self_intersecting_polygons_skipped(self):
        result = self.read([
            feature(coordinates=[[[0, 0], [1, 0], [2, 0], [0, 0]]]),
            feature(coordinates=[[[0, 0], [10, 10], [0, 10], [10, 0], [0, 0]]]),
            feature(coordinates=[[[0, 0], [10, 0], [5, 10], [5, -5], [0, 0]]]),
        ])
        self.assertFalse(result["buildings"])
        self.assertEqual(len(result["warnings"]), 3)

    def test_malformed_features_do_not_abort_others(self):
        malformed = [None, 8, {"type": "Feature", "geometry": "bad"},
                     feature(coordinates="bad"), feature(coordinates=[[[0, 0], [1, "bad"], [1, 0]]])]
        result = self.read(malformed + [feature()])
        self.assertEqual(len(result["buildings"]), 1)
        self.assertEqual(len(result["warnings"]), 5)

    def test_malformed_geometry_types_and_properties_are_skipped(self):
        bad_properties = feature()
        bad_properties["properties"] = False
        result = self.read([feature([], []), feature({}, []), bad_properties, feature()])
        self.assertEqual(len(result["buildings"]), 1)
        self.assertEqual(len(result["warnings"]), 3)

    def test_roads_multiline_width_and_duplicates(self):
        result = self.read([feature("MultiLineString", [[[0, 0], [0, 0], [10, 10]], [[20, 0], [30, 10]]],
                                   {"name": "Road", "width": "20 ft"})])
        self.assertEqual(len(result["roads"]), 2)
        self.assertEqual(len(result["roads"][0]["points"]), 2)
        self.assertAlmostEqual(result["roads"][0]["width"], 6.096)

    def test_road_default_and_lanes(self):
        result = self.read([feature("LineString", [[0, 0], [10, 10]], {"highway": "footway"}),
                           feature("LineString", [[0, 0], [10, 10]], {"lanes": "4"})])
        self.assertEqual([r["width"] for r in result["roads"]], [2.0, 12.0])

    def test_auto_wgs84_and_explicit_local_metadata(self):
        data = {"type": "FeatureCollection", "features": [feature()]}
        self.path.write_text(json.dumps(data))
        result = load_map(self.path)
        self.assertEqual(result["coordinate_system"], "wgs84")
        self.assertIn("assumed WGS84", " ".join(result["warnings"]))
        data["coordinate_system"] = "local"
        self.path.write_text(json.dumps(data))
        self.assertEqual(load_map(self.path)["coordinate_system"], "local")

    def test_unsupported_crs_rejected(self):
        data = {"type": "FeatureCollection", "features": [],
                "crs": {"type": "name", "properties": {"name": "EPSG:3857"}}}
        self.path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "Unsupported GeoJSON CRS"):
            load_map(self.path)

    def test_osm_building_and_highway(self):
        xml = ('<node id="1" lon="-73" lat="40"/><node id="2" lon="-72.9999" lat="40"/>'
               '<node id="3" lon="-72.9999" lat="40.0001"/><node id="4" lon="-73" lat="40.0001"/>'
               '<way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>'
               '<tag k="building" v="yes"/><tag k="height" v="30 ft"/><tag k="name" v="Office"/></way>'
               '<way id="20"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>')
        result = self.read_osm(xml, origin=(-73, 40))
        self.assertEqual(len(result["buildings"]), 1)
        self.assertEqual(len(result["roads"]), 1)
        self.assertEqual(result["buildings"][0]["name"], "Office")
        self.assertAlmostEqual(result["buildings"][0]["height"], 9.144)
        self.assertEqual(result["roads"][0]["points"][0], [0, 0])
        self.assertIn("OpenStreetMap", result["attribution"])

    def test_osm_missing_nodes_skips_entire_way(self):
        result = self.read_osm('<node id="1" lon="0" lat="0"/>'
                               '<way id="4"><nd ref="1"/><nd ref="missing"/><tag k="highway" v="service"/></way>')
        self.assertEqual(result["roads"], [])
        self.assertIn("missing nodes", " ".join(result["warnings"]))

    def test_osm_unclosed_building_skipped(self):
        result = self.read_osm('<node id="1" lon="0" lat="0"/><node id="2" lon=".001" lat="0"/>'
                               '<node id="3" lon=".001" lat=".001"/>'
                               '<way id="4"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="building" v="yes"/></way>')
        self.assertFalse(result["buildings"])
        self.assertIn("unclosed", " ".join(result["warnings"]))

    def test_osm_relations_warn_and_local_override_fails(self):
        result = self.read_osm('<relation id="6"><tag k="building" v="yes"/></relation>')
        self.assertIn("relations are not supported", " ".join(result["warnings"]))
        with self.assertRaisesRegex(ValueError, "uses WGS84"):
            load_map(self.path, "local")

    def test_entity_declarations_rejected(self):
        self.path.write_text('<!DOCTYPE osm [<!ENTITY x "xx">]><osm/>')
        with self.assertRaisesRegex(ValueError, "entity declarations"):
            load_map(self.path)

    def test_document_errors_are_clear(self):
        for text in ["{", '<osm>', '{"type":"Polygon"}']:
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ValueError):
                    load_map(self.path)


class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_osm.py"
        spec = importlib.util.spec_from_file_location("fetch_osm", path)
        cls.fetch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.fetch)

    def test_query_has_explicit_bbox_and_nodes(self):
        query = self.fetch.build_query([40, -73, 40.01, -72.99], 30)
        self.assertIn("[timeout:30]", query)
        self.assertIn('way["building"](40.000000000,-73.000000000,40.010000000,-72.990000000)', query)
        self.assertIn('way["highway"]', query)
        self.assertIn("(._;>;);", query)

    def test_query_rejects_bad_bounds_and_timeout(self):
        for bbox in [[41, -73, 40, -72], [40, -72, 41, -73], [0, 0, 100, 1], [0, 0, float("nan"), 1]]:
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                self.fetch.build_query(bbox)
        for timeout in [0, 181, 1.5, True]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.fetch.build_query([0, 0, 1, 1], timeout)

    def test_fetch_mocked_response_and_request(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(self.fetch, "urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = b'<osm version="0.6" />'
            output = Path(temp) / "map.osm"
            self.fetch.fetch_osm([0, 0, .01, .01], output, 10)
            self.assertTrue(output.exists())
            request = opener.call_args.args[0]
            self.assertEqual(request.full_url, self.fetch.OVERPASS_URL)
            self.assertEqual(opener.call_args.kwargs["timeout"], 25)

    def test_fetch_error_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(self.fetch, "urlopen") as opener:
            output = Path(temp) / "map.osm"
            output.write_text("previous data")
            opener.return_value.__enter__.return_value.read.return_value = b'<osm><remark>runtime error: timeout</remark></osm>'
            with self.assertRaisesRegex(ValueError, "incomplete"):
                self.fetch.fetch_osm([0, 0, .01, .01], output)
            self.assertEqual(output.read_text(), "previous data")


if __name__ == "__main__":
    unittest.main()
