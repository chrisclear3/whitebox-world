"""Source provenance and projection tests for mapped street details."""
import json
from pathlib import Path
import tempfile
import unittest

from whitebox_world.geo import load_map, project_lonlat


def feature(kind, coordinates, props, identity=None):
    return {"type": "Feature", "id": identity, "properties": props,
            "geometry": {"type": kind, "coordinates": coordinates}}


class StreetFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "map.geojson"

    def geojson(self, features, system="local", **kwargs):
        self.path.write_text(json.dumps({"type": "FeatureCollection",
            "coordinate_system": system, "features": features}))
        return load_map(self.path, **kwargs)

    def osm(self, body, **kwargs):
        self.path.write_text('<osm version="0.6">' + body + '</osm>')
        return load_map(self.path, **kwargs)

    def test_local_points_preserve_identity_tags_and_positions(self):
        scene = self.geojson([
            feature("Point", [5, 9], {"natural": "tree", "osm_id": "n1", "species": "oak"}),
            feature("Point", [15, 19], {"tags": {"power": "pole", "height": "8"}}, "node/2"),
            feature("Point", [25, 29], {"power": "tower", "@id": "node/3"}),
            feature("Point", [35, 39], {"highway": "traffic_signals"}),
        ])
        self.assertEqual([p["kind"] for p in scene["street_features"]],
                         ["trees", "utility_poles", "utility_poles", "traffic_lights"])
        self.assertEqual([p["point"] for p in scene["street_features"]],
                         [[5, 9], [15, 19], [25, 29], [35, 39]])
        self.assertEqual([p["osm_id"] for p in scene["street_features"]],
                         ["n1", "node/2", "node/3", None])
        self.assertEqual(scene["street_features"][1]["tags"], {"power": "pole", "height": "8"})
        self.assertEqual(scene["warnings"], [])

    def test_geographic_points_share_road_projection(self):
        scene = self.geojson([
            feature("LineString", [[139, 35], [139.001, 35.002]], {"highway": "residential"}),
            feature("Point", [139.001, 35.002], {"natural": "tree"}),
        ], system="wgs84", origin=[139, 35])
        point = scene["street_features"][0]["point"]
        self.assertEqual(point, scene["roads"][0]["points"][1])
        self.assertEqual(point, project_lonlat(139.001, 35.002, [139, 35]))

    def test_multipoints_validate_individually(self):
        scene = self.geojson([
            feature("MultiPoint", [[1, 2], ["bad", 4], [3, 4]], {"natural": "tree"}),
            feature("Point", [0, None], {"highway": "traffic_signals"}),
        ])
        self.assertEqual([p["point"] for p in scene["street_features"]], [[1, 2], [3, 4]])
        self.assertEqual(len(scene["warnings"]), 2)

    def test_invalid_wgs84_point_is_skipped(self):
        scene = self.geojson([feature("Point", [200, 20], {"natural": "tree"})],
                             system="wgs84", origin=[139, 35])
        self.assertEqual(scene["street_features"], [])
        self.assertEqual(len(scene["warnings"]), 1)

    def test_absent_or_unrelated_points_never_infer_actual_features(self):
        for points in ([], [feature("Point", [1, 2], {"amenity": "bench"})],
                       [feature("LineString", [[1, 2], [2, 3]], {"highway": "residential"})]):
            self.assertEqual(self.geojson(points)["street_features"], [])
        self.assertEqual(self.osm('<node id="1" lon="139" lat="35"/>')["street_features"], [])

    def test_osm_nodes_keep_tags_ids_and_projection(self):
        scene = self.osm('''
          <node id="1" lon="139" lat="35"><tag k="natural" v="tree"/></node>
          <node id="2" lon="139.001" lat="35.002"><tag k="power" v="tower"/></node>
          <node id="3" lon="139.002" lat="35.003"><tag k="highway" v="traffic_signals"/></node>
          <node id="4" lon="bad" lat="35"><tag k="natural" v="tree"/></node>
          <way id="9"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
        ''', origin=[139, 35])
        self.assertEqual([p["kind"] for p in scene["street_features"]],
                         ["trees", "utility_poles", "traffic_lights"])
        self.assertEqual([p["osm_id"] for p in scene["street_features"]], ["1", "2", "3"])
        self.assertEqual(scene["street_features"][0]["point"], [0, 0])
        self.assertEqual(scene["street_features"][1]["point"], scene["roads"][0]["points"][1])
        self.assertEqual(scene["street_features"][1]["tags"], {"power": "tower"})
        self.assertEqual(len(scene["warnings"]), 1)

    def test_semantic_building_and_road_tags_survive(self):
        scene = self.geojson([
            feature("Polygon", [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                    {"tags": {"building": "retail", "building:use": "commercial"}}),
            feature("LineString", [[1, 2], [2, 3]], {"highway": "footway", "surface": "paved"}),
        ])
        self.assertEqual(scene["buildings"][0]["tags"]["building:use"], "commercial")
        self.assertEqual(scene["roads"][0]["tags"]["surface"], "paved")
        self.assertEqual(scene["roads"][0]["highway"], "footway")

    def test_osm_building_keeps_semantic_tags_and_id(self):
        scene = self.osm('''
          <node id="1" lon="139" lat="35"/><node id="2" lon="139.001" lat="35"/>
          <node id="3" lon="139.001" lat="35.001"/>
          <way id="7"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/>
            <tag k="building" v="apartments"/><tag k="building:use" v="residential"/>
          </way>''')
        self.assertEqual(scene["buildings"][0]["osm_id"], "7")
        self.assertEqual(scene["buildings"][0]["tags"]["building"], "apartments")


if __name__ == "__main__":
    unittest.main()
