"""Pure placement checks: these tests deliberately do not require Blender."""
import unittest
from whitebox_world.street_details import (plan_street_details, PlacementIndex,
    road_samples, intersections, segment_distance, signal_junctions)


class StreetDetailsTests(unittest.TestCase):
    def setUp(self):
        self.roads=[{'points':[[-70,0],[70,0]],'width':8,'osm_id':'east','highway':'residential'},
                    {'points':[[0,-70],[0,70]],'width':8,'osm_id':'north','highway':'primary'}]
        self.buildings=[{'footprint':[[10,7],[25,7],[25,20],[10,20]],'height':12}]

    def test_deterministic_and_clear(self):
        a=plan_street_details(self.roads,self.buildings,{'seed':9})
        self.assertEqual(a,plan_street_details(self.roads,self.buildings,{'seed':9}))
        index=PlacementIndex(self.roads,self.buildings)
        for kind,radius in [('trees',2),('utility_poles',.65),('traffic_lights',.65)]:
            self.assertGreater(len(a[kind]),0)
            for item in a[kind]:
                self.assertTrue(index.clear(item['point'],radius))
                self.assertEqual(item['placement'],'procedural')
                self.assertTrue(item['source_road_ids'])
        self.assertEqual(a['metadata']['intersection_count'],1)

    def test_paint_stays_on_road_and_away_from_intersection(self):
        plan=plan_street_details(self.roads,[],{})
        self.assertGreater(len(plan['road_markings']),0)
        for item in plan['road_markings']:
            road=self.roads[item['road_index']]
            self.assertAlmostEqual(segment_distance(item['point'],*road['points']),0)
            self.assertGreaterEqual(sum(x*x for x in item['point'])**.5,11)

    def test_footpaths_have_no_motor_infrastructure(self):
        road={'points':[[0,0],[100,0]],'width':6,'highway':'footway'}
        plan=plan_street_details([road],[],{})
        for kind in ('road_markings','utility_poles','traffic_lights'):
            self.assertEqual(plan[kind],[])
        self.assertTrue(plan['trees'])

    def test_source_features_are_preserved_and_collisions_skipped(self):
        plan=plan_street_details(self.roads,self.buildings,{},[
            {'kind':'trees','point':[-32,9],'osm_id':'tree123'},
            {'kind':'utility_poles','point':[16,12],'osm_id':'badpole'}])
        tree=next(x for x in plan['trees'] if x['source_id']=='tree123')
        self.assertEqual(tree['point'],(-32,9)); self.assertEqual(tree['placement'],'source')
        self.assertEqual(plan['metadata']['source_counts']['trees'],1)
        self.assertEqual(plan['metadata']['skipped_source_collisions_or_limit'],1)
        self.assertNotIn('badpole',[x['source_id'] for x in plan['utility_poles']])

    def test_limits_and_disable(self):
        plan=plan_street_details(self.roads,[],{'street_details':{'max_trees':2,'max_poles':1,'max_markings':3,'max_traffic_lights':1}})
        self.assertEqual(plan['metadata']['counts'],{'trees':2,'utility_poles':1,'road_markings':3,'traffic_lights':1})
        plan=plan_street_details(self.roads,[],{'street_details':False})
        self.assertFalse(any(plan[k] for k in ('trees','utility_poles','road_markings','traffic_lights')))

    def test_continuous_sampling(self):
        samples=list(road_samples({'points':[[0,0],[3,0],[3,7]]},4))
        self.assertEqual([s[0] for s in samples],[(2,0),(3,3),(3,7)])

    def test_shared_vertex_crossing_is_deduplicated(self):
        roads=[{'points':[[-10,0],[0,0],[10,0]],'width':6},
               {'points':[[0,-10],[0,0],[0,10]],'width':6}]
        self.assertEqual(len(intersections(roads)),1)

    def test_signal_inference_excludes_shallow_continuations(self):
        roads=[{'points':[[-20,0],[0,0]],'width':6,'highway':'primary'},
               {'points':[[0,0],[20,2]],'width':6,'highway':'primary'}]
        self.assertEqual(len(intersections(roads)),1)
        self.assertEqual(signal_junctions(roads),[])
        self.assertEqual(len(signal_junctions(self.roads)),1)

    def test_signal_junctions_merge_close_crossings(self):
        roads=[{'points':[[-30,0],[30,0]],'width':6,'highway':'primary'},
               {'points':[[0,-20],[0,20]],'width':6,'highway':'secondary'},
               {'points':[[8,-20],[8,20]],'width':6,'highway':'secondary'}]
        self.assertEqual(len(intersections(roads)),2)
        self.assertEqual(len(signal_junctions(roads)),1)
        self.assertEqual(signal_junctions(roads)[0]['roads'],{0,1,2})

    def test_signal_inference_excludes_service_only_junctions(self):
        roads=[dict(r,highway='service') for r in self.roads]
        self.assertEqual(signal_junctions(roads),[])
        roads[0]['highway']='primary'
        self.assertEqual(len(signal_junctions(roads)),1)

    def test_grade_separation_uses_nested_tags(self):
        for tags in ({'bridge':'yes'},{'tunnel':'yes'},{'layer':'1'},{'layer':'-1'}):
            roads=[dict(self.roads[0],tags=tags),self.roads[1]]
            self.assertEqual(signal_junctions(roads),[],tags)
        roads=[dict(self.roads[0],tags={'bridge':'no','layer':'0'}),self.roads[1]]
        self.assertEqual(len(signal_junctions(roads)),1)

    def test_collision_query_respects_polygon_boundary(self):
        index=PlacementIndex([],self.buildings)
        self.assertFalse(index.clear((17,12),.1))
        self.assertFalse(index.clear((10,12),.1))
        self.assertFalse(index.clear((9.5,12),1))
        self.assertTrue(index.clear((7,12),1))


if __name__=='__main__': unittest.main()
