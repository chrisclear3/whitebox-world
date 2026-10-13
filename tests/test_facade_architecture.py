import math
import unittest
from whitebox_world.facade_styles import STYLES, classify_style, stable_seed
from whitebox_world.facade_layout import plan_facade_layout
from whitebox_world.facade_geometry import wall_boxes, shell_mesh
from whitebox_world.core import validate_config

RING=[(0,0),(18,0),(18,12),(0,12)]

class ArchitectureTests(unittest.TestCase):
    def test_mapped_use_over_size(self):
        for kind,want in [('house','house'),('apartments','apartment'),('warehouse','warehouse'),
                          ('retail','retail'),('garage','blank'),('church','blank')]:
            self.assertEqual(classify_style({'building':kind},height=40,area=200)[0],want)
        self.assertEqual(classify_style({'building':'house'},override='curtain_wall')[0],'curtain_wall')

    def test_override_and_deterministic_prior(self):
        for key in ['a','b','c']:
            a=classify_style(height=23,area=400,key=key)
            self.assertEqual(a,classify_style(height=23,area=400,key=key))
        self.assertNotEqual(stable_seed(key='a'),stable_seed(key='b'))
        self.assertEqual(classify_style({'building':'yes'},height=6,area=80)[1],'inferred_size_prior')
        with self.assertRaises(ValueError):classify_style(override='invalid')
        with self.assertRaises(ValueError):validate_config({'facade_style_overrides':{'123':'invalid'}})

    def test_mapped_floor_count_and_auto_override(self):
        p=plan_facade_layout(RING,18,tags={'building':'apartments','building:levels':'5'})
        self.assertEqual(p['floors'],5);self.assertEqual(p['floor_source'],'mapped_levels')
        self.assertEqual(classify_style({'facade:style':'house'},override='AUTO')[0],'house')
        validate_config({'facade_style_overrides':{'123':'AUTO'}})

    def test_actual_families_and_bounds(self):
        signatures=[]
        for style in STYLES:
            plan=plan_facade_layout(RING,24,style=style)
            self.assertEqual(plan['style'],style)
            openings=[o for e in plan['edges'] for o in e['openings']]
            if style=='blank':self.assertFalse(openings);continue
            self.assertTrue(openings,style)
            signatures.append(tuple(sorted((round(o['u1']-o['u0'],3),round(o['z1']-o['z0'],3)) for o in openings)))
            for e in plan['edges']:
                for o in e['openings']:
                    self.assertGreater(o['u0'],.4);self.assertLess(o['u1'],e['length']-.4)
                    self.assertGreater(o['z0'],0);self.assertLess(o['z1'],24)
            for specs in plan['groups'].values():
                for (x,y,z),(w,d,h),t,n in specs:
                    self.assertTrue(all(math.isfinite(v) for v in [x,y,z,w,d,h]))
                    self.assertGreater(min(w,d,h),0);self.assertGreaterEqual(z-h/2,0);self.assertLessEqual(z+h/2,24)
        self.assertEqual(len(set(signatures)),7)

    def test_openings_really_subtracted(self):
        for style in STYLES:
            plan=plan_facade_layout(RING,18,style=style)
            walls=wall_boxes(plan)
            for e in plan['edges']:
                for o in e['openings']:
                    u=(o['u0']+o['u1'])/2;z=(o['z0']+o['z1'])/2
                    p=(e['a'][0]+u*e['tangent'][0]-.08*e['normal'][0],
                       e['a'][1]+u*e['tangent'][1]-.08*e['normal'][1],z)
                    for c,size,t,n in walls:
                        delta=[p[i]-c[i] for i in range(3)]
                        inside=abs(delta[0]*t[0]+delta[1]*t[1])<size[0]/2-1e-6 and abs(delta[0]*n[0]+delta[1]*n[1])<size[1]/2-1e-6 and abs(delta[2])<size[2]/2-1e-6
                        self.assertFalse(inside,(style,o))
            vertices,faces=shell_mesh(plan)
            self.assertTrue(vertices);self.assertTrue(faces)
            self.assertTrue(all(len(f)>=3 and all(0<=i<len(vertices) for i in f) for f in faces))

    def test_conservative_neighbors_and_small_walls(self):
        touching=[(18,0),(30,0),(30,12),(18,12)]
        plan=plan_facade_layout(RING,18,style='apartment',neighbors=[touching])
        self.assertFalse(plan['edges'][1]['openings'])
        plan=plan_facade_layout([(0,0),(1.8,0),(1.8,1.8),(0,1.8)],10,style='house')
        self.assertFalse(any(e['openings'] for e in plan['edges']))
        bad=plan_facade_layout([(0,0),(12,12),(0,12),(12,0)],10)
        self.assertFalse(bad['edges'])

    def test_winding_and_dense_tall_floors(self):
        a=plan_facade_layout(RING,110,style='office')
        self.assertGreater(a['floors'],18)
        b=plan_facade_layout(list(reversed(RING)),110,style='office')
        self.assertEqual(sum(len(e['openings']) for e in a['edges']),sum(len(e['openings']) for e in b['edges']))
        for p in [a,b]:
            for c,size,t,n in p['groups']['glazing']:
                self.assertTrue(0<c[0]<18 and 0<c[1]<12)

    def test_shop_eligibility(self):
        roads=[{'points':[(-10,-7),(30,-7)],'width':6}]
        for style in ['house','warehouse','blank']:
            self.assertFalse(plan_facade_layout(RING,12,style=style,roads=roads)['groups']['shopfronts'])
        self.assertTrue(plan_facade_layout(RING,12,style='office',roads=roads)['groups']['shopfronts'])
        self.assertFalse(plan_facade_layout(RING,12,3,style='retail',roads=roads)['groups']['shopfronts'])

if __name__=='__main__':unittest.main()
