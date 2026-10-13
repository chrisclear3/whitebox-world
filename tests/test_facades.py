import unittest
from whitebox_world.facades import plan_facades, _mesh_boxes, residential_type

SQUARE=[(0,0),(12,0),(12,12),(0,12)]

class FacadeTests(unittest.TestCase):
    def test_determinism_and_variation(self):
        self.assertEqual(plan_facades(SQUARE,12,key='a'),plan_facades(SQUARE,12,key='a'))
        self.assertNotEqual(plan_facades(SQUARE,12,key='a'),plan_facades(SQUARE,12,key='b'))

    def test_extruded_frames_and_railings(self):
        groups=plan_facades(SQUARE,12,residential=True)
        self.assertTrue(groups['glazing'])
        self.assertTrue(groups['balconies'])
        self.assertTrue(all(min(spec[1]) > 0 for specs in groups.values() for spec in specs))
        vertices,faces=_mesh_boxes(groups['frames'])
        self.assertEqual(len(vertices),len(groups['frames'])*8)
        self.assertEqual(len(faces),len(groups['frames'])*6)

    def test_shared_wall_suppressed(self):
        neighbor=[(12,0),(24,0),(24,12),(12,12)]
        groups=plan_facades(SQUARE,12,neighbors=[neighbor],residential=True)
        self.assertTrue(groups['glazing'])
        self.assertFalse(any(spec[0][0] > 12 for specs in groups.values() for spec in specs))

    def test_shopfront_only_on_road_side(self):
        self.assertFalse(plan_facades(SQUARE,12)['shopfronts'])
        roads=[{'points':[(-10,-7),(22,-7)],'width':6}]
        groups=plan_facades(SQUARE,12,roads=roads)
        self.assertTrue(groups['shopfronts'])
        self.assertTrue(all(spec[0][1] < 0 for spec in groups['shopfronts']))
        self.assertFalse(plan_facades(SQUARE,12,min_height=3,roads=roads)['shopfronts'])

    def test_concave_narrow_recess_is_clear(self):
        # A .3m-wide inward notch cannot support projecting windows or balconies.
        shape=[(0,0),(12,0),(12,12),(6.15,12),(6.15,4),(5.85,4),(5.85,12),(0,12)]
        groups=plan_facades(shape,12,residential=True)
        self.assertFalse(any(5.85 < spec[0][0] < 6.15 and spec[0][1] > 4
                             for specs in groups.values() for spec in specs))

    def test_winding_does_not_flip_outward(self):
        for ring in (SQUARE,list(reversed(SQUARE))):
            groups=plan_facades(ring,12)
            self.assertTrue(all(x < 0 or x > 12 or y < 0 or y > 12
                                for (x,y,z),_,_,_ in groups['glazing']))

    def test_source_tag_classifier(self):
        self.assertTrue(residential_type('{"building": "apartments"}'))
        self.assertFalse(residential_type({'building': 'office'}))
        self.assertFalse(residential_type({'building': 'retail'}))
        self.assertIsNone(residential_type({'building': 'yes'}))
        self.assertIsNone(residential_type('not-json'))

    def test_vertical_boundaries(self):
        for base,height in ((0,2.7),(0,6.4),(3,7),(0,89)):
            groups=plan_facades(SQUARE,height,min_height=base,residential=True,
                                roads=[{'points':[(-10,-7),(22,-7)],'width':6}])
            for specs in groups.values():
                for center,size,_,_ in specs:
                    self.assertGreaterEqual(center[2]-size[2]/2,base)
                    self.assertLessEqual(center[2]+size[2]/2,height)

    def test_small_building_no_detail(self):
        self.assertFalse(any(plan_facades(SQUARE,2).values()))

if __name__ == '__main__':unittest.main()
